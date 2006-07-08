# Copyright (C) 1998-2006 by the Free Software Foundation, Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301,
# USA.

import os
import sys
import time
import socket
import logging
import nntplib
import optparse

import email.Errors
from email.Parser import Parser

from Mailman import LockFile
from Mailman import MailList
from Mailman import Message
from Mailman import Utils
from Mailman import loginit
from Mailman import mm_cfg
from Mailman.Queue.sbcache import get_switchboard
from Mailman.i18n import _

# Work around known problems with some RedHat cron daemons
import signal
signal.signal(signal.SIGCHLD, signal.SIG_DFL)

GATENEWS_LOCK_FILE = os.path.join(mm_cfg.LOCK_DIR, 'gate_news.lock')

LOCK_LIFETIME = mm_cfg.hours(2)
NL = '\n'

loginit.initialize(propagate=True)
log = logging.getLogger('mailman.fromusenet')

class _ContinueLoop(Exception):
    pass

__i18n_templates__ = True



def parseargs():
    parser = optparse.OptionParser(version=mm_cfg.MAILMAN_VERSION,
                                   usage=_("""\
%prog [options]

Poll the NNTP servers for messages to be gatewayed to mailing lists."""))
    opts, args = parser.parse_args()
    if args:
        parser.print_help()
        print >> sys.stderr, _('Unexpected arguments')
        sys.exit(1)
    return opts, args, parser



_hostcache = {}

def open_newsgroup(mlist):
    # Split host:port if given
    nntp_host, nntp_port = Utils.nntpsplit(mlist.nntp_host)
    # Open up a "mode reader" connection to nntp server.  This will be shared
    # for all the gated lists having the same nntp_host.
    conn = _hostcache.get(mlist.nntp_host)
    if conn is None:
        try:
            conn = nntplib.NNTP(nntp_host, nntp_port,
                                readermode=True,
                                user=mm_cfg.NNTP_USERNAME,
                                password=mm_cfg.NNTP_PASSWORD)
        except (socket.error, nntplib.NNTPError, IOError), e:
            log.error('error opening connection to nntp_host: %s\n%s',
                      mlist.nntp_host, e)
            raise
        _hostcache[mlist.nntp_host] = conn
    # Get the GROUP information for the list, but we're only really interested
    # in the first article number and the last article number
    r, c, f, l, n = conn.group(mlist.linked_newsgroup)
    return conn, int(f), int(l)


def clearcache():
    for conn in set(_hostcache.values()):
        conn.quit()
    _hostcache.clear()



# This function requires the list to be locked.
def poll_newsgroup(mlist, conn, first, last, glock):
    listname = mlist.internal_name()
    # NEWNEWS is not portable and has synchronization issues.
    for num in range(first, last):
        glock.refresh()
        try:
            headers = conn.head(repr(num))[3]
            found_to = False
            beenthere = False
            for header in headers:
                i = header.find(':')
                value = header[:i].lower()
                if i > 0 and value == 'to':
                    found_to = True
                if value <> 'x-beenthere':
                    continue
                if header[i:] == ': %s' % mlist.GetListEmail():
                    beenthere = True
                    break
            if not beenthere:
                body = conn.body(repr(num))[3]
                # Usenet originated messages will not have a Unix envelope
                # (i.e. "From " header).  This breaks Pipermail archiving, so
                # we will synthesize one.  Be sure to use the format searched
                # for by mailbox.UnixMailbox._isrealfromline().  BAW: We use
                # the -bounces address here in case any downstream clients use
                # the envelope sender for bounces; I'm not sure about this,
                # but it's the closest to the old semantics.
                lines = ['From %s  %s' % (mlist.GetBouncesEmail(),
                                          time.ctime(time.time()))]
                lines.extend(headers)
                lines.append('')
                lines.extend(body)
                lines.append('')
                p = Parser(Message.Message)
                try:
                    msg = p.parsestr(NL.join(lines))
                except email.Errors.MessageError, e:
                    log.error('email package exception for %s:%d\n%s',
                              mlist.linked_newsgroup, num, e)
                    raise _ContinueLoop
                if found_to:
                    del msg['X-Originally-To']
                    msg['X-Originally-To'] = msg['To']
                    del msg['To']
                msg['To'] = mlist.GetListEmail()
                # Post the message to the locked list
                inq = get_switchboard(mm_cfg.INQUEUE_DIR)
                inq.enqueue(msg,
                            listname=mlist.internal_name(),
                            fromusenet=True)
                log.info('posted to list %s: %7d', listname, num)
        except nntplib.NNTPError, e:
            log.exception('NNTP error for list %s: %7d', listname, num)
        except _ContinueLoop:
            continue
        # Even if we don't post the message because it was seen on the
        # list already, update the watermark
        mlist.usenet_watermark = num



def process_lists(glock):
    for listname in Utils.list_names():
        glock.refresh()
        # Open the list unlocked just to check to see if it is gating news to
        # mail.  If not, we're done with the list.  Otherwise, lock the list
        # and gate the group.
        mlist = MailList.MailList(listname, lock=False)
        if not mlist.gateway_to_mail:
            continue
        # Get the list's watermark, i.e. the last article number that we gated
        # from news to mail.  None means that this list has never polled its
        # newsgroup and that we should do a catch up.
        watermark = getattr(mlist, 'usenet_watermark', None)
        # Open the newsgroup, but let most exceptions percolate up.
        try:
            conn, first, last = open_newsgroup(mlist)
        except (socket.error, nntplib.NNTPError):
            break
        log.info('%s: [%d..%d]', listname, first, last)
        try:
            try:
                if watermark is None:
                    mlist.Lock(timeout=mm_cfg.LIST_LOCK_TIMEOUT)
                    # This is the first time we've tried to gate this
                    # newsgroup.  We essentially do a mass catch-up, otherwise
                    # we'd flood the mailing list.
                    mlist.usenet_watermark = last
                    log.info('%s caught up to article %d', listname, last)
                else:
                    # The list has been polled previously, so now we simply
                    # grab all the messages on the newsgroup that have not
                    # been seen by the mailing list.  The first such article
                    # is the maximum of the lowest article available in the
                    # newsgroup and the watermark.  It's possible that some
                    # articles have been expired since the last time gate_news
                    # has run.  Not much we can do about that.
                    start = max(watermark + 1, first)
                    if start > last:
                        log.info('nothing new for list %s', listname)
                    else:
                        mlist.Lock(timeout=mm_cfg.LIST_LOCK_TIMEOUT)
                        log.info('gating %s articles [%d..%d]',
                                 listname, start, last)
                        # Use last+1 because poll_newsgroup() employes a for
                        # loop over range, and this will not include the last
                        # element in the list.
                        poll_newsgroup(mlist, conn, start, last + 1, glock)
            except LockFile.TimeOutError:
                log.error('Could not acquire list lock: %s', listname)
        finally:
            if mlist.Locked():
                mlist.Save()
                mlist.Unlock()
        log.info('%s watermark: %d', listname, mlist.usenet_watermark)



def main():
    opts, args, parser = parseargs()
    lock = LockFile.LockFile(GATENEWS_LOCK_FILE,
                             # It's okay to hijack this
                             lifetime=LOCK_LIFETIME)
    try:
        lock.lock(timeout=0.5)
    except LockFile.TimeOutError:
        log.error('Could not acquire gate_news lock')
        return
    try:
        process_lists(lock)
    finally:
        clearcache()
        lock.unlock(unconditionally=True)



if __name__ == '__main__':
    main()
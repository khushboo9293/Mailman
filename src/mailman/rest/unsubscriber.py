# Copyright (C) 2010-2015 by the Free Software Foundation, Inc.
#
# This file is part of GNU Mailman.
#
# GNU Mailman is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# GNU Mailman is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# GNU Mailman.  If not, see <http://www.gnu.org/licenses/>.

"""REST for unsubscribers."""

__all__ = [
    'Unsubscriber',
    ]

from mailman.interfaces.listmanager import IListManager
from mailman.interfaces.member import CHANNELS
from mailman.rest.helpers import (
    CollectionMixin, bad_request,etag, no_content,  okay)
from mailman.rest.validator import Validator
from zope.component import getUtility
from mailman.model.member import Unsubscriber
from mailman.model import mailinglist
from mailman.model.roster import Unsubscribers 
import datetime


class Unsubscriber(CollectionMixin):
    """/unsubscriber/listname"""
    
    def _resource_as_dict(self, result):
        """See `CollectionMixin`."""
        return dict (no_of_unsubscriber = result)

    def __init__(self, list_identifier):
        """ Initialize the instance with the mailing list name for which 
            unsubscriber count is requested"""

        list_manager = getUtility(IListManager)
        if '@' in list_identifier:
            self._mlist = list_manager.get(list_identifier)
        else:
            self._mlist = list_manager.get_by_list_id(list_identifier)

    def get_count(self, start_date=None, stop_date=None):
        result = ""
        total = 0
        unsub_roster = Unsubscribers(self._mlist)    #see mailman/model/roster.py
        # reporting the unsubscribers via all the possible modes
        for channel in CHANNELS:
            if start_date and stop_date:
                count = unsub_roster.countUnsubscribers(channel, start_date, stop_date)
            else:
                count = unsub_roster.countUnsubscribers(channel)
            if count == 'db-error':
                return 'A database error occurred while retrieving the unsubscriber count.'
            total += int(0 if count is None else count)
            result += "The number of unsubscribers via \""+channel+"\": "+str(count)+"\n"
        result += "Total number of unsubscribers: "+str(total)
        return result

    def on_get(self, request, response):
        """return no of unsubscribers for different channels"""
        if self._mlist is None:
            bad_request(response, 'No such list')
            return
        result = self.get_count()
        okay(response, self._resource_as_json(result))

    def on_post(self, request, response):
        """return no of unsubscribers for different channels for a specific time period"""
        if self._mlist is None:
            bad_request(response, 'No such list')
            return

        validator = Validator(
            start_date=str,
            stop_date=str
            )
        try:
            values = validator(request)
        except ValueError as error:
            bad_request(response, str(error))
            return
        result = self.get_count(values['start_date'], values['stop_date'])
        okay(response, self._resource_as_json(result))

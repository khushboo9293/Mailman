# Copyright (C) 2011-fOA2015 by the Free Software Foundation, Inc.
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

"""REST unsubscriber tests."""

__all__ = [
    'TestUnsubscriber',
    ]

import unittest

from mailman.app.lifecycle import create_list
from mailman.config import config
from mailman.database.transaction import transaction
from mailman.interfaces.usermanager import IUserManager
from mailman.testing.helpers import call_api
from mailman.testing.layers import ConfigLayer, RESTLayer
from urllib.error import HTTPError
from zope.component import getUtility


class TestUnsubscriber(unittest.TestCase):
    layer = RESTLayer

    def setUp(self):
        with transaction():
            self._mlist = create_list('test@example.com')
        self._usermanager = getUtility(IUserManager)


    def test_count_unsubscriber_missing_list_get(self):
        # A user tries to count unsubscribes from a non-existent list.
        with self.assertRaises(HTTPError) as cm:
            call_api('http://localhost:9001/3.0/unsubscriber/missing@example.com')
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(cm.exception.reason, b'No such list')

    def test_count_unsubscriber_missing_list_post(self):
        # A user tries to count unsubscribes from a non-existent list for a time interval.
        with self.assertRaises(HTTPError) as cm:
            call_api('http://localhost:9001/3.0/unsubscriber/missing@example.com', {
                     'start_date':'2015-12-17',
                     'stop_date':'2015-12-19'
                      })
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(cm.exception.reason, b'No such list')

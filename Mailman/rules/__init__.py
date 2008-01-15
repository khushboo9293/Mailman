# Copyright (C) 2007 by the Free Software Foundation, Inc.
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

"""The built in rule set."""

__all__ = ['initialize']
__metaclass__ = type


import os
import sys

from Mailman.interfaces import IRule



def initialize():
    """Initialize the built-in rules.

    Rules are auto-discovered by searching for IRule implementations in all
    importable modules in this subpackage.
    """
    # Find all rules found in all modules inside our package.
    import Mailman.rules
    here = os.path.dirname(Mailman.rules.__file__)
    for filename in os.listdir(here):
        basename, extension = os.path.splitext(filename)
        if extension <> '.py':
            continue
        module_name = 'Mailman.rules.' + basename
        __import__(module_name, fromlist='*')
        module = sys.modules[module_name]
        for name in module.__all__:
            rule = getattr(module, name)
            if IRule.implementedBy(rule):
                yield rule

#!/usr/bin/env python3.2
#
# Copyright (c) Net24 Limited, Christchurch, New Zealand 2011-2012
#       and     Voyager Internet Ltd, New Zealand, 2012-2013
#
#    This file is part of py-magcode-core.
#
#    Py-magcode-core is free software: you can redistribute it and/or modify
#    it under the terms of the GNU  General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Py-magcode-core is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU  General Public License for more details.
#
#    You should have received a copy of the GNU  General Public License
#    along with py-magcode-core.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Auto PTR utility functions.  Here to prevent import nesting.
"""


from magcode.core import log_debug
from magcode.core import settings


def check_auto_ptr_privilege(op_rr_ref, sectag, zone_sm, old_rr):
    """
    Check whether an auto PTR operation can proceed
    """
    if sectag.sectag == settings['admin_sectag']:
        return True
    if not op_rr_ref:
        return False
    if not zone_sm.reference:
        return False
    if op_rr_ref == zone_sm.reference:
        return True
    if not old_rr:
        return False
    if not old_rr.reference:
        return False
    if op_rr_ref == old_rr.reference:
        return True
    return False


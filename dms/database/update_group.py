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
UpdateGroup - collects all the individual RR updates for a zone
"""


from sqlalchemy.orm import relationship

from magcode.core.database import *


@saregister
class UpdateGroup(object):
    """
    Class representing one collective update operation
    """
    _table = "update_groups"

    @classmethod
    def _mapper_properties(class_):
        zone_sm_type = sql_types['ZoneSM']
        zone_sm_table = sql_data['tables'][zone_sm_type]
        rr_type = sql_types['ResourceRecord']
        rr_table = sql_data['tables'][rr_type]
        return {
                'update_ops': relationship(rr_type, passive_deletes=True,
                                order_by=rr_table.c.get('id'), 
                                backref='update_group'),
                            }
    
    def __init__(self, update_type, change_by, ptr_only=False, sectag=None):
        """
        Initialize an update group
        """
        self.update_type = update_type
        self.ptr_only = ptr_only
        self.sectag = sectag
        self.change_by = change_by

def new_update_group(db_session, update_type, zone_sm, change_by=None, 
                    ptr_only=False, sectag=None):
    """
    Create a new update group
    """
    update_group = UpdateGroup(update_type, change_by=change_by, 
                                ptr_only=ptr_only, sectag=sectag)
    db_session.add(update_group)
    zone_sm.update_groups.append(update_group)
    # Get it out there to force early raise of IntegrityError
    db_session.flush()
    return update_group
    


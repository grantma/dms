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
Zone security tag class, corresponding to zone_sectags table
"""

from sqlalchemy.orm.exc import NoResultFound

from magcode.core.database import *
from dms.exceptions import ZoneSecTagExists
from dms.exceptions import ZoneSecTagDoesNotExist
from dms.exceptions import ZoneSecTagStillUsed

@saregister
class ZoneSecTag(object):
    """
    DNS Resource Record comment.

    Comparison methods are also used for sorting displayed output.
    """
    _table="zone_sectags"

    def __init__(self, sectag_label=None):
        """
        Initialise a security tag comment
        """
        self.sectag = sectag_label

    # For comparison purposes, including display!
    def __eq__(self, other):
        return self.sectag == other.sectag

    def __ne__(self, other):
        return self.sectag != other.sectag

    def __lt__(self, other):
        return self.sectag < other.sectag
    
    def __gt__(self, other):
        return self.sectag > other.sectag
    
    def __le__(self, other):
        return self.sectag <= other.sectag
    
    def __ge__(self, other):
        return self.sectag >= other.sectag

    def __str__(self):
        """
        Print out sectag name
        """
        return str(self.sectag)

    def to_engine(self, time_format=None):
        """
        Output for zone engine.
        """
        return {'zone_id': self.sectag, 'sectag_label': self.sectag}

    def to_engine_brief(self, time_format=None):
        """
        Brief output for zone_engine
        """
        return {'sectag_label': self.sectag}

def new_sectag(db_session, sectag_label):
    """
    Create a new sectag type
    """
    if sectag_label == settings['admin_sectag']:
        raise ZoneSecTagExists(sectag_label)
    zone_sectag = ZoneSecTag(sectag_label)
    try:
        sectag_list = db_session.query(ZoneSecTag)\
                        .filter(ZoneSecTag.zone_id == None)\
                        .filter(ZoneSecTag.sectag == sectag_label).all()
        if len(sectag_list):
            raise ZoneSecTagExists(sectag_label)
    except NoResultFound:
        pass
    db_session.add(zone_sectag)
    db_session.flush()
    return zone_sectag

def del_sectag(db_session, sectag_label):
    """
    Delete a sectag label
    """
    if sectag_label == settings['admin_sectag']:
        raise ZoneSecTagStillUsed(sectag_label)
    zone_sectag = ZoneSecTag(sectag_label)
    try:
        zone_sectag = db_session.query(ZoneSecTag)\
                        .filter(ZoneSecTag.zone_id == None)\
                        .filter(ZoneSecTag.sectag == sectag_label).one()
    except NoResultFound:
        raise ZoneSecTagDoesNotExist(sectag_label)
    # Check that it is no longer being used.
    try:
        in_use_count = db_session.query(ZoneSecTag.sectag)\
                        .filter(ZoneSecTag.zone_id != None)\
                        .filter(ZoneSecTag.sectag == sectag_label).count()
        if in_use_count:
            raise ZoneSecTagStillUsed(sectag_label)
    except NoResultFound:
        pass
    db_session.delete(zone_sectag)
    db_session.flush()
    del zone_sectag

def list_all_sectags(db_session):
    """
    Return list of all sectags
    """
    zone_sectags = [ZoneSecTag(settings['admin_sectag'])]
    try:
        zone_sectags.extend(db_session.query(ZoneSecTag)\
                            .filter(ZoneSecTag.zone_id == None).all())
    except NoResultFound:
        return zone_sectags
    return zone_sectags

def list_all_sectag_labels(db_session):
    """
    Return a list of all the sectag labels
    """
    zone_sectag_labels = [settings['admin_sectag']]
    try:
        zone_sectag_label_list = db_session.query(ZoneSecTag.sectag)\
                            .filter(ZoneSecTag.zone_id == None).all()
    except NoResultFound:
        pass
    zone_sectag_labels.extend([x[0] for x in zone_sectag_label_list])
    return zone_sectag_labels

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
Reference DB class.
"""


from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from magcode.core.database import *
from dms.exceptions import ReferenceExists
from dms.exceptions import ReferenceDoesNotExist
from dms.exceptions import ReferenceStillUsed
from dms.exceptions import MultipleReferencesFound
from dms.exceptions import NoReferenceFound


@saregister
class Reference(object):
    """
    Reference object for tagging data in database with things like customer IDs.
    """
    _table = 'reference'

    @classmethod
    def _mapper_properties(class_):
        zone_sm_type = sql_types['ZoneSM']
        zone_sm_table = sql_data['tables'][zone_sm_type]
        rr_type = sql_types['ResourceRecord']
        return {
                'zones': relationship(zone_sm_type, passive_deletes=True,
                                lazy='dynamic'),
                            }
    
    def __init__(self, reference=None):
        """
        Initialize a reference
        """
        self.reference = reference

    # For comparison purposes, including display!
    def __eq__(self, other):
        return self.reference.lower() == other.reference.lower()

    def __ne__(self, other):
        return self.reference.lower() != other.reference.lower()

    def __lt__(self, other):
        return self.reference.lower() < other.reference.lower()
    
    def __gt__(self, other):
        return self.reference.lower() > other.reference.lower()
    
    def __le__(self, other):
        return self.reference.lower() <= other.reference.lower()
    
    def __ge__(self, other):
        return self.reference.lower() >= other.reference.lower()

    def __str__(self):
        """
        Print out reference name
        """
        return str(self.reference)

    def set_zone(self, zone_sm):
        """
        Set the reference for a zone.

        Uses backref on zone to release old reference if it exists. 
        """
        if hasattr(zone_sm, 'reference') and zone_sm.reference:
            old_ref = zone_sm.reference
            old_ref.zones.remove(zone_sm)
        self.zones.append(zone_sm)
        zone_sm.reference = self

    def to_engine(self, time_format=None):
        """
        Output for zone engine.
        """
        return {'reference_id': self.id_, 'reference': self.reference}

    def to_engine_brief(self, time_format=None):
        """
        Brief output for zone_engine
        """
        return {'reference': self.reference}


def new_reference(db_session, reference, return_existing=False):
    """
    Create a new reference
    """
    ref_obj = Reference(reference)
    try:
        reference_list = db_session.query(Reference)\
                        .filter(Reference.reference.ilike(reference)).all()
        if len(reference_list):
            if not return_existing:
                raise ReferenceExists(reference)
            return reference_list[0]
    except NoResultFound:
        pass
    db_session.add(ref_obj)
    db_session.flush()
    return ref_obj

def del_reference(db_session, reference):
    """
    Delete a reference
    """
    try:
        ref_obj = db_session.query(Reference)\
                        .filter(Reference.reference.ilike(reference)).one()
    except NoResultFound:
        raise ReferenceDoesNotExist(reference)
    # Check that it is no longer being used.
    try:
        zone_sm_type = sql_types['ZoneSM']
        in_use_count = db_session.query(zone_sm_type)\
                        .filter(zone_sm_type.ref_id == ref_obj.id_).count()
        if in_use_count:
            raise ReferenceStillUsed(reference)
    except NoResultFound:
        pass
    db_session.delete(ref_obj)
    db_session.flush()
    del ref_obj

def find_reference(db_session, reference, raise_exc=True):
    """
    Find a reference and return it
    """
    if reference == None:
        if raise_exc:
            raise NoReferenceFound(reference)
        return None
    try:
        ref_obj = db_session.query(Reference)\
                .filter(Reference.reference.ilike(reference)).one()
    except NoResultFound:
        if raise_exc:
            raise NoReferenceFound(reference)
        return None
    except MultipleResultsFound:
        raise MultipleReferencesFound(reference)
    return ref_obj

def rename_reference(db_session, reference, dst_reference):
    """
    Rename a reference 
    """
    try:
        ref_obj = db_session.query(Reference)\
                        .filter(Reference.reference.ilike(reference)).one()
    except NoResultFound:
        raise ReferenceDoesNotExist(reference)
    try:
        reference_list = db_session.query(Reference)\
                        .filter(Reference.reference.ilike(dst_reference)).all()
        if len(reference_list):
            raise ReferenceExists(dst_reference)
    except NoResultFound:
        pass
    ref_obj.reference = dst_reference
    db_session.flush()
    return ref_obj

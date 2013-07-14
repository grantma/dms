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
Access zone_config table containing default values for zone initialisation, 
and Apex NS server names
"""


from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import and_
from sqlalchemy.sql import or_

from magcode.core.database import *
from dms.database.sg_utility import find_sg_byname
from dms.exceptions import ZoneCfgItemNotFound
from dms.exceptions import NoSgFound


@saregister
class ZoneCfg(object):
    """
    Zone Config row label value object
    """
    _table = 'zone_cfg'

    def __init__(self, key, value, sg_id=None):
        self.key = key
        self.value = value
        self.sg_id = sg_id

    def to_engine(self, time_format=None):
        """
        Dict for JSON serialized output
        """
        if (hasattr(self, 'sg') and self.sg):
            sg_name = self.sg.name
        else:
            sg_name = None
        return {'key': self.key, 'sg_name': sg_name, 'value': self.value}
    
    to_engine_brief = to_engine

def get_row(db_session, key, sg=None, sg_name=None, raise_exc=False):
    """
    Return the first value found for a key

    if key not found in sg, return value where sg_id is None
    """
    result = None
    if sg_name:
        sg = find_sg_byname(db_session, sg_name)
    if sg:
        stuff = [x for x in sg.zone_cfg_entries if x.key == key]
        if stuff:
            result = stuff[0].value
            return result
    try:
        stuff = db_session.query(ZoneCfg)\
                    .filter(and_(ZoneCfg.key == key, 
                        ZoneCfg.sg_id == None)).all()
        result = stuff[0].value
    except IndexError:
        result = None
    if raise_exc and not result:
        raise ZoneCfgItemNotFound(key)
    return result

def get_row_exc(db_session, key, sg=None, sg_name=None):
    """
    Return the first value found for a key

    Raises Exception suitable for JSON RPC
    """
    return get_row(db_session, key, sg=sg, sg_name=sg_name, raise_exc=True)

def get_rows(db_session, key, sg=None, sg_name=None, raise_exc=False):
    """
    Return all the values for a key as a list
    """
    result = []
    if sg_name:
        sg = find_sg_byname(db_session, sg_name)
    if sg:
        stuff = [x for x in sg.zone_cfg_entries if x.key == key]
        result = [x.value for x in stuff]
        if result:
            return result
    try:
        stuff = db_session.query(ZoneCfg)\
                    .filter(and_(ZoneCfg.key == key, 
                                ZoneCfg.sg_id == None)).all()
        result =  [x.value for x in stuff]
    except NoResultFound:
        result = []
    if raise_exc and not result:
        raise ZoneCfgItemNotFound(key)
    return result

def get_rows_exc(db_session, key, sg=None, sg_name=None):
    """
    Return all the values found for a key

    Raises Exception suitable for JSON RPC
    """
    return get_rows(db_session, key, sg=sg, sg_name=sg_name, raise_exc=True)

def set_row(db_session, key, value, sg=None, sg_name=None):
    """
    Set one row to a given value

    This is always called from command line or wsgi configuration code.
    """
    if sg_name:
        sg = find_sg_byname(db_session, sg_name)
        if not sg:
            raise NoSgFound(sg_name)
    if sg:
        stuff = [x for x in sg.zone_cfg_entries if x.key == key]
        if stuff:
            zone_cfg = stuff[0]
            zone_cfg.value = value
            db_session.flush()
            return
        zone_cfg = ZoneCfg(key, value)
        db_session.add(zone_cfg)
        sg.zone_cfg_entries.append(zone_cfg)
        db_session.flush()
        return

    # We have reached the part which processes the case of no SG being given
    # to function
    try:
        stuff = db_session.query(ZoneCfg)\
                    .filter(and_(ZoneCfg.key == key,
                                ZoneCfg.sg_id == None)).one()
        zone_cfg = stuff
        zone_cfg.value = value
    except NoResultFound:
        zone_cfg = ZoneCfg(key, value)
        db_session.add(zone_cfg)
    finally:
        db_session.flush()

def set_rows(db_session, key, values, sg=None, sg_name=None):
    """
    Set a whole key type to a list of values

    This is always called from command line or wsgi configuration code.
    """
    if sg_name:
        sg = find_sg_byname(db_session, sg_name)
        if not sg:
            raise NoSgFound(sg_name)
    sg_id = sg.id_ if sg else None
    try:
        # Easiest to delete and recreate
        stuff = db_session.query(ZoneCfg)\
                    .filter(and_(ZoneCfg.key == key,
                            ZoneCfg.sg_id == sg_id)).all()
        for zone_cfg in stuff:
            db_session.delete(zone_cfg)
    except NoResultFound:
        pass

    for value in values:
        zone_cfg = ZoneCfg(key, value, sg_id)
        db_session.add(zone_cfg)
    # Flush should reconstruct sg zone_cfg_entries lists?
    # Any how, this function is called in configuration code, and this is
    # the end of the query group for that.  ie - data will commited on function
    # call return
    db_session.flush()


    


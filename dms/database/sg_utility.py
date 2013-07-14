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
Server Group utilities

They are here to avoid import nesting problems
"""


import os
import stat
import pwd

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.sql import or_
from sqlalchemy.sql import and_
from sqlalchemy.sql import not_

from magcode.core.globals_ import settings
from magcode.core.database import sql_types
from dms.exceptions import SgMultipleResults
from dms.exceptions import NoSgFound
from dms.exceptions import SgExists
from dms.exceptions import SgStillHasZones
from dms.exceptions import SgStillHasServers
from dms.database.master_sm import set_mastersm_replica_sg

def list_all_sgs(db_session):
    """
    Return a list of all SG names
    """
    sg_type = sql_types['ServerGroup']
    sg_names = db_session.query(sg_type.name).all()
    sg_names = [x[0] for x in sg_names] 
    return sg_names

def find_sg_byname(db_session, sg_name, raise_exc=False):
    """
    Find an SG by name
    """
    sg_type = sql_types['ServerGroup']
    query = db_session.query(sg_type)\
            .filter(sg_type.name == sg_name)
    multiple_results = False
    try:
        sg = query.one()
    except NoResultFound:
        sg = None
    except MultipleResultsFound:
        multiple_results = True
    if multiple_results:
        raise SgMultipleResults(sg_name)
    if raise_exc and not sg:
        raise NoSgFound(sg_name)
    return sg

def find_sg_byid(db_session, sg_id, raise_exc=False):
    """
    Find an SG by id
    """
    sg_type = sql_types['ServerGroup']
    query = db_session.query(sg_type)\
            .filter(sg_type.id_ == sg_id)
    try:
        sg = query.one()
    except NoResultFound:
        sg = None
    if raise_exc and not sg:
        raise NoSgFound('*')
    return sg

def new_sg(db_session, sg_name, config_dir=None, address=None, 
        alt_address=None, replica_sg=False):
    """
    Create a new SG
    """
    sg_type = sql_types['ServerGroup']
    try:
        sg_list = db_session.query(sg_type)\
                        .filter(sg_type.name == sg_name).all()
        if len(sg_list):
            raise SgExists(sg_name)
    except NoResultFound:
        pass
    _check_config_dir(config_dir)
    sg = sg_type(sg_name, config_dir, master_address=address, 
            master_alt_address=alt_address)
    db_session.add(sg)
    if replica_sg:
        set_mastersm_replica_sg(db_session, sg)
    db_session.flush()
    return sg

def del_sg(db_session, sg_name):
    """
    Delete an SG
    """
    sg_type = sql_types['ServerGroup']
    # Get the SG from the DB.
    try:
        sg = db_session.query(sg_type)\
                    .filter(sg_type.name == sg_name).one()
    except NoResultFound:
        raise NoSgFound(sg_name)
    # Delete SG.  If it is still in use, SQA will raise an exception
    try:
        zone_sm_type = sql_types['ZoneSM']
        query = db_session.query(zone_sm_type)\
                        .filter(or_(zone_sm_type.sg_id == sg.id_,
                                    zone_sm_type.alt_sg_id == sg.id_))
        query = zone_sm_type.query_is_not_deleted(query)
        in_use_count = query.count()
        if in_use_count:
            raise SgStillHasZones(sg_name)
    except NoResultFound:
        pass
    if len(sg.servers):
        raise SgStillHasServers(sg_name)
    db_session.delete(sg)
    db_session.flush()
    del sg

def rename_sg(db_session, sg_name, new_sg_name):
    """
    Rename an SG
    """
    sg_type = sql_types['ServerGroup']
    # Get the SG from the DB.
    try:
        sg = db_session.query(sg_type)\
                    .filter(sg_type.name == sg_name).one()
    except NoResultFound:
        raise NoSgFound(sg_name)
    # Check that new_sg_name does not exist
    try:
        sg_list = db_session.query(sg_type)\
                        .filter(sg_type.name == new_sg_name).all()
        if len(sg_list):
            raise SgExists(new_sg_name)
    except NoResultFound:
        pass
    # Rename the SG
    sg.name = new_sg_name
    db_session.flush()

def set_sg_master_address(db_session, sg_name, address=None):
    """
    Set the master server address for the SG
    """
    sg_type = sql_types['ServerGroup']
    query = db_session.query(sg_type).filter(sg_type.name == sg_name)
    try:
        sg = query.one()
    except NoResultFound:
        raise NoSgFound(sg_name)
    sg.master_address = address
    db_session.flush()

def set_sg_master_alt_address(db_session, sg_name, address=None):
    """
    Set the alternate master server address for the SG
    """
    sg_type = sql_types['ServerGroup']
    query = db_session.query(sg_type).filter(sg_type.name == sg_name)
    try:
        sg = query.one()
    except NoResultFound:
        raise NoSgFound(sg_name)
    sg.master_alt_address = address
    db_session.flush()

def set_sg_config(db_session, sg_name, config_dir=None):
    """
    Set the config_dir of an SG
    """
    _check_config_dir(config_dir)
    sg_type = sql_types['ServerGroup']
    query = db_session.query(sg_type).filter(sg_type.name == sg_name)
    try:
        sg = query.one()
    except NoResultFound:
        raise NoSgFound(sg_name)
    sg.config_dir = config_dir
    db_session.flush()

def set_sg_replica_sg(db_session, sg_name):
    """
    Set the replica_sg flag
    """
    sg = None
    if sg_name:
        sg_type = sql_types['ServerGroup']
        query = db_session.query(sg_type).filter(sg_type.name == sg_name)
        try:
            sg = query.one()
        except NoResultFound:
            raise NoSgFound(sg_name)
    set_mastersm_replica_sg(db_session, sg)
    db_session.flush()


def _check_config_dir(config_dir):
    """
    Stat a directory and check that it exists, and is readable by 
    dmsdmd user
    """
    if not (config_dir):
        return
    # Check that config_dir exists
    stat_info = os.stat(config_dir)
    # Check that config_dir is a directory
    if not stat.S_ISDIR(stat_info.st_mode):
        raise IOError(errno.ENOTDIR, os.strerror(errno.ENOTDIR))
    # Check that config_dir is readable by run_as_user
    perm_bits = stat.S_IMODE(stat_info.st_mode)
    uid = stat_info.st_uid
    run_as_user = settings.get('run_as_user')
    if (not run_as_user):
        if (not (perm_bits & stat.S_IXOTH and perm_bits & stat.S_IROTH)):
            raise IOError(errno.EACCES, os.strerror(EACCESS))
        return
    try:
        run_as_user_pwd = pwd.getpwnam(run_as_user)
    except KeyError as exc:
        raise IOError(errno.EOWNERDEAD, os.strerror(errno.EOWNERDEAD))

    if (not (perm_bits & stat.S_IXOTH and perm_bits & stat.S_IROTH)
        and not ( uid == run_as_user_pwd.uid and perm_bits &stat.S_IXUSR 
            and perm_bits & stat.SIRUSR)):
        raise IOError(errno.EACCES, os.strerror(EACCESS))
    # If we get here, we can be sure dmsdmd can access the directory
    return

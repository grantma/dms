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
DNS Zone State Machine
"""


import glob
import os.path
from tempfile import mkstemp
import io
import os
import errno
import grp
import pwd
from datetime import timedelta
from datetime import datetime

from sqlalchemy.orm import reconstructor
from sqlalchemy.orm import relationship
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import and_
from sqlalchemy.sql import or_
from sqlalchemy.sql import not_

from magcode.core.database import *
from dms.exceptions import *
from dms.dns import RRCLASS_IN
from dms.globals_ import update_engine
from dms.globals_ import MASTER_STATIC_TEMPLATE
from dms.globals_ import MASTER_SLAVE_TEMPLATE
from dms.globals_ import MASTER_DYNDNS_TEMPLATE
from dms.globals_ import MASTER_AUTO_DNSSEC_TEMPLATE
import dms.database.zone_instance
import dms.database.zone_sectag
import dms.database.server_group
import dms.database.update_group
import dms.database.reverse_network
from magcode.core.database.event import create_event
from magcode.core.database.event import cancel_event
from magcode.core.database.event import reschedule_event
from magcode.core.database.state_machine import StateMachine
from magcode.core.database.state_machine import SMEvent
from magcode.core.database.state_machine import SMSyncEvent
from magcode.core.database.state_machine import StateMachineError
from magcode.core.database.state_machine import StateMachineFatalError
from magcode.core.database.state_machine import smregister
from magcode.core.database.event import Event
from magcode.core.database.event import ESTATE_SUCCESS
from magcode.core.database.event import eventregister
from magcode.core.database.event import synceventregister
from magcode.core.database.event import queue_event
from dms.template_cache import read_template
import dms.database.zone_cfg as zone_cfg
from dms.zone_text_util import data_to_bind
from dms.database.master_sm import zone_sm_reconfig_schedule
from dms.database.master_sm import zone_sm_dnssec_schedule
from dms.database.master_sm import reconfig_sg
from dms.database.sg_utility import find_sg_byname
from dms.database.sg_utility import list_all_sgs
from dms.database.reference import new_reference
from dms.exceptions import NoSgFound


sql_data['zone_sm_subclasses'] = []
sql_data['zone_sm_type_list'] = []

# Some Static Constants
ZSTATE_INIT = 'INIT'
ZSTATE_CREATE = 'CREATE'
ZSTATE_RESET = 'RESET'
ZSTATE_BATCH_CREATE_1 = 'BATCH_CREATE_1'
ZSTATE_BATCH_CREATE_2 = 'BATCH_CREATE_2'
ZSTATE_DELETED = 'DELETED'
ZSTATE_UNCONFIG = 'UNCONFIG'
ZSTATE_DISABLED = 'DISABLED'
ZSTATE_UPDATE = 'UPDATE'
ZSTATE_PUBLISHED = 'PUBLISHED'
ZLSTATE_EDIT_UNLOCK = 'EDIT_UNLOCK'
ZLSTATE_EDIT_LOCK = 'EDIT_LOCK'
zone_sm_states = (ZSTATE_UNCONFIG, ZSTATE_DISABLED,
                    ZSTATE_PUBLISHED, ZSTATE_UPDATE)

# Zone State machine exceptions
# Error Exceptions
class ZoneSMError(StateMachineError):
    """
    Base exception for Zone State Machine.
    """
    pass

class ZoneSMFatalError(StateMachineFatalError):
    """
    Base exception for Zone State Machine Fatal errors.
    """
    pass
class ZoneSMLockFailure(ZoneSMFatalError):
    """
    Lock mechanism failure
    """
class ZoneSMEventFailure(ZoneSMFatalError):
    """
    Event failure
    """
class ZoneSMUpdateFailure(ZoneSMFatalError):
    """
    Update failure
    """
class ZoneEditLocked(ZoneSMFatalError):
    """
    Exception raised if zone Locked, and an attempt
    to update or Exit the Edit session is made.
    """
    def __init__(self, domain, edit_lock_token, locked_by, locked_at):
        if locked_by:
            message = (
                "Zone '%s' is locked with token '%s', held by '%s', since %s."
                        % (domain, edit_lock_token, locked_by, locked_at))
        else:
            message = ("Zone '%s' is locked with token '%s' since %s."
                        % (domain, edit_lock_token, locked_at))
        Exception.__init__(self, message)
        self.domain = domain
        self.edit_lock_token = edit_lock_token

class ZoneEditLockTimedOut(ZoneSMFatalError):
    """
    Exception raised if zone was locked, and then timed out
    and an attempt to update zone ior tickle the edit lock is made.
    """
    def __init__(self, domain):
        message = ("Zone '%s' was locked and the lock timed out."
                        % domain )
        Exception.__init__(self, message)
        self.domain = domain

class ZoneNotEditLocked(ZoneSMFatalError):
    """
    Exception raised if zone Locked, and an attempt
    to update or Exit the Edit session is made.
    """
    def __init__(self, domain):
        message = ("Zone '%s' is not LOCKED."
                    % (domain))
        Exception.__init__(self, message)
        self.domain = domain

class ReadSoaRetry(ZoneSMError):
    """
    read_soa failed because of a temporary error 
    Will retry.
    """
class ZoneInBindRetry(ZoneSMError):
    """
    Retrying file configuration until bind reconfigured without zone.
    """
class ReadSoaFailed(ZoneSMFatalError):
    """
    read_soa failed permanently.
    """
class DynDNSUpdateRetry(ZoneSMError):
    """
    Dynamic Zone update failed because of a temporary error 
    Will retry.
    """
class DynDNSUpdateFailed(ZoneSMFatalError):
    """
    Dynamic Zone update failed permanently.
    """
class BatchCreateFailed(ZoneSMFatalError):
    """
    Dynamic Zone update failed permanently.
    """
class CreateFailed(ZoneSMFatalError):
    """
    Dynamic Zone update failed permanently.
    """
class ZoneAlreadyDisabled(ZoneSMFatalError):
    """
    Disabled zone is already disabled.
    """
class ZoneAlreadyEnabled(ZoneSMFatalError):
    """
    Disabled zone is already disabled.
    """
class ZoneResetDisabled(ZoneSMFatalError):
    """
    Disabled zone can't be reset
    """
class ZoneSMUndeleteFailure(ZoneSMFatalError):
    """
    Undelete failure - No ZI or Active zone exists
    """
class ZoneNotDestroyedFilesExist(ZoneSMFatalError):
    """
    Can't destroy a Zone as its Bind files still exist
    """
class ZoneNoAltSg(ZoneSMFatalError):
    """
    Can't swap SGs as alt_sg is not set.
    """

# Zone State Machine events
@eventregister
class ZoneSMBatchConfig(SMEvent):
    """
    Initialize configuration during a batch load
    """
@eventregister
class ZoneSMReconfigCheck(SMEvent):
    """
    Check that Master NS has loaded zone
    """
@eventregister
class ZoneSMConfig(SMEvent):
    """
    For ordinary configuration of zones.  Writes out initial ZI to 
    master dynamic directory, and then issues ZoneSmReconfigUpdate
    """
@eventregister
class ZoneSMReconfigUpdate(SMEvent):
    """
    Refresh zone on Master NS reconfig, loadkeys, or signzone
    """

@eventregister
class ZoneSMUpdate(SMEvent):
    """
    Update event publishing a ZI
    """
@eventregister
class ZoneSMRemoveZoneFiles(SMEvent):
    """
    Delete Zone files for a disabled or deleted domain
    """
@synceventregister
class ZoneSMDoReset(SMSyncEvent):
    """
    Reset the zone, via CREATE state.
    """
@synceventregister
class ZoneSMDoBatchConfig(SMSyncEvent):
    """
    Initialise the zone, from batch if it is NOT DNSSEC signed.
    """
@synceventregister
class ZoneSMDoConfig(SMSyncEvent):
    """
    Initialise the zone, normally or fall back from batch.
    """
@synceventregister
class ZoneSMDoReconfig(SMSyncEvent):
    """
    Reconfigure the zone, be it DNSSEC, or related to other issues.
    """
@synceventregister
class ZoneSMDoRefresh(SMSyncEvent):
    """
    Refresh a zone, by issuing an update.
    """
@synceventregister
class ZoneSMDoSgSwap(SMSyncEvent):
    """
    Swap between sg and alt_sg a zone, transfering a zone to a new SG.
    """
@synceventregister
class ZoneSMDoSetAltSg(SMSyncEvent):
    """
    Set the alt_sg on a zone.  Doing it in SM makes it possible to do it
    live
    """
@synceventregister
class ZoneSMEnable(SMSyncEvent):
    """
    Enable zone 
    """
@synceventregister
class ZoneSMDisable(SMSyncEvent):
    """
    Disable zone 
    """
@synceventregister
class ZoneSMDelete(SMSyncEvent):
    """
    Start deleting a zone
    """
@synceventregister
class ZoneSMNukeStart(SMSyncEvent):
    """
    Start process of nuking a zone
    """
@synceventregister
class ZoneSMDoDestroy(SMSyncEvent):
    """
    Destroy a zone if its zone files are cleared
    """
@synceventregister
class ZoneSMUndelete(SMSyncEvent):
    """
    Start undeleting a zone
    """
@synceventregister
class ZoneSMEdit(SMSyncEvent):
    """
    Start a locked editing session
    """
@synceventregister
class ZoneSMEditSavedNoLock(SMSyncEvent):
    """
    Unlocked edit ZI saved, commence update
    """

@synceventregister
class ZoneSMEditExit(SMSyncEvent):
    """
    Cancel a locked editing session
    """
    def __init__(self, sm_id, edit_lock_token, *args, **kwargs):
        super().__init__(sm_id, *args, edit_lock_token=edit_lock_token,
                            **kwargs)

@synceventregister
class ZoneSMEditSaved(SMSyncEvent):
    """
    Locked Edit ZI saved, commence update
    """
    def __init__(self, sm_id, edit_lock_token, *args, **kwargs):
        super().__init__(sm_id, *args, edit_lock_token=edit_lock_token,
                            **kwargs)

@synceventregister
class ZoneSMEditLockTickle(SMSyncEvent):
    """
    Locked Edit ZI saved, commence update
    """
    def __init__(self, sm_id, edit_lock_token, *args, **kwargs):
        super().__init__(sm_id, *args, edit_lock_token=edit_lock_token,
                            **kwargs)

@eventregister
class ZoneSMEditTimeout(SMEvent):
    """
    Timeout a locked editing session
    """

@eventregister
class ZoneSMEditUpdate(SMEvent):
    """
    Update event exiting a locked edit session.
    """
    def __init__(self, sm_id, edit_lock_token, *args, **kwargs):
        super().__init__(sm_id, *args, edit_lock_token=edit_lock_token,
                            **kwargs)

def zonesmregister(class_):
    """
    Event descedant class decorator function to register class for SQL
    Alchemy mapping in init_event_class() below, called in 
    magcode.core.database.utility.setup_sqlalchemy()
    """
    sql_data['zone_sm_subclasses'].append(class_)
    return(class_)

class BaseZoneSM(StateMachine):
    """
    Base Zone State Machine.

    Parent class to contain common code between Zone SM types.
    """
    
    def __init__(self, name):
        """
        Initialise attributes etc.
        """
        # We keep domains and labels in database lowercase 
        self.name = name.lower()
        self.state = ''
        self.edit_lock = False
        self.use_apex_ns = True
        self.auto_dnssec = False
        self.nsec3 = False
        self.zone_files = False
        self.inc_updates = False
        self._reset_edit_lock
   
    def _reset_edit_lock(self):
        self.locked_by = None
        self.locked_at = None
        self.edit_lock_token = None
        self.lock_state = ZLSTATE_EDIT_UNLOCK

    def __str__(self):
        return "Zone '%s'" % self.name

    def _to_engine_timestamps(self, time_format):
        """
        Backend common function to fill out timestamps for
        to_engine methods.
        """
        if not time_format:
            locked_at = (self.locked_at.isoformat(sep=' ') 
                               if self.locked_at else None)
            deleted_start = (self.deleted_start.isoformat(sep=' ') 
                               if self.deleted_start else None)
            ctime = (self.ctime.isoformat(sep=' ') 
                               if self.ctime else None)
            mtime = (self.mtime.isoformat(sep=' ') 
                               if self.mtime else None)
        else:
            locked_at = (self.locked_at.strftime(time_format) 
                               if self.locked_at else None)
            deleted_start = (self.deleted_start.strftime(time_format) 
                               if self.deleted_start else None)
            ctime = (self.ctime.strftime(time_format) 
                               if self.ctime else None)
            mtime = (self.mtime.strftime(time_format) 
                               if self.mtime else None)
        return (locked_at, deleted_start, ctime, mtime)


    def to_engine_brief(self, time_format=None):
        """
        Brief dict of zone_sm fields for zone engine
        """
        locked_at, deleted_start, ctime, mtime \
                = self._to_engine_timestamps(time_format)
        result =  {'zone_id': self.id_, 'zi_id': self.zi_id,
                'name': self.name, 'state': self.state, 
                'soa_serial': self.soa_serial, 
                'ctime': ctime, 'mtime': mtime,
                'deleted_start': deleted_start}
        result['reference'] = (self.reference.reference if self.reference
                                    else None)
        return result

    def to_engine(self, time_format=None):
        """
        Return dict of zone_sm fields for zone engine
        """
        locked_at, deleted_start, ctime, mtime \
                = self._to_engine_timestamps(time_format)
        result =  {'zone_id': self.id_, 'zi_id': self.zi_id, 
                'zi_candidate_id': self.zi_candidate_id,
                'state': self.state, 'soa_serial': self.soa_serial,
                'zone_type': self.zone_type, 'name': self.name, 
                'lock_state': self.lock_state,
                'locked_by': self.locked_by,
                'locked_at': locked_at,
                'use_apex_ns': self.use_apex_ns, 'edit_lock': self.edit_lock,
                'auto_dnssec': self.auto_dnssec, 'nsec3': self.nsec3,
                'edit_lock_token': self.edit_lock_token,
                'inc_updates': self.inc_updates,
                'sg_name': self.sg.name,
                'deleted_start': deleted_start,
                'ctime': ctime, 'mtime': mtime, }
        result['reference'] = (self.reference.reference if self.reference
                                    else None)
        result['alt_sg_name'] = (self.alt_sg.name if self.alt_sg 
                                    else None)
        return result

@smregister
@typeregister
class ZoneSM(BaseZoneSM):
    """
    IntermediateZone State Machine class which defines SQL Alchemy
    Accessors.
    """
    _sm_events = ()
    # self._tmplate_names indirection used so that config file settings
    # will take effect.
    _template_names = ()

    @classmethod
    def _mapper_properties(class_):
        zi_type = sql_types['ZoneInstance']
        zone_sectag_type = sql_types['ZoneSecTag']
        sg_type = sql_types['ServerGroup']
        reference_type = sql_types['Reference']
        zi_table = sql_data['tables'][zi_type]
        zone_sm_table = sql_data['tables'][ZoneSM]
        sg_table = sql_data['tables'][sg_type]
        ug_type = sql_types['UpdateGroup']
        ug_table = sql_data['tables'][ug_type]
        rn_type = sql_types['ReverseNetwork']
        return {'all_zis': relationship(zi_type,
                            primaryjoin=(zi_table.c.zone_id
                                == zone_sm_table.c.get('id')),
                            lazy='dynamic', passive_deletes=True),
                'zi':   relationship(zi_type,
                            primaryjoin=(zi_table.c.get('id')
                                == zone_sm_table.c.zi_id),
                            viewonly=True),
                'zi_candidate':   relationship(zi_type,
                            primaryjoin=(zi_table.c.get('id')
                                == zone_sm_table.c.zi_candidate_id),
                            foreign_keys=[zone_sm_table.c.zi_candidate_id],
                            viewonly=True),
                'sg':  relationship(sg_type, primaryjoin=(
                            sg_table.c.get('id') == zone_sm_table.c.sg_id),
                            viewonly=True),
                'alt_sg':  relationship(sg_type, primaryjoin=(
                        sg_table.c.get('id') == zone_sm_table.c.alt_sg_id),
                            viewonly=True),
                'reference': relationship(reference_type, viewonly=True),
                'sectags': relationship(zone_sectag_type, passive_deletes=True),
                'update_groups': relationship(ug_type, passive_deletes=True,
                                        order_by=ug_table.c.get('id'), 
                                        backref='zone'),
                'reverse_network': relationship(rn_type, passive_deletes=True,
                                uselist=False, backref='zone'),
                            }


    @classmethod
    def sa_map_subclass(class_):
        sql_data['mappers'][class_] = mapper(class_,
                    inherits=sql_data['mappers'][ZoneSM], 
                    polymorphic_identity=class_.__name__)
        sql_data['zone_sm_type_list'].append(class_.__name__)

    def add_sectag(self, db_session, zone_sectag):
        """
        Add a security tag to the Zone
        """
        ZoneSecTag = sql_types['ZoneSecTag']
        # Skip admin sectag
        if zone_sectag == ZoneSecTag(settings['admin_sectag']):
            return
        # Make sure sec tag does not already exist
        if zone_sectag in self.sectags:
            return
        db_session.add(zone_sectag)
        self.sectags.append(zone_sectag)

    def remove_sectag(self, db_session, zone_sectag):
        """
        Remove a security tag from the zone
        """
        ZoneSecTag = sql_types['ZoneSecTag']
        # Skip admin sectag
        if zone_sectag == ZoneSecTag(settings['admin_sectag']):
            return
        # form list of objects to delete
        del_list = [x for x in self.sectags if x == zone_sectag]
        for x in del_list:
            self.sectags.remove(x)
        while del_list:
            db_session.delete(del_list[-1])
            x = del_list.pop()
            if not x:
                continue
            del x

    def remove_all_sectags(self, db_session):
        """
        Remove all security tags from the zone.
        """
        while self.sectags:
            sectag = self.sectags.pop()
            if not sectag:
                continue
            db_session.delete(sectag)
            del sectag

    def copy_zone_sectags(self, db_session, src_zone_sm):
        """
        add sectag list to a zone
        """
        ZoneSecTag = sql_types['ZoneSecTag']
        admin_sectag = ZoneSecTag(settings['admin_sectag'])
        for src_sectag in src_zone_sm.sectags:
        # Skip admin sectag
            if src_sectag == admin_sectag:
                continue
            zone_sectag = ZoneSecTag(src_sectag.sectag)
            self.add_sectag(db_session, zone_sectag)

    def replace_all_sectags(self, db_session, *zone_sectags):
        """
        Replace all sectags for a zone
        """
        self.remove_all_sectags(db_session)
        for zone_sectag in zone_sectags:
            self.add_sectag(db_session, zone_sectag)

    def list_sectags(self, db_session):
        """
        List all security tags for this zone as JSON
        """
        result = [sql_types['ZoneSecTag'](settings['admin_sectag'])\
                        .to_engine_brief()]
        result.extend([t.to_engine_brief() for t in self.sectags])
        return result

    def set_sg(self, sg):
        """
        Set the server group this zone is served from.
        """
        if hasattr(self, 'sg') and self.sg:
            old_sg = self.sg
            old_sg.zones.remove(self)
            self.sg = None
        sg.zones.append(self)
        self.sg = sg

    def _set_alt_sg(self, sg):
        """
        Set the alternate server group this zone is served from.
        """
        if hasattr(self, 'alt_sg') and self.alt_sg:
            old_sg = self.alt_sg
            old_sg.alt_zones.remove(self)
            self.alt_sg = None
        if sg:
            sg.alt_zones.append(self)
        self.alt_sg = sg

    def write_config(self, include_file, db_session, server_acls, 
            replica_sg=None):
        """
        Fill out master server configuration template

        Stub function that needs overriding in descendant class
        """
        raise IOError(errno.EINVAL, os.strerror(errno.EINVAL), include_name)
        # Exceptions for this caught by an outer try: in the 
        # self._tmplate_names indirection used so that config file settings
        # will take effect.
        #template_name = (settings['master_template_dir'] + '/' 
        #                        + settings[self._template_names[0]])
        #template = read_template(template_name)
        #filler = { 'name': self.name, }
        #section = template % filler
        # include_file.write(section)
    
    def is_disabled_or_deleted(self):
        """
        Test to see if a zone is disabled or deleted.

        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return self.state in (ZSTATE_DISABLED, ZSTATE_DELETED,)

    @classmethod
    def query_is_not_disabled_deleted(self, query):
        """
        Test to see if a zone is not disabled or deleted.

        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return query.filter(and_(self.state != ZSTATE_DISABLED,
                    self.state != ZSTATE_DELETED))

    def is_not_configured(self):
        """
        Test to see if a zone is not configured.

        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return self.state in (ZSTATE_DISABLED, ZSTATE_DELETED, ZSTATE_CREATE,
                            ZSTATE_BATCH_CREATE_1)
    
    @classmethod
    def query_sg_is_configured(self, query):
        """
        Test to see if a zone is configured for use in server config

        Considers ZSTATE_RESET to be a configured state, so that zones are
        not removed from servers during a ZonsSM reset
        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return query.filter(~ self.state.in_((ZSTATE_DISABLED, ZSTATE_DELETED,
            ZSTATE_CREATE, ZSTATE_BATCH_CREATE_1)) )

    @classmethod
    def query_is_configured(self, query):
        """
        Test to see if a zone is configured.

        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return query.filter(~ self.state.in_((ZSTATE_DISABLED, ZSTATE_DELETED,
            ZSTATE_CREATE, ZSTATE_RESET, ZSTATE_BATCH_CREATE_1)) )

    def is_deleted(self):
        """
        Test to see if a zone is deleted.

        Saves having to import ZSTATE_DELETED and thus import nesting...
        """
        return self.state in (ZSTATE_DELETED,)
    
    @classmethod
    def query_is_not_deleted(self, query):
        """
        Add a test to a query to see if a zone is deleted or not
        """
        return query.filter(self.state != ZSTATE_DELETED)

    def is_disabled(self):
        """
        Test to see if a zone is disabled.

        Saves having to import ZSTATE_DISABLED and thus import nesting...
        """
        return self.state == ZSTATE_DISABLED

    @classmethod
    def query_inc_updates(self, query):
        """
        Add a test to a query to see if a zone has inc_updates enabled.
        """
        return query.filter(self.inc_updates == True)

    def _do_incremental_updates(self, db_session, zi,
                        process_inc_updates=False):
        """
        Process incremental updates for a zone
        """
        # Check if zone edit locked, if so, defer
        # This to prevent updates being 'lost'
        if (not process_inc_updates and self.edit_lock == ZLSTATE_EDIT_LOCK):
            return zi
        # Pull in all update groups for zone
        UpdateGroup = sql_types['UpdateGroup']
        query = db_session.query(UpdateGroup)\
                .filter(UpdateGroup.zone_id == self.id_)
        updates = query.all()
        # Check to see if there are updates
        if not len(updates):
            return zi
        # Check and see if updates are all PTR related, if so, follow different
        # copy algorithm
        normal_updates = [ug for ug in updates if not ug.ptr_only]
        if not len(normal_updates):
            # only create new candidate ZI only if config_hold_time has passed
            # This means published reverse ZI gets morphed, only time a
            # ZI contents get changed other than Apex records and Zone 
            # TTL updates
            time = db_time(db_session)
            freeze_time = timedelta(
                            minutes=float(settings['master_hold_timeout']))
            if (self.zi and time > (self.zi.ctime + freeze_time) 
                and self.zi_candidate_id == self.zi_id):
                zi = zi.copy(db_session)
            elif self.zi_candidate_id == self.zi_id:
                log_debug("Zone '%s' - republishing old reverse ZI %s."
                            % (self.name, zi.id_))
       
        # Normal copy algorithm
        elif (self.zi_candidate_id == self.zi_id):
            # create new candidate ZI
            zi = zi.copy(db_session)

        # Apply each update group to candidate ZI
        for ug in updates:
            zi.exec_update_group(db_session, ug)

        # return updated zi
        return zi
        

@smregister
@zonesmregister
class StaticZoneSM(ZoneSM):
    """
    Static Zone File State Machine

    Implements the traditional static zone file
    Currently just a place holder
    """
    pass
    _template_names = (MASTER_STATIC_TEMPLATE,)


@smregister
@zonesmregister
class SlaveZoneSM(ZoneSM):
    """
    Slave Zone File State Machine

    Implements a slaved master
    Currently just a place holder
    """
    _template_names = (MASTER_SLAVE_TEMPLATE,)
    pass


@smregister
@zonesmregister
class DynDNSZoneSM(ZoneSM):
    """
    Dynamic DNS Zone State Machine

    Implements Zone State machine that uses Dynamic DNS for Updates
    """
    # self._tmplate_names indirection used so that config file settings
    # will take effect.
    _template_names = (MASTER_DYNDNS_TEMPLATE, MASTER_AUTO_DNSSEC_TEMPLATE,)
    _sm_events= (ZoneSMDoReset, ZoneSMDoSgSwap, ZoneSMDoSetAltSg,
            ZoneSMDoBatchConfig, ZoneSMBatchConfig, ZoneSMReconfigCheck,
            ZoneSMDoReconfig, ZoneSMReconfigUpdate, ZoneSMDoConfig, 
            ZoneSMConfig, ZoneSMRemoveZoneFiles,
            ZoneSMEnable, ZoneSMDisable, ZoneSMDoRefresh, ZoneSMEditExit,
            ZoneSMEdit, ZoneSMUpdate, ZoneSMEditUpdate, ZoneSMEditSaved,
            ZoneSMEditSavedNoLock,
            ZoneSMEditLockTickle, ZoneSMEditTimeout, ZoneSMDelete,
            ZoneSMUndelete, ZoneSMNukeStart, ZoneSMDoDestroy)

    def __init__(self, name, edit_lock=False, use_apex_ns=True,
            auto_dnssec=False, nsec3=False, inc_updates=False):
        """
        Initialise Zone SM
        """
        super().__init__(name)
        self.edit_lock = edit_lock
        self.use_apex_ns = use_apex_ns
        self.auto_dnssec = auto_dnssec
        self.nsec3 = nsec3
        self.inc_updates = inc_updates
        self.state = ZSTATE_INIT
    
    def _process_edit_lock_token_mismatch(self):
        """
        Handle a lock token mismatch.  Needed to handle lock timeout as
        well as actually locked zone.
        """
        if self.lock_state == ZLSTATE_EDIT_UNLOCK:
            raise ZoneEditLockTimedOut(self.name)
        else:
            raise ZoneEditLocked(self.name, self.edit_lock_token,
                    self.locked_by, self.locked_at)

    def write_zone_file(self, db_session, op_exc):
        """
        Write out zone file.

        Usable from outside as root for recovery purposes
        """
        # Get zi, if not found, fail gracefully
        zi_type = sql_types['ZoneInstance']
        err_string = ''
        try:
            zi = db_session.query(zi_type)\
                    .filter(zi_type.id_ == self.zi_candidate_id).one()
        except NoResultFound as exc:
            err_string = str(exc)
        if err_string:
            raise op_exc("Zone '%s' - %s" % (self.name, err_string))
        # Write/overwrite current zi to NS dynamic dir
        err_string = ''
        err_filename = ''
        try:
            dynamic_zone_dir = settings['master_dyndns_dir']
            # Remove dot at end of zone name as this gives more
            # human literate filenames
            human_name = self.name[:-1] if self.name.endswith('.') \
                                    else self.name
            zone_file = settings['master_dyndns_dir'] + '/' + human_name
            zone_file_jnl = zone_file + '.jnl'
            zi_data = zi.to_data(all_rrs=True)
            prefix = '.' + os.path.basename(human_name) + '-'
            (fd, tmp_filename) = mkstemp(
                        dir=dynamic_zone_dir,
                        prefix=prefix)
            tmp_file = io.open(fd, mode='wt')
            reference = self.reference.reference if self.reference else None
            data_to_bind(zi_data, self.name, tmp_file, reference=reference,
                        for_bind=True)
            tmp_file.close()
            # Rename tmp file into place so that replacement is atomic
            try:
                uid = pwd.getpwnam(settings['run_as_user']).pw_uid
                bind_gid = grp.getgrnam(settings['zone_file_group']).gr_gid
            except KeyError as exc:
                msg = ("Could not look up group '%s' or user '%s'"
                        " for zone file for %s" 
                        % (settings['zone_file_group'],
                            settings['run_as_user'],
                            self.name))
                raise op_exc(msg)
            os.chown(tmp_filename, uid, bind_gid)
            os.chmod(tmp_filename, int(settings['zone_file_mode'],8))
            # Update zone_files flag
            self.zone_files = True
            try:
                # Remove journal file - can cause trouble with bind
                os.unlink(zone_file_jnl)
            except:
                pass
            os.rename(tmp_filename, zone_file)
        except (IOError, OSError) as exc:
            err_string = exc.strerror
            err_filename = exc.filename
        finally:
            # clean up if possible
            try:
                os.unlink(tmp_filename)
            except:
                pass
        if err_string:
            msg = ( "Could not write file '%s' - %s." 
                            % (err_filename, err_string))
            raise op_exc(msg)

    def _remove_zone_files(self, event):
        """
        Tidy up routine to remove zone files.  Does not matter it if errors
        """
        db_session = event.db_session
        # Set self.zone_files false as this janitor event for zone is being
        # executed. If another zone active, when it is deleted or disabled it
        # will remove the files if another zone instance is not active then...
        try:
            query = db_session.query(ZoneSM)\
                    .filter(ZoneSM.name == self.name)\
                    .filter(and_(ZoneSM.state != ZSTATE_DELETED, 
                                ZoneSM.state != ZSTATE_DISABLED))
            result = query.all()
            if result:
                self.zone_files = False
                return (RCODE_OK, "Zone '%s' - not removing files "
                        "as another zone instance active" 
                        % self.name)
        except NoResultFound:
            pass
        finally:
            del result
        human_name = self.name[:-1] if self.name.endswith('.') \
                                    else self.name
        zone_file = settings['master_dyndns_dir'] + '/' + human_name
        zone_file_jnl = zone_file + '.jnl'
        try:
            os.unlink(zone_file)
            os.unlink(zone_file_jnl)
        except:
            pass
        self.zone_files = False
        return (RCODE_OK, "Zone '%s' - tidy up - zone files probably deleted" 
                        % self.name)

    def _do_destroy(self, event):
        """
        ZoneSM routine to remove zone, will only succeed if zone files have 
        already been removed, otherwise will queue a ZoneSMRemoveZoneFiles
        """
        if not self.zone_files:
            event.db_session.delete(self)
            return (RCODE_OK, 
                    "Zone '%s' - destroying, zone files deleted"
                    % self.name)
        # Can't do it now, but need to seed our own future destruction
        # Use coalesce_period to avoid double events if possible
        buffer_period = timedelta(seconds=3*float(settings['sleep_time']))
        coalesce_period = timedelta(
                            minutes=2*float(settings['master_hold_timeout']))
        create_event(ZoneSMRemoveZoneFiles, db_session=event.db_session, 
                        sm_id=self.id_, zone_id=self.id_, name=self.name,
                        coalesce_period=coalesce_period,
                        delay=coalesce_period+buffer_period)
        raise ZoneNotDestroyedFilesExist(
                "Zone '%s' - not destroyed zone files still exist" 
                                            % self.name)

    def _do_batch_config(self, event):
        """
        Batch configure zone
        """
        # Add zi from event if zone is being created
        self.zi_candidate_id = event.py_parameters['zi_id']
        # Initialise self.zi_id so that show_zone works on zone creation 
        if not self.zi_id:
            self.zi_id = event.py_parameters['zi_id']
        self.state = ZSTATE_BATCH_CREATE_1
        create_event(ZoneSMBatchConfig, db_session=event.db_session,
                        sm_id=self.id_, zone_id=self.id_, name=self.name)
        return (RCODE_OK, "Zone '%s' - initialising" % self.name)

    def _batch_config(self, event):
        """
        Initialise zone configuration to named.conf on master and servers
        """
        self.write_zone_file(event.db_session, BatchCreateFailed)
        self.state = ZSTATE_BATCH_CREATE_2
        # Queue ZoneSMReconfigCheck
        zone_sm_reconfig_schedule(event.db_session, self, ZoneSMReconfigCheck)
        return (RCODE_OK, "Zone '%s' -  Wrote seed zone file, queuing reconfig" 
                        % self.name)

    def _reconfig_check(self, event):
        """
        Check that zone is loaded on zone creation
        """
        db_session = event.db_session
        # Run update engine
        (rcode, msg, soa_serial) = update_engine['dyndns']\
                                    .read_soa(self.name)

        # Handle auto reset of Zone SM if DNS server is not configured
        if rcode == RCODE_RESET:
            log_info(msg)
            msg = "reseting ZoneSM as server not configured" 
            return self._do_reset(event, msg, randomize=True, via_create=True)

        if rcode == RCODE_ERROR:
            raise ReadSoaRetry(msg)
        elif rcode == RCODE_FATAL:
            raise ReadSoaFailed(msg)
        if self.zi_id != self.zi_candidate_id:
            self.zi_id = self.zi_candidate_id
        self.state = ZSTATE_PUBLISHED
        return (RCODE_OK, "Zone '%s' - Master NS loaded successfully"
                            % self.name)

    def _retry_reconfig(self, event, randomize=False):
        """
        Retry ZoneSMReconfigUpdate
        """
        self.state = ZSTATE_UNCONFIG
        # Queue ZoneSMReconfigUpdate
        zone_sm_reconfig_schedule(event.db_session, self, ZoneSMReconfigUpdate, 
                            randomize=randomize)
        msg = "Retrying reconfig of ZoneSM as server not configured" 
        return (RCODE_OK, msg)

    def _do_reset(self, event, msg=None, randomize=False, via_create=False):
        """
        Reset the Zone SM, going via CREATE state as per normal zone creation 
        """
        db_session = event.db_session
        # Specifically fetch parameters
        zi_id = event.py_parameters.get('zi_id')
        if zi_id:
            self.zi_candidate_id = event.py_parameters['zi_id']
            # Initialise self.zi_id so that show_zone works on zone creation 
            if not self.zi_id:
                self.zi_id = event.py_parameters['zi_id']
        self.state = ZSTATE_CREATE if via_create else ZSTATE_RESET
        # Queue ZoneSMConfig, only master bind reconfiguration,
        # to preserve anything being currently served on servers
        zone_sm_reconfig_schedule(db_session, self, ZoneSMConfig, 
                                    master_reconfig=True, randomize=randomize)
        msg = "Zone '%s' - reseting SM" % self.name
        return (RCODE_OK, msg)

    def _do_config(self, event):
        """
        Initialise zone creation normally 
        """
        db_session = event.db_session
        # Add zi from event if zone is being created
        self.zi_candidate_id = event.py_parameters['zi_id']
        # Initialise self.zi_id so that show_zone works on zone creation 
        if not self.zi_id:
            self.zi_id = event.py_parameters['zi_id']
        self.state = ZSTATE_CREATE
        create_event(ZoneSMConfig, db_session=db_session,
                        sm_id=self.id_, zone_id=self.id_, name=self.name)
        return (RCODE_OK, "Zone '%s' - initialising" % self.name)

    def _config(self, event, write_file_exc=CreateFailed):
        """
        Add configuration to named.conf on master and servers
        """
        db_session = event.db_session

        # Run update engine - we are checking to see if zone is in bind
        (rcode, msg, soa_serial) = update_engine['dyndns']\
                                    .read_soa(self.name)
        if rcode == RCODE_ERROR:
            raise ReadSoaRetry(msg)
        if rcode == RCODE_OK:
            msg = ("Zone '%s' - reconfiguring ZoneSM as server not configured"
                    % self.name)
            log_info(msg)
            return self._do_reset(event, via_create=False)

        self.write_zone_file(db_session, write_file_exc)
        self.state = ZSTATE_UNCONFIG
        # Queue ZoneSMReconfigUpdate
        zone_sm_reconfig_schedule(db_session, self, ZoneSMReconfigUpdate)
        return (RCODE_OK, "Zone '%s' -  Wrote seed zone file, queuing reconfig" 
                        % self.name)
    
    def _reconfig_update(self,event):
        """
        Update upon rndc reconfig
        """
        return self._update(event)

    def _nuke_start(self, event):
        """
        Prepare a zone to be nuked by setting it to deleted state.
        """
        return self._delete(event, nuke_start=True)

    def _delete(self, event, nuke_start=False):
        """
        Delete processing for zone
        """
        # check that zone is not EDIT_LOCKED
        if  (self.lock_state == ZLSTATE_EDIT_LOCK):
            raise ZoneEditLocked(self.name, self.edit_lock_token,
                    self.locked_by, self.locked_at)
        # set state to DELETED
        if self.state in (ZSTATE_PUBLISHED, ZSTATE_UPDATE):
            if self.zi_id != self.zi_candidate_id:
                self.zi_id = self.zi_candidate_id
        self.state = ZSTATE_DELETED
        if nuke_start:
             self.deleted_start = None
        else:
            self.deleted_start = db_time(event.db_session)
        # Queue MasterSMPartialReconfig
        zone_sm_reconfig_schedule(event.db_session, self, ZoneSMRemoveZoneFiles)
        if nuke_start:
            msg = ("Zone '%s' - DELETED state preparing to nuke"
                            % self.name)
        else:
            msg = ("Zone '%s' - going into DELETED state"
                            % self.name)
        return (RCODE_OK, msg)

    def _event_failure(self, event):
        """
        Fail an event when zone is in INIT transient state.
        """
        raise ZoneSMEventFailure(
                "Zone '%s' - event failed as zone in transient INIT state"
                % self.name)

    def _update_fail(self, event):
        """
        Fail an when zone is in UPDATE state with edit_locked changes being
        saved.
        """
        raise ZoneSMUpdateFailure(
                "Zone '%s' - Failure due to UPDATE state changes being saved"
                % self.name)

    def _undelete(self, event):
        """
        Undelete a zone from DELETED to UNCONFIG, then proceed to enable it.
        """
        # Get zi, if not found, fail gracefully
        zi_type = sql_types['ZoneInstance']
        err_string = ''
        try:
            zi = event.db_session.query(zi_type)\
                    .filter(zi_type.id_ == self.zi_candidate_id).one()
        except NoResultFound as exc:
            err_string = str(exc)
        if err_string:
            raise ZoneSMUndeleteFailure("Zone '%s' - %s" % (self.name, msg))
        # Check that we are only zone instance
        db_session = event.db_session
        try:
            query = db_session.query(ZoneSM)\
                    .filter(ZoneSM.name == self.name)\
                    .filter(ZoneSM.state != ZSTATE_DELETED)
            result = query.all()
            if result:
                raise ZoneSMUndeleteFailure(
                    "Zone '%s' - Failure as other instances of zone are active"
                        % self.name)
        except NoResultFound:
            pass
        # Go to CREATE
        self.deleted_start = None
        self.zi_candidate_id = self.zi_id
        self.state = ZSTATE_CREATE
        create_event(ZoneSMConfig, db_session=event.db_session,
                        sm_id=self.id_, zone_id=self.id_, name=self.name)
        return (RCODE_OK, "Zone '%s' - undeleted and initialising" % self.name)

    def _disable(self, event):
        """
        Remove configuration to named.conf on master and servers
        """
        if self.state in (ZSTATE_PUBLISHED, ZSTATE_UPDATE):
            if self.zi_id != self.zi_candidate_id:
                self.zi_id = self.zi_candidate_id
        self.state = ZSTATE_DISABLED
        # Execute Configuration SM here
        # Do a MasterSMPartialReconfig here
        zone_sm_reconfig_schedule(event.db_session, self, ZoneSMRemoveZoneFiles)
        return (RCODE_OK, "Zone '%s' - disabling" % self.name)

    def _already_disabled(self, event):
        """
        Zone already disabled
        """
        raise ZoneAlreadyDisabled("Zone '%s' - already disabled" % self.name)

    def _enable(self, event):
        """
        Proceed to enable zone
        """
        self.state = ZSTATE_CREATE
        create_event(ZoneSMConfig, db_session=event.db_session,
                        sm_id=self.id_, zone_id=self.id_, name=self.name)
        return (RCODE_OK, "Zone '%s' - enabled and initialising" % self.name)

    def _already_enabled(self, event):
        """
        Zone already enabled
        """
        raise ZoneAlreadyEnabled("Zone '%s' - already enabled" % self.name)

    def _reset_disabled(self, event):
        """
        Zone disabled - can't reset
        """
        raise ZoneResetDisabled("Zone '%s' - disabled, can't reset" % self.name)

    def _do_reconfig(self, event):
        """
        Reconfigure zone
        """
        if self.state in (ZSTATE_PUBLISHED, ZSTATE_UPDATE):
            if self.zi_id != self.zi_candidate_id:
                self.zi_id = self.zi_candidate_id
        self.state = ZSTATE_UNCONFIG
        zone_sm_reconfig_schedule(event.db_session, self, ZoneSMReconfigUpdate)
        return (RCODE_OK, "Zone '%s' - reconfiguring" % self.name)

    def _do_refresh(self, event):
        """
        Refresh a zone by queuing an update event.
        """
        if self.state in (ZSTATE_PUBLISHED,):
            zi_candidate_id = event.py_parameters.get('zi_id')
            wrap_soa_serial = event.py_parameters.get('wrap_soa_serial')
            candidate_soa_serial = event.py_parameters.get(
                                                    'candidate_soa_serial')
            force_soa_serial_update = event.py_parameters.get(
                                                    'force_soa_serial_update')
            if (wrap_soa_serial or candidate_soa_serial 
                                            or force_soa_serial_update):
                # Can only do these operations if zone is not locked.
                if (self.lock_state == ZLSTATE_EDIT_LOCK):
                    raise ZoneEditLocked(self.name, self.edit_lock_token,
                            self.locked_by, self.locked_at)
            if zi_candidate_id:
                if (self.lock_state == ZLSTATE_EDIT_LOCK):
                    raise ZoneEditLocked(self.name, self.edit_lock_token,
                            self.locked_by, self.locked_at)
                self.zi_candidate_id = zi_candidate_id
            elif self.zi_id != self.zi_candidate_id:
                self.zi_id = self.zi_candidate_id
            create_event(ZoneSMUpdate, db_session=event.db_session,
                     sm_id=self.id_, zone_id=self.id_, name=self.name,
                     publish_zi_id=self.zi_candidate_id,
                     wrap_soa_serial=wrap_soa_serial,
                     candidate_soa_serial=candidate_soa_serial,
                     force_soa_serial_update=force_soa_serial_update)
        return (RCODE_OK, "Zone '%s' - refreshing" % self.name)

    def _do_sg_swap(self, event):
        """
        Swap SGs, and then reconfig refresh a zone by queuing events.
        """
        db_session = event.db_session
        if not self.alt_sg:
            raise ZoneNoAltSg("Zone '%s' - no alt_sg, swap failed." 
                                                        % self.name)
        new_sg = self.alt_sg
        new_alt_sg = self.sg
        self.set_sg(new_sg)
        self._set_alt_sg(new_alt_sg)
        zone_sm_reconfig_schedule(db_session, self, ZoneSMUpdate, 
                randomize=True, publish_zi_id=self.zi_candidate_id)
        return (RCODE_OK, "Zone '%s' - SG reconfig and then refresh" 
                        % self.name)

    def _do_set_alt_sg(self, event):
        """
        Set alt SG.  Needed to lock Zone to update zone_sm row in DB.
        """
        db_session = event.db_session
        alt_sg_name = event.py_parameters['alt_sg_name']
        if alt_sg_name:
            alt_sg = find_sg_byname(db_session, alt_sg_name, raise_exc=False)
            if not alt_sg:
                raise ZoneNoAltSg("Zone '%s' - no alt_sg %s, set failed." 
                                                        % (self.name, sg_name))
            reconf_sg = alt_sg
        else:
            alt_sg = None
            reconf_sg = self.alt_sg
        self._set_alt_sg(alt_sg)
        reconfig_sg(db_session, reconf_sg.id_, reconf_sg.name)
        return (RCODE_OK, "Zone '%s' - alt SG set and SG reconfig queued" 
                        % self.name)

    def _edit(self, event):
        """
        Edit zone configuration.
        """
        db_session = event.db_session
        if (not self.edit_lock):
            return (RCODE_NOCHANGE, "Edit locking turned off for zone '%s'" 
                        % self.name)
        if  (self.lock_state == ZLSTATE_EDIT_LOCK):
            raise ZoneEditLocked(self.name, self.edit_lock_token,
                    self.locked_by, self.locked_at)

        timeout = timedelta(
                        minutes=float(settings['edit_lock_timeout']))
        if timeout: 
            timeout_event = create_event(ZoneSMEditTimeout,
                                db_session=db_session,
                                delay=timeout, sm_id=self.id_, 
                                zone_id=self.id_, name=self.name)
            lock_id = timeout_event.id_
        else:
            lock_id = event.id_
        self.edit_lock_token = lock_id
        self.lock_state = ZLSTATE_EDIT_LOCK
        self.locked_by = event.py_parameters.get('locked_by') 
        self.locked_at = db_time(db_session)
        event.py_results['edit_lock_token'] =  self.edit_lock_token
        return (RCODE_OK, "Locked edit zone '%s' entered - token '%s'" 
                % (self.name, self.edit_lock_token))

    def _edit_locked(self, event):
        """
        Attempt to edit  a zone while edit locked!!

        raise and bomb...
        """
        raise ZoneEditLocked(self.name, self.edit_lock_token, self.locked_by, 
                            self.locked_at)

    def _edit_not_locked(self, event):
        """
        Attempt to update a zone while not edit locked!!

        raise and bomb...
        """
        raise ZoneNotEditLocked(self.name)

    def _edit_exit(self, event):
        """
        Exit edit lock state.  Need value of lock token to exit.
        """
        if not self.edit_lock_token:
            if self.lock_state != ZLSTATE_EDIT_UNLOCK:
                raise ZoneSMLockFailure(
                        "Zone '%s' - lock mechanism in bad state"
                        % self.name)
            return (RCODE_OK, "Zone '%s' - exit edit, zone not locked"
                    % self.name) 
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            raise ZoneEditLocked(self.name, self.edit_lock_token,
                    self.locked_by, self.locked_at)
        # This will cancel any existing timeout events with this
        # edit_lock_token.  If it is a ZoneSMEditEvent, it is the one
        # processed to begin this session.
        cancel_event(self.edit_lock_token, db_session=event.db_session)
        old_lock_state = self.lock_state
        self._reset_edit_lock()
        return (RCODE_OK, "Exiting %s for zone '%s'" % (old_lock_state,
                                                            self.name))
    
    def _update_edit_exit(self, event):
        """
        Clear edit lock in UPDATE state by queuing ZoneSMEditUpdate event
        """
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            raise ZoneEditLocked(self.name, self.edit_lock_token, 
                    self.locked_by, self.locked_at)
        create_event(ZoneSMEditUpdate, db_session=event.db_session,
                     sm_id=self.id_, zone_id=self.id_, name=self.name,
                     publish_zi_id=self.zi_candidate_id,
                     edit_lock_token=event.py_parameters['edit_lock_token'])
        return (RCODE_OK, "Zone '%s' - exiting lock by queuing"
                " ZoneSMEditUpdate" % self.name)

    def _edit_lock_tickle(self, event):
        """
        Tickle edit lock timeout  Need correct value of lock token to execute.
        """
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            self._process_edit_lock_token_mismatch()
        timeout = timedelta(
                        minutes=float(settings['edit_lock_timeout']))
        if not timeout:
            return (RCODE_NOEFFECT, "Edit Lock Timeout disabled")
        reschedule_event(self.edit_lock_token, db_session=event.db_session,
                delay=timeout)
        return (RCODE_OK, "Tickled timeout for zone '%s'" % self.name)

    def _edit_timeout(self, event):
        """
        Timeout edit lock state.  Need value of lock token to do timeout.
        """
        old_lock_state = self.lock_state
        self._reset_edit_lock()
        return (RCODE_OK, "Exiting %s for zone '%s'" % (old_lock_state,
                                            self.name))

    def _edit_saved_no_lock(self, event):
        """
        Unlocked edit saved, puts zi in place, issues a publish event
        """
        db_session = event.db_session
        zi_candidate_id = event.py_parameters['zi_id']
        self.zi_candidate_id = zi_candidate_id
        event = ZoneSMUpdate(sm_id=self.id_, zone_id=self.id_, name=self.name,
                                publish_zi_id=zi_candidate_id)
        # This call does a db_session.commit()
        queue_event(event, db_session=db_session, commit=True,
                    signal_queue_daemon=True)
        return (RCODE_OK, "Zone '%s' - unlocked edit saved,"
                        " ZoneSMUpdate queued" % self.name)

    def _other_edit_saved_no_lock(self, event):
        """
        Unlocked edit saved, puts zi in place, in non-PUBLISHED state
        """
        db_session = event.db_session
        zi_id = event.py_parameters['zi_id']
        self.zi_candidate_id = zi_id
        self.zi_id = zi_id
        return (RCODE_OK, "Zone '%s' - unlocked edit saved" % self.name)


    def _edit_saved_to_update(self, event):
        """
        Lock edit saved, commence update state
        """
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            self._process_edit_lock_token_mismatch()
        # This will cancel any existing timeout events with this
        # edit_lock_token.  If it is a ZoneSMEditEvent, it is the one
        # processed to begin this session.
        cancel_event(self.edit_lock_token, db_session=event.db_session)
        old_state = self.state
        self.state = ZSTATE_UPDATE
        self.zi_candidate_id = event.py_parameters['zi_id']
        create_event(ZoneSMEditUpdate, db_session=event.db_session,
                     sm_id=self.id_, zone_id=self.id_, name=self.name,
                     publish_zi_id=self.zi_candidate_id,
                     edit_lock_token=event.py_parameters['edit_lock_token'])
        return (RCODE_OK, "Exiting  %s for zone '%s' - edit saved, updating" 
                    % (old_state, self.name))

    def _other_edit_saved(self, event):
        """
        Do edit saved for states other than PUBLISHED
        """
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            self._process_edit_lock_token_mismatch()
        # This will cancel any existing timeout events with this
        # edit_lock_token.  If it is a ZoneSMEditEvent, it is the one
        # processed to begin this session.
        cancel_event(self.edit_lock_token, db_session=event.db_session)
        self._reset_edit_lock()
        zi_id = event.py_parameters['zi_id']
        self.zi_candidate_id = zi_id
        self.zi_id = zi_id
        return (RCODE_OK, "Zone '%s' - edit saved, updated" 
                    % self.name)

    def _update_dnssec_preprocess(self):
        """
        Pre update processing for DNSSEC
        """
        dnssec_args = {}
        if self.auto_dnssec and not self._check_dnssec_keys():
            log_error ("Zone '%s' - DNSSEC keys are not present." % self.name)
            return {}
        if not self.auto_dnssec:
            dnssec_args['clear_dnskey'] = True
        elif self.auto_dnssec:
            if self.nsec3:
                dnssec_args['nsec3_seed'] = True
            elif not self.nsec3:
                dnssec_args['clear_nsec3'] = True
        return dnssec_args

    def _update_dnsssec_postprocess(self, db_session, update_info, dnssec_args):
        """
        Post update processing for checking DNSSEC state
        """
        if not update_info:
            # Things did not go as well as we thought...
            return
        if self.auto_dnssec:
            if not dnssec_args:
                # Empty dnssec_args flag no DNSSSEC keys present for zone.
                # This is only needed for enabling DNSSEC
                return
            if not update_info.get('dnskey_flag'):
                zone_sm_dnssec_schedule(db_session, self, 'sign')
                msg = ("Zone '%s' - DNSSEC configured and not DNSSEC signed"
                        % self.name)
                raise DynDNSUpdateRetry(msg)
            if self.nsec3:
                if not update_info.get('nsec3param_flag'):
                    msg = ("Zone '%s' - NSEC3 configured and not converted"
                            % self.name)
                    raise DynDNSUpdateRetry(msg)
            else:
                if update_info.get('nsec3param_flag'):
                    msg = ("Zone '%s' - NSEC3 not configured"
                            " and NSEC3 present" % self.name)
                    raise DynDNSUpdateRetry(msg)
        elif not self.auto_dnssec:
            if (update_info and update_info.get('dnskey_flag')):
                msg = ("Zone '%s' - DNSSEC signed and DNSSEC not configured"                            % self.name)
                raise DynDNSUpdateRetry(msg)


    def _update(self, event, clear_edit_lock=False, 
                        process_inc_updates=False):
        """
        Update Zone on name server, mainly from PUBLISHED state
        """
        db_session = event.db_session
        # Get new zi_id from zi_candidate_id
        zi_id = self.zi_candidate_id
        zi_type = sql_types['ZoneInstance']
        # Get zi, if not found, fail gracefully
        err_string = ''
        try:
            zi = db_session.query(zi_type)\
                    .filter(zi_type.id_ == zi_id).one()
        except NoResultFound as exc:
            err_string = str(exc)
        if err_string:
            raise DynDNSUpdateFailed(err_string)

        # Get SOA twiddling parameters, if any
        candidate_soa_serial = event.py_parameters.get('candidate_soa_serial')
        wrap_soa_serial = event.py_parameters.get('wrap_soa_serial')
        force_soa_serial_update = event.py_parameters.get(
                                                    'force_soa_serial_update')
        do_soa_serial_update = (candidate_soa_serial != None 
                                        or wrap_soa_serial 
                                        or force_soa_serial_update)

        # Add in any incremental updates here
        zi = self._do_incremental_updates(db_session, zi, process_inc_updates)

        # Update Apex Records
        zi.update_apex(db_session)

        # Update Zone TTLs
        zi.update_zone_ttls()
        
        # Preprocessing for DNSSEC goes here
        dnssec_args = self._update_dnssec_preprocess()
        
        # Run update engine
        (rcode, msg, soa_serial, update_info) = update_engine['dyndns']\
                        .update_zone(self.name, zi,
                                db_soa_serial=self.soa_serial,
                                candidate_soa_serial=candidate_soa_serial,
                                force_soa_serial_update=do_soa_serial_update,
                                wrap_serial_next_time=wrap_soa_serial,
                                **dnssec_args)

        # Handle auto reset of Zone SM if DNS server is not configured
        if rcode == RCODE_RESET:
            msg = "reconfiguring ZoneSM as server not configured" 
            log_info(msg)
            return self._retry_reconfig(event, randomize=True)

        # Post processing for DNSSEC goes here.
        # Empty dnssec_args flag no DNSSSEC keys present for zone.
        self._update_dnsssec_postprocess(db_session, update_info, dnssec_args)

        if rcode == RCODE_ERROR:
            raise DynDNSUpdateRetry(msg)
        elif rcode == RCODE_FATAL:
            raise DynDNSUpdateFailed(msg)

        # Update ZI in zone_sm.zi_id and self.soa_serial here.
        # Somehow because of SQL Alchemy, a raise does not revert
        # values in SA instrumented data....
        zi.ptime = db_time(db_session)
        # Don't have to update self.zi as this data is being committed and
        # is finished with as part of this event.  Only processed on event
        # queue.
        self.zi_id = zi.id_
        self.zi_candidate_id = self.zi_id
        self.soa_serial = soa_serial
        self.state = ZSTATE_PUBLISHED
        if clear_edit_lock:
            self._reset_edit_lock()
        return (rcode, msg)

    def _edit_update(self, event):
        """
        Update from a locked edit session, from UPDATE state
        """
        if  (event.py_parameters['edit_lock_token'] != self.edit_lock_token):
            raise ZoneEditLocked(self.name, self.edit_lock_token,
                    self.locked_by, self.locked_at)
        old_state = self.state
        # Rest of code is mostly the same as for _update() above
        try:
            return self._update(event, clear_edit_lock=True, 
                                process_inc_updates=True)
        except DynDNSUpdateFailed:
            # if failure, transition to published, releasing lock
            self.state = ZSTATE_PUBLISHED
            self._reset_edit_lock()
            return (RCODE_NOCHANGE, 
                    "Exiting %s for zone '%s' - update failed"
                    % (old_state, self.name))
    
    # State Table
    _sm_table  = {  ZSTATE_BATCH_CREATE_1: {
                            ZoneSMBatchConfig:   _batch_config,
                            ZoneSMDoReset: _do_reset,
                            ZoneSMDisable: _event_failure,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMDelete: _nuke_start,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_BATCH_CREATE_2: {
                            ZoneSMReconfigCheck: _reconfig_check,
                            ZoneSMDoReset: _do_reset,
                            ZoneSMDisable: _event_failure,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_INIT: {
                            ZoneSMDoConfig: _do_config,
                            ZoneSMDoBatchConfig: _do_batch_config,
                            ZoneSMDoReset: _do_reset,
                            ZoneSMDisable: _event_failure,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMDelete: _nuke_start,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_CREATE: {
                            ZoneSMDoReset: _do_reset,
                            ZoneSMRemoveZoneFiles: _remove_zone_files,
                            ZoneSMEditSaved: _edit_exit,
                            ZoneSMEdit: _edit,
                            ZoneSMEditTimeout: _edit_timeout,
                            ZoneSMEditExit: _edit_exit,
                            ZoneSMEditLockTickle: _edit_lock_tickle,
                            ZoneSMDisable: _disable,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMEditSavedNoLock: _other_edit_saved_no_lock,
                            ZoneSMEditSaved: _other_edit_saved,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMConfig:   _config,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_UNCONFIG: {
                            ZoneSMDoReset: _do_reset,
                            ZoneSMEditSaved: _edit_exit,
                            ZoneSMEdit: _edit,
                            ZoneSMEditTimeout: _edit_timeout,
                            ZoneSMEditExit: _edit_exit,
                            ZoneSMEditLockTickle: _edit_lock_tickle,
                            ZoneSMDisable: _disable,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMEditSavedNoLock: _other_edit_saved_no_lock,
                            ZoneSMEditSaved: _other_edit_saved,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMReconfigUpdate: _reconfig_update,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_DISABLED: {
                            ZoneSMDoReset: _reset_disabled,
                            ZoneSMEditSaved: _edit_exit,
                            ZoneSMEdit: _edit,
                            ZoneSMEditTimeout: _edit_timeout,
                            ZoneSMEditExit: _edit_exit,
                            ZoneSMEditLockTickle: _edit_lock_tickle,
                            ZoneSMEnable: _enable,
                            ZoneSMDisable: _already_disabled,
                            ZoneSMEditSavedNoLock: _other_edit_saved_no_lock,
                            ZoneSMEditSaved: _other_edit_saved,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMRemoveZoneFiles: _remove_zone_files,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_PUBLISHED: {
                            ZoneSMDoReset: _do_reset,
                            ZoneSMUpdate: _update,
                            ZoneSMEditSavedNoLock: _edit_saved_no_lock,
                            ZoneSMEditSaved: _edit_saved_to_update,
                            ZoneSMEdit: _edit,
                            ZoneSMEditTimeout: _edit_timeout,
                            ZoneSMEditExit: _edit_exit,
                            ZoneSMEditLockTickle: _edit_lock_tickle,
                            ZoneSMDisable: _disable,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMDoReconfig: _do_reconfig,
                            ZoneSMDoRefresh: _do_refresh,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_UPDATE:  {   
                        # No EditExit here as this state will only fail
                        # with a significant event code failure
                            ZoneSMDoReset: _do_reset,
                            ZoneSMEditUpdate: _edit_update,
                            ZoneSMEditSaved: _edit_not_locked,
                            ZoneSMEdit: _edit_locked,
                            ZoneSMEditExit: _update_edit_exit,
                            ZoneSMDelete: _delete,
                            ZoneSMNukeStart: _nuke_start,
                            ZoneSMDoReconfig: _do_reconfig,
                            ZoneSMDoRefresh: _do_refresh,
                            ZoneSMDisable: _disable,
                            ZoneSMEnable: _already_enabled,
                            ZoneSMDoSgSwap: _do_sg_swap,
                            ZoneSMDoSetAltSg: _do_set_alt_sg,
                            },
                    ZSTATE_DELETED: {  
                            ZoneSMUndelete: _undelete,
                            ZoneSMRemoveZoneFiles: _remove_zone_files,
                            ZoneSMDoDestroy: _do_destroy,
                                        },
                }
    # RESET state is a copy of CREATE state
    _sm_table[ZSTATE_RESET] = _sm_table[ZSTATE_CREATE]
   
    def _check_dnssec_keys(self):
        key_glob = (settings['master_dnssec_key_dir'] + '/K' 
                        + self.name + '*')
        key_files = glob.glob(key_glob)
        if (len(key_files) <= 0):
            return False
        if not os.path.isfile(key_files[0]):
            return False
        return True

    def write_config(self, include_file, db_session, server_acls, 
            replica_sg=None):
        """
        Fill out master server configuration template 
        """
        if self.is_not_configured():
            # Disabled and deleted zones are NOT in master config file!
            return
        # Exceptions for this caught by an outer try:
        # self._template_names indirection used so that config file settings
        # will take effect.
        do_auto_dnssec = False
        if self.auto_dnssec:
            do_auto_dnssec = self._check_dnssec_keys()
            if not do_auto_dnssec:
                log_error("Zone '%s' - DNSSEC not configured due to no keys"
                            % self.name)
        template_dir = settings['master_template_dir']
        if do_auto_dnssec:
            template_name = (template_dir + '/'
                                + settings[self._template_names[1]])
        else:
            template_name = (template_dir + '/' 
                                + settings[self._template_names[0]])

        template = read_template(template_name)
        # Remove dot at end of zone name as this gives more
        # human literate filenames
        filler_name = self.name[:-1] if self.name.endswith('.') \
                                    else self.name
        sg_server_acls = '%s;' % server_acls[self.sg.name]['acl_name']
        if self.alt_sg:
            sg_server_acls += ' %s;' % server_acls[self.alt_sg.name]['acl_name']
        if replica_sg:
            sg_server_acls += ' %s;' % server_acls[replica_sg.name]['acl_name']
        # Include also-notify directive in string to be written
        # to stop any trouble due to blank also-notify statement, as
        # well as Admin confusion.....
        also_notify = ''
        for server_sm in self.sg.servers:
             # Skip server if it is actually this server
             if server_sm.is_this_server():
                 del server_sm
                 continue
             # include disabled server, as access can be shut off
             # in IPSEC and firewall!
             also_notify += ("%s; "% server_sm.address)
             del server_sm
        if self.alt_sg:
            for server_sm in self.alt_sg.servers:
                 # Skip server if it is actually this server
                 if server_sm.is_this_server():
                     del server_sm
                     continue
                 # include disabled server, as access can be shut off
                 # in IPSEC and firewall!
                 also_notify += ("%s; "% server_sm.address)
                 del server_sm
        if replica_sg:
            for server_sm in replica_sg.servers:
                 # Skip server if it is actually this server
                 if server_sm.is_this_server():
                     del server_sm
                     continue
                 # include disabled servers, as access can be shut off
                 # in IPSEC and firewall!
                 also_notify += ("%s; "% server_sm.address)
                 del server_sm
        if also_notify.endswith(' '):
            also_notify = also_notify[:-1]
        filler = { 'name': filler_name, 
                'master_dyndns_dir': settings['master_dyndns_dir'],
                'sg_server_acls': sg_server_acls,
                'also_notify': also_notify}
        section = template % filler
        include_file.write(section)
    

def get_default_zone_data(db_session):
    """
    Return default zone data from zone_cfg table
    """
    zone_sm_data = {}
    fields = ['use_apex_ns', 'auto_dnssec', 'edit_lock', 'nsec3', 
                'inc_updates']
    for field in fields:
        value = zone_cfg.get_row(db_session, field)
        if value in ('true', 'True', 'TRUE'):
            zone_sm_data[field] = True
        elif value in ('false', 'False', 'FALSE'):
            zone_sm_data[field] = False
        elif value is None:
            zone_sm_data[field] = False
        else:
            raise ZoneCfgItemValueError(field, value)
    return zone_sm_data

def new_zone(db_session, type_, sectag=None, sg_name=None, reference=None,
        **kwargs_init):
    """
    Create a new zone of type_, add it to the db_session, persist it,
    and return object.
    """
    zone_sm_data = get_default_zone_data(db_session)
    for arg in kwargs_init:
        if kwargs_init[arg] is None:
            kwargs_init[arg] = zone_sm_data.get(arg)
    # Check that SG exists
    if not sg_name:
        sg_name = zone_cfg.get_row_exc(db_session, 'default_sg')
    if not sg_name in list_all_sgs(db_session):
        raise NoSgFound(sg_name)
    zone_sm = type_(**kwargs_init)
    zone_sm.state = ZSTATE_INIT
    db_session.add(zone_sm)
    ZoneSecTag = sql_types['ZoneSecTag']
    if sectag and sectag != ZoneSecTag(settings['admin_sectag']):
        # Need a new sectag instance to go with this zone 
        if isinstance(sectag, str):
            new_sectag = ZoneSecTag(sectag)
        else:
            new_sectag = ZoneSecTag(sectag.sectag)
        zone_sm.add_sectag(db_session, new_sectag)
    sg = find_sg_byname(db_session, sg_name, raise_exc=True)
    zone_sm.set_sg(sg)
    # Add reference for zone
    if not reference:
        reference = zone_cfg.get_row_exc(db_session, 'default_ref')
    ref_obj = new_reference(db_session, reference, return_existing=True)
    ref_obj.set_zone(zone_sm)
    db_session.flush()
    return zone_sm

def del_zone(db_session, zone):
    """
    Delete the given zone
    """
    # Delete it from the DB
    db_session.delete(zone)
    db_session.commit()
    # Delete the object
    del(zone)

def exec_zonesm(zone_sm, sync_event_type, exception_type=ZoneSmFailure,
                **event_kwargs):
    """
    Execute a synchronous event of the zone state machine
    """
    if not issubclass(sync_event_type, SMSyncEvent):
        raise TypeError("'%s' is not a Synchonous Event." % sync_event_type)

    event = sync_event_type(sm_id=zone_sm.id_,
                                    zone_id=zone_sm.id_,
                                    name=zone_sm.name,
                                    **event_kwargs)
    results = event.execute()
    if results['state'] != ESTATE_SUCCESS:
        if isinstance(event, ZoneSMEdit):
            results['locked_by'] = zone_sm.locked_by
            results['locked_at'] = zone_sm.locked_at
        # By std Python convention exceptions don't have default value
        # arguments. Do the following to take care of 2 or 3 argument
        # variants for the exception.
        zi_id = event_kwargs.get('zi_id')
        if zi_id:
            raise exception_type(zone_sm.name, results['message'], results,
                                zi_id)
        else:
            raise exception_type(zone_sm.name, results['message'], results)
    return results

# SQL Alchemy hooks
def init_zone_sm_table():
    table = Table('sm_zone', sql_data['metadata'],
                        autoload=True, 
                        autoload_with=sql_data['db_engine'])
    sql_data['tables'][ZoneSM] = table

def init_zone_sm_mappers():
    table = sql_data['tables'][ZoneSM]
    sql_data['mappers'][ZoneSM] = mapper(ZoneSM, table,
            polymorphic_on=table.c.zone_type, 
            polymorphic_identity=ZoneSM.__name__,
            properties=mapper_properties(table, ZoneSM))
    sql_data['zone_sm_type_list'].append(ZoneSM.__name__)
    # Map all the zone_sm subclasses
    for class_ in sql_data['zone_sm_subclasses']:
        class_.sa_map_subclass()

sql_data['init_list'].append({'table': init_zone_sm_table,
                            'mapper': init_zone_sm_mappers})

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
Configuration State Machine

There is some verbose programming in here due to similar sections, but it is
better to lay everything out so that you can see whats happening.
"""

from tempfile import mkstemp
import io
import os
import grp
import pwd
import socket
from os.path import basename
from datetime import timedelta
from random import random
from subprocess import check_call
from subprocess import CalledProcessError

from sqlalchemy.sql import or_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm import relationship

from magcode.core.utility import get_numeric_setting
from magcode.core.utility import get_configured_addresses
from magcode.core.database import *
from magcode.core.database.state_machine import StateMachine
from magcode.core.database.state_machine import smregister
from magcode.core.database.state_machine import SMEvent
from magcode.core.database.state_machine import SMSyncEvent
from magcode.core.database.state_machine import StateMachineError
from magcode.core.database.state_machine import StateMachineFatalError
from magcode.core.database.event import eventregister
from magcode.core.database.event import synceventregister
from magcode.core.database.event import create_event
from magcode.core.database.event import ESTATE_SUCCESS
from dms.globals_ import MASTER_SERVER_ACL_TEMPLATE
from dms.template_cache import read_template
from dms.template_cache import clear_template_cache
from dms.exceptions import ReplicaSgExists


# Some constants
MSTATE_HOLD = "HOLD"
MSTATE_READY = "READY"

HOLD_SG_NONE = 0
HOLD_SG_MASTER = -1
HOLD_SG_ALL = -2

# Configuration State Machine Exceptions
class MasterConfigFileError(StateMachineFatalError):
    """
    Can not write configuration file, or cannot access a master template file,
    or there was a template key error.
    """
class ServerConfigFileError(StateMachineFatalError):
    """
    Can not write configuration file, or cannot access a server template file,
    or there was a template key error.
    """
class CantContactMasterServer(StateMachineError):
    """
    rndc operation, can't contact master dns server
    """
class CantFindSg(StateMachineFatalError):
    """
    rndc operation, can't contact master dns server
    """
class RndcFatalError(StateMachineFatalError):
    """
    rndc operation, unrecognised exit code.
    """
@eventregister
class MasterSMLoadKeys(SMEvent):
    """
    rndc operation, Master Server only, DNSSEC loadkeys
    """
# Commenting out as duplicate declaration casuing SAWarnings.  One below
# is the one being actually used in state machines....
#@eventregister
#class MasterSMSignZone(SMSyncEvent):
#    """
#    rndc operation, Master Server only, DNSSEC sign zone
#
#    Can either be synchronous or scheduled.
#    """
@eventregister
class MasterSMSignZone(SMEvent):
    """
    rndc operation, Master Server only, DNSSEC sign zone
    """
@eventregister
class MasterSMMasterReconfig(SMEvent):
    """
    Configuration update, Master Server only.

    Useful for DNSSEC zone transitions
    """
@eventregister
class MasterSMPartialReconfig(SMEvent):
    """
    Configuration update, Master and one Server Group
    """
@eventregister
class MasterSMAllReconfig(SMEvent):
    """
    Configuration update, Master and All Server Groups
    """
@eventregister
class MasterSMHoldTimeout(SMEvent):
    """
    Hold  time out event
    """
@eventregister
class MasterSMReset(SMEvent):
    """
    Reset Config SM and queue a MasterSMAllReconfig
    """
@synceventregister
class MasterSMBatchHold(SMSyncEvent):
    """
    Hold  time out event
    """

@smregister
class MasterSM(StateMachine):
    """
    Configuration State Machine
    """
    _table = 'sm_master'
    _sm_events = (MasterSMLoadKeys, MasterSMSignZone, MasterSMMasterReconfig,
            MasterSMPartialReconfig, MasterSMAllReconfig, MasterSMHoldTimeout,
            MasterSMBatchHold,MasterSMReset)
    
    @classmethod
    def _mapper_properties(class_):
        ServerGroup = sql_types['ServerGroup']
        ServerSM = sql_types['ServerSM']
        return {'replica_sg': relationship(ServerGroup, backref='master_sm'),
                'master_server': relationship(ServerSM, 
                                        backref='master_sm')}

    def _init(self):
        self.hold_sg = HOLD_SG_NONE
        self.hold_sg_name = None
        self.hold_start = None
        self.hold_stop = None
        self.state = MSTATE_READY
    
    def __init__(self):
        self._init()
        # These should only be initialised on initial MasterSM creation
        self.replica_sg_id = None
        self.master_server_id = None
        self.master_hostname = None

    def write_named_conf_includes(self, db_session, op_exc):
        """
        Write the bits of named configuration.

        Seperated so that it is callable from recovery script
        """
        def open_tmp_file(prefix):
            (fd, tmp_filename) = mkstemp(
                        dir=tmp_dir,
                        prefix=prefix)
            include_file = io.open(fd, mode='wt')
            return (include_file, tmp_filename)

        def clean_up_rename(include_file, tmp_filename, config_file_name):
                include_file.close()
                # Rename tmp file into place so that replacement is atomic
                run_as_user = settings['run_as_user']
                try:
                    run_as_user_pwd = pwd.getpwnam(run_as_user)
                except KeyError as exc:
                    msg = ("Could not find user '%s' in passwd database - %s"
                                % (run_as_user, str(exc)))
                    raise op_exc(msg)
                uid = run_as_user_pwd.pw_uid 
                gid = run_as_user_pwd.pw_gid 
                os.chown(tmp_filename, uid, gid)
                os.chmod(tmp_filename, int(settings['zone_file_mode'],8))
                # Rename tmp file into place so that replacement is atomic
                os.chmod(tmp_filename, int(settings['config_file_mode'],8))
                os.rename(tmp_filename, config_file_name)

        db_query_slice = get_numeric_setting('db_query_slice', int)
        # Clear template cache.  This forces a re read of all templates
        clear_template_cache()
        # Rewrite include and global server ACL file if required.
        # Trap file IO errors as event queue can't handle them.
        try:
            tmp_dir = settings['master_config_dir']
            # master server ACL file
            acl_prefix = ('.' 
                    + basename(settings['master_server_acl_file']) + '-')
            acl_file, tmp_filename = open_tmp_file(acl_prefix)

            # Create Master ACL file 
            server_acl_template = read_template(
                            settings['master_template_dir'] + '/' 
                            + settings[MASTER_SERVER_ACL_TEMPLATE])
            server_acls = {}
            ServerGroup = sql_types['ServerGroup']
            query = db_session.query(ServerGroup)
            for sg in query:
                # Each SG gets its own ACL to prevent cross  SG
                # domain discovery if a server is compromised.
                sg_acl_name = sg.name + settings['acl_name_extension']
                server_acls[sg.name] = {'acl_name': sg_acl_name, 
                                        'servers': ''}
                for server_sm in sg.servers:
                    # include disabled server, as access can be shut off
                    # in IPSEC and firewall!
                    server_acls[sg.name]['servers'] += ("%s;\n" 
                                                    % server_sm.address)
                    del server_sm
                if not server_acls[sg.name]['servers']:
                    server_acls[sg.name]['servers'] = 'none;\n'
                # Stop memory leaks
                del sg
            for sg_name in server_acls:
                acl_file.write(server_acl_template % server_acls[sg_name])
            clean_up_rename(acl_file, tmp_filename, 
                    settings['master_server_acl_file'])

            # include file
            include_prefix = ('.' 
                    + basename(settings['master_include_file']) + '-')
            include_file, tmp_filename = open_tmp_file(include_prefix)
            # Get list of zones from zone_sm, and write out each 
            # config file section
            ZoneSM = sql_types['ZoneSM']
            query = ZoneSM.query_is_configured(
                        db_session.query(ZoneSM)).yield_per(db_query_slice)
            for zone_sm in query:
                zone_sm.write_config(include_file, db_session, server_acls, 
                        self.replica_sg)
                del zone_sm
            clean_up_rename(include_file, tmp_filename, 
                    settings['master_include_file'])
        except (IOError, OSError) as exc: 
            msg = ( "Could not access/write file '%s' - %s." 
                            % (exc.filename, exc.strerror))
            raise op_exc(msg)
        except KeyError as exc:
            msg = ("Invalid template key in template dir %s - %s"
                    % (settings['master_template_dir'], str(exc)))
            raise op_exc(msg)
        finally:
            # clean up if possible
            try:
                os.unlink(tmp_filename)
            except:
                pass

    def _master_rndc(self, event, *rndc_args):
        """
        Write out include file for Master server

        This is done as part of the Master Server Config SM unlike the server 
        servers, where it is part of the SG code, and is exceuted by the 
        MasterSM.
        """
        if (rndc_args[0] == 'reconfig' 
                or (rndc_args[0] == 'reload' and len(rndc_args) == 1)):
            db_session = event.db_session
            self.write_named_conf_includes(db_session, MasterConfigFileError)

        # Run rndc 
        try:
            cmdline = [settings['rndc_path']]
            cmdline.extend(rndc_args)
            output = check_call(cmdline)
        except CalledProcessError as exc:
            if exc.returncode == 1:
                msg = (
                    "%s could not contact master DNS server, return code '%s'" 
                   % (settings['rndc_path'], exc.returncode))
                raise CantContactMasterServer(msg)
            else:
                msg = str(exc)
                raise RndcFatalError(msg)

        return (RCODE_OK, "'%s' on master DNS server completed" 
                                    % ' '.join(cmdline)) 

    def _rndc_dnssec(self, event, operation):
        """
        rndc loadkeys/sign zone only
        """
        db_session = event.db_session
        sm_id = event.py_parameters['sm_id']
        zone_name = event.py_parameters['zone_name']
        rndc_args = [operation, zone_name]
        return self._master_rndc(event, *rndc_args)

    def _rndc_load_keys(self, event):
        """
        rndc loadkeys zone
        """
        return self._rndc_dnssec(event, 'loadkeys')

    def _rndc_sign_zone(self, event):
        """
        rndc loadkeys zone
        """
        return self._rndc_dnssec(event, 'sign')

    def _hold_enter(self, db_session, all_reconfig=False):
        """
        Enter hold state

        Set fields as needed.
        """
        if self.state == MSTATE_HOLD:
            return
        self.hold_sg = HOLD_SG_ALL if all_reconfig else HOLD_SG_NONE
        self.state = MSTATE_HOLD
        self.hold_start = db_time(db_session)
        delay=timedelta(minutes=float(settings['master_hold_timeout']))
        self.hold_stop = self.hold_start + delay
        # Queue hold timeout
        create_event(MasterSMHoldTimeout, db_session=db_session,
                sm_id=self.id_, master_id=self.id_, delay=delay)

    def _reset(self, event):
        """
        Reset mastersm
        """
        self._init()
        # Queue all reconfig
        create_event(MasterSMAllReconfig, db_session=event.db_session,
                sm_id=self.id_, master_id=self.id_)
        return (RCODE_OK, "MasterSM - SM reinitialised and MasterSMAllReconfig")

    def _batch_hold(self, event):
        """
        Process a batch hold start event

        Made to be used from both states
        """
        self._hold_enter(event.db_session, all_reconfig=True)
        return (RCODE_OK, "MasterSM - CONFIG_HOLD via MasterSMBatchHold event")

    def _ready_master_reconfig(self, event):
        """
        Process a master only reconfig
        """
        # Update server address info
        recalc_machine_dns_server_info(event.db_session)
        # Update master server configuration
        rcode, msg = self._master_rndc(event, 'reconfig')
        if rcode != RCODE_OK:
            return (rcode, msg)
        self._hold_enter(event.db_session)
        return (RCODE_OK, "MasterSM: master reconfig only done")

    def _ready_partial_reconfig(self, event):
        """
        Process a partial reconfig event
        """
        # Update server address info
        recalc_machine_dns_server_info(event.db_session)
        # Update master server configuration
        rcode, msg = self._master_rndc(event, 'reconfig')
        if rcode != RCODE_OK:
            return (rcode, msg)

        # Issue reconfig event to SG
        db_session = event.db_session
        ServerGroup = sql_types['ServerGroup']
        # sg_id found in zone_sm and sent here as event parameter
        sg_id = event.py_parameters['sg_id']
        sg_name = event.py_parameters['sg_name']
        try:
            sg = db_session.query(ServerGroup)\
                    .filter(ServerGroup.id_ == sg_id).one()
        except NoResultFound as exc:
            msg = ("MasterSM: can't find SG %s by id '%s'" 
                % (sg_name, sg_id))
            raise CantFindSg(msg)
        
        self.hold_sg_name = sg.name
        
        delay_time = timedelta(
                seconds=float(settings['master_rndc_settle_delay']))
        # Replica SG reconfigure
        replica_sg = self.replica_sg
        if (replica_sg and replica_sg is not sg):
            try:
                replica_sg.write_config(db_session, ServerConfigFileError)
            except ServerConfigFileError as exc:
                log_error(str(exc))
            else:
                for server_sm in replica_sg.servers:
                    if server_sm.is_disabled():
                        continue
                    create_event(sql_events['ServerSMConfigChange'],
                                db_session=event.db_session,
                                sm_id=server_sm.id_, server_id=server_sm.id_,
                                delay=delay_time,
                                server_name=server_sm.name)

        # SG reconfigure
        try:
            sg.write_config(db_session, ServerConfigFileError)
        except ServerConfigFileError as exc:
            log_error(str(exc))
        else:
            # Reconfigure servers in this group
            for server_sm in sg.servers:
                if server_sm.is_disabled():
                    continue
                create_event(sql_events['ServerSMConfigChange'],
                            db_session=event.db_session,
                            sm_id=server_sm.id_, server_id=server_sm.id_,
                            delay=delay_time,
                            server_name=server_sm.name)

        self._hold_enter(db_session)
        return (RCODE_OK, "MasterSM: SG '%s' - master named reconfig done and SG reconfig queued"
                            % self.hold_sg_name)

    def _ready_all_reconfig(self, event):
        """
        Process an all reconfig
        """
        # Update server address info
        recalc_machine_dns_server_info(event.db_session)
        # Update master server configuration
        rcode, msg = self._master_rndc(event, 'reconfig')
        if rcode != RCODE_OK:
            return (rcode, msg)
        
        # Issue all reconfig event to all servers
        delay_time = timedelta(
                seconds=float(settings['master_rndc_settle_delay']))
        db_session = event.db_session
        ServerGroup = sql_types['ServerGroup']
        for sg in db_session.query(ServerGroup):
            try:
                sg.write_config(db_session, ServerConfigFileError)
            except ServerConfigFileError as exc:
                log_error(str(exc))
                continue
            for server_sm in sg.servers:
                if server_sm.is_disabled():
                    continue
                create_event(sql_events['ServerSMConfigChange'],
                            db_session=event.db_session,
                            sm_id=server_sm.id_, server_id=server_sm.id_,
                            delay=delay_time,
                            server_name=server_sm.name)
        
        self._hold_enter(db_session)
        return (RCODE_OK, 
                "Master named reconfig done and reconfig queued for all SGs")
        
    def _hold_master_reconfig(self, event):
        """
        Process a master reconfig event during hold

        Sets master_sm hold level as apropriate
        """
        db_session = event.db_session
        sm_id = event.py_parameters['sm_id']

        if self.hold_sg == HOLD_SG_NONE:
            self.hold_sg = HOLD_SG_MASTER
            self.hold_sg_name = None
        return (RCODE_OK, 
                "MasterSM - hold event %s, hold_sg now '%s'"
                    % (MasterSMMasterReconfig.__name__, 
                        self._display_hold_sg()))

    def _hold_partial_reconfig(self, event):
        """
        Process a reconfig event during hold

        Sets master_sm hold level as apropriate
        """
        db_session = event.db_session
        sm_id = event.py_parameters['sm_id']
        sg_id = event.py_parameters['sg_id']
        sg_name = event.py_parameters['sg_name']

        if self.hold_sg in (HOLD_SG_NONE, HOLD_SG_MASTER):
            self.hold_sg = sg_id
            self.hold_sg_name = sg_name
        elif self.hold_sg == HOLD_SG_ALL:
            pass
        elif self.hold_sg != sg_id:
            self.hold_sg = HOLD_SG_ALL
            self.hold_sg_name = None

        return (RCODE_OK, 
            "MasterSM - hold event %s, hold_sg now '%s',"
                " hold_sg_name '%s'"
                    % (MasterSMPartialReconfig.__name__, 
                        self._display_hold_sg(), self.hold_sg_name))

    def _hold_all_reconfig(self, event):
        """
        Process an all reconfig event during hold

        Sets master_sm hold_sg to HOLD_SG_ALL
        """
        db_session = event.db_session
        sm_id = event.py_parameters['sm_id']

        # OK, its eveything!
        self.hold_sg = HOLD_SG_ALL
        self.hold_sg_name = None

        return (RCODE_OK, 
                "MasterSM -  hold event %s, hold_sg now '%s'"
                    % (MasterSMAllReconfig.__name__, self._display_hold_sg()))

    def _hold_time_out(self, event):
        """
        Process a hold time out.

        This the event runs the associated SM backend routine depending on 
        value of self.hold_sg
       """
        db_session = event.db_session
        sm_id = event.py_parameters['sm_id']
        old_hold_sg = self.hold_sg
        old_hold_sg_name = self.hold_sg_name
        # Reset All SM fields
        self._init()
        if old_hold_sg == HOLD_SG_ALL:
            create_event(MasterSMAllReconfig, 
                    sm_id = self.id_, master_id = self.id_)
            return(RCODE_OK, 
                    "MasterSM - %s, %s created and queued"
                    % (MasterSMHoldTimeout.__name__, 
                        MasterSMAllReconfig.__name__))
        if old_hold_sg == HOLD_SG_MASTER:
            create_event(MasterSMMasterReconfig, 
                    sm_id = self.id_, master_id = self.id_)
            return(RCODE_OK,
                "MasterSM - %s, %s created and queued"
                % (MasterSMHoldTimeout.__name__, 
                    MasterSMMasterReconfig.__name__))
        elif old_hold_sg:
            create_event(MasterSMPartialReconfig, 
                    sm_id = self.id_, master_id = self.id_,
                    sg_id = old_hold_sg, sg_name = old_hold_sg_name)
            return(RCODE_OK,
        "MasterSM - %s, %s for SG %s(%s) created and queued"
            % (MasterSMHoldTimeout.__name__, 
                MasterSMPartialReconfig.__name__, 
                old_hold_sg_name, self._display_hold_sg(old_hold_sg)))
                
        return(RCODE_NOCHANGE, "MasterSM - no reconfigure event during hold")

    _sm_table = { MSTATE_READY: { 
                        MasterSMMasterReconfig: _ready_master_reconfig,
                        MasterSMPartialReconfig: _ready_partial_reconfig,
                        MasterSMAllReconfig: _ready_all_reconfig,
                        MasterSMBatchHold: _batch_hold,
                        MasterSMLoadKeys: _rndc_load_keys,
                        MasterSMSignZone: _rndc_sign_zone,
                        MasterSMReset: _reset,
                        },
                  MSTATE_HOLD: {
                        MasterSMHoldTimeout: _hold_time_out,
                        MasterSMMasterReconfig: _hold_master_reconfig,
                        MasterSMPartialReconfig: _hold_partial_reconfig,
                        MasterSMAllReconfig: _hold_all_reconfig,
                        MasterSMBatchHold: _batch_hold,
                        MasterSMLoadKeys: _rndc_load_keys,
                        MasterSMSignZone: _rndc_sign_zone,
                        MasterSMReset: _reset,
                        },
                  }

    def _display_hold_sg(self, hold_sg=None):
        """
        Get display value for hold_sg
        """
        if not hold_sg:
            hold_sg = self.hold_sg
        if hold_sg == HOLD_SG_ALL:
            display = 'HOLD_SG_ALL'
        elif hold_sg == HOLD_SG_NONE:
            display = 'HOLD_SG_NONE'
        elif hold_sg == HOLD_SG_MASTER:
            display = 'HOLD_SG_MASTER'
        else:
            display = '%s' % hold_sg
        return display

    def to_engine_brief(self, time_format=None):
        """
        Brief dict of master_sm fields
        """
        return {'master_id': self.id_, 'state': self.state}

    def to_engine(self, time_format=None):
        """
        Dict of master_sm fields
        """
        hold_sg = self._display_hold_sg()
        if not time_format:
            hold_start = (self.hold_start.isoformat(sep=' ')
                            if self.hold_start else None)
            hold_stop = (self.hold_stop.isoformat(sep=' ')
                            if self.hold_stop else None)
        else:
            hold_start = (self.hold_start.strftime(time_format)
                            if self.hold_start else None)
            hold_stop = (self.hold_stop.strftime(time_format)
                            if self.hold_stop else None)
        return {'master_id': self.id_, 'state': self.state, 
                'hold_start': hold_start, 'hold_stop':hold_stop, 
                'hold_sg': hold_sg, 'hold_sg_name': self.hold_sg_name,
                'master_server_id': self.master_server_id,
                'master_server': self.master_server.name if self.master_server
                                    else self.master_hostname,
                'replica_sg_id': self.replica_sg_id, 
                'replica_sg_name': self.replica_sg.name if self.replica_sg 
                                    else None }

def get_master_sm(db_session):
    """
    get master_sm from database, create it if not there
    """
    try:
        master_sm = db_session.query(MasterSM).one()
    except MultipleResultsFound as exc:
        # Blow up REAL BIG!
        log_critical("More than one MasterSM found in database, giving up")
        systemd_exit(os.EX_SOFTWARE, SDEX_GENERIC)
    except NoResultFound:
        master_sm = MasterSM()
        db_session.add(master_sm)
        db_session.flush()

    return master_sm

def batch_hold(db_session):
    """
    Start a batch hold zone creation state
    """
    master_sm = get_master_sm(db_session)
    batch_hold_event = MasterSMBatchHold()
    results = batch_hold_event.execute()
    if results['state'] != ESTATE_SUCCESS:
        raise ConfigBatchHoldFailed()

def zone_sm_reconfig_schedule(db_session, zone_sm, zone_sm_event=None,
                            randomize=False, master_reconfig=False, **kwargs):
    """
    Schedule MasterSM zone creation/update events

    Zone SM helper function
    """
    master_sm = get_master_sm(db_session)
    # According to sampling theorem, twice tick rate, add 1 to account for
    # safety
    coalesce_time = timedelta(seconds=3*float(settings['sleep_time']))
    # Make delay_secs 2 * coalesce time
    delay_secs = 6*float(settings['sleep_time'])
    if randomize:
        delay_secs += 60*float(settings['master_hold_timeout']) * random()
    delay_time = timedelta(seconds=delay_secs)
    sg_id = zone_sm.sg.id_
    # Queue config event
    if master_reconfig:
        if (master_sm.state != MSTATE_HOLD
            or (master_sm.state == MSTATE_HOLD
                and master_sm.hold_sg == HOLD_SG_NONE)):
            create_event(MasterSMMasterReconfig, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_)
    # Only create MasterSMPartialEvents when needed, as they clog the 
    # event queue
    elif (master_sm.state != MSTATE_HOLD
            or (master_sm.state == MSTATE_HOLD 
                and (master_sm.hold_sg != sg_id 
                    and master_sm.hold_sg != HOLD_SG_ALL))):
        create_event(MasterSMPartialReconfig, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_,
                        sg_id=sg_id, sg_name=zone_sm.sg.name)
    # Queue zone_sm event
    if not zone_sm_event:
        return
    if master_sm.state == MSTATE_READY:
        create_event(zone_sm_event, db_session=db_session,
                        sm_id=zone_sm.id_, zone_id=zone_sm.id_,
                        name=zone_sm.name,
                        delay=delay_time, coalesce_period=coalesce_time,
                        **kwargs)
        return
    elif master_sm.state == MSTATE_HOLD:
        schedule_time = master_sm.hold_stop + delay_time
        create_event(zone_sm_event, db_session=db_session,
                        time=schedule_time, coalesce_period=coalesce_time,
                        sm_id=zone_sm.id_, zone_id=zone_sm.id_,
                        name=zone_sm.name, **kwargs)
        return
    else:
        log_critical('MasterSM - unrecognized state, exiting')
        systemd_exit(os.EX_SOFTWARE, SDEX_GENERIC)
    return

def zone_sm_dnssec_schedule(db_session, zone_sm, operation):
    """
    Schedule a DNSSEC rndc sign/loadkeys operation for a zone_sm
    """
    master_sm = get_master_sm(db_session)
    if operation == 'loadkeys':
        create_event(MasterSMLoadKeys, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_,
                        zone_name=zone_sm.name)
    elif operation in ('sign', 'signzone'):
        create_event(MasterSMSignZone, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_,
                        zone_name=zone_sm.name)
    else:
        log_error("MasterSM - zone '%s', invalid dnssec operation"
                % zone_sm.name)

def show_master_sm(db_session, time_format=None):
    """
    Return a dict consisting of the MasterSM
    """
    master_sm = get_master_sm(db_session)
    return master_sm.to_engine(time_format)

def reset_master_sm(db_session):
    """
    Reset the Configuration state machine
    """
    master_sm = get_master_sm(db_session)
    create_event(MasterSMReset, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_)

def reconfig_all(db_session):
    """
    Reconfigure all DNS servers - helper
    """
    master_sm = get_master_sm(db_session)
    create_event(MasterSMAllReconfig, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_)

def reconfig_sg(db_session, sg_id, sg_name):
    """
    Reconfigure An SGs DNS servers - helper
    """
    master_sm = get_master_sm(db_session)
    create_event(MasterSMPartialReconfig, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_,
                        sg_id=sg_id, sg_name=sg_name)

def reconfig_master(db_session):
    """
    Reconfigure Master DNS server
    """
    master_sm = get_master_sm(db_session)
    create_event(MasterSMMasterReconfig, db_session=db_session,
                        sm_id=master_sm.id_, master_id=master_sm.id_)

def set_mastersm_replica_sg(db_session, sg):
    """
    Set the replica SG
    """
    master_sm = get_master_sm(db_session)
    if hasattr(master_sm, 'replica_sg') and master_sm.replica_sg and sg:
        raise ReplicaSgExists(sg.name, master_sm.replica_sg.name)
    master_sm.replica_sg = sg
    # This is being done straight after this call....
    # db_session.flush()

def get_mastersm_replica_sg(db_session):
    """
    Get the replica SG
    """
    master_sm = get_master_sm(db_session)
    return master_sm.replica_sg

def get_mastersm_master_server(db_session):
    """
    Get the master server setting, if it exists
    """
    if hasattr(self, 'master_server') and self.master_server:
        return master_server
    return None

def recalc_machine_dns_server_info(db_session, ifconfig_exc=False):
    """
    Recalculate DNS server connection information for this machine
    """
    # Get machines configurede addresses via 'ip addr' (Linux) 
    # or 'ifconfig -a' (FreeBSD, *BSD?)
    try:
        configured_addresses = get_configured_addresses()
    except CalledProcessError as exc:
        if ifconfig_exc:
            raise(exc)
        log_error(str(exc))
        return
    # Traverse server_groups table and add all connectable master_address and 
    # master_alt_address to this_servers_addresses
    this_servers_addresses = []
    ServerGroup = sql_types['ServerGroup']
    for sg in db_session.query(ServerGroup):
        for address in (sg.master_address, sg.master_alt_address):
            if not address:
                continue
            if address in configured_addresses:
                this_servers_addresses.append(address)
    
    # Calculate master_dns_server
    master_sm = get_master_sm(db_session)
    replica_sg = master_sm.replica_sg
    master_address = None
    master_server = None
    if replica_sg:
        if replica_sg.master_address:
            if replica_sg.master_address in this_servers_addresses:
                master_address = replica_sg.master_address
        if replica_sg.master_alt_address:
            if replica_sg.master_alt_address in this_servers_addresses:
                master_address = replica_sg.master_alt_address
    # Prefer master_address for settings['master_dns_server']
    if master_address:
        settings['master_dns_server'] = master_address
        # Recalculate master server
        for server_sm in replica_sg.servers:
            if server_sm.address == master_address:
                master_server = server_sm
    master_sm.master_server = master_server
    master_sm.master_hostname = socket.gethostname()

    # sort | uniq all the addresses to remove any literal duplicates
    this_servers_addresses.append(settings['master_dns_server'])
    this_servers_addresses = list(set(sorted(this_servers_addresses)))
    settings['this_servers_addresses'] = this_servers_addresses



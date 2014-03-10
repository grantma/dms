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
Server State Machines
"""


import socket
import errno
from random import random
from datetime import timedelta
from subprocess import check_call
from subprocess import check_output
from subprocess import CalledProcessError
from subprocess import STDOUT

import dns.name
import dns.rdatatype
import dns.rdataclass
import dns.message
import dns.exception
import dns.query
import dns.flags
import dns.rrset
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

from magcode.core.database import *
from magcode.core.database.state_machine import StateMachine
from magcode.core.database.state_machine import smregister
from magcode.core.database.state_machine import SMEvent
from magcode.core.database.state_machine import SMSyncEvent
from magcode.core.database.state_machine import StateMachineError
from magcode.core.database.state_machine import StateMachineFatalError
from magcode.core.database.event import eventregister
from magcode.core.database.event import synceventregister
from magcode.core.database.event import find_events
from magcode.core.database.event import ESTATE_SUCCESS
from magcode.core.database.event import create_event
from dms.database import zone_cfg
from dms.database.sg_utility import list_all_sgs
from dms.database.sg_utility import find_sg_byname
from dms.exceptions import ServerExists
from dms.exceptions import NoServerFound
from dms.exceptions import NoServerFoundByAddress
from dms.exceptions import ServerAddressExists
from dms.exceptions import ServerNotDisabled
from dms.exceptions import NoSgFound
from dms.exceptions import ServerSmFailure
from dms.dns import RRTYPE_SOA


# Some constants
SSTATE_CONFIG = "CONFIG"
SSTATE_OK = "OK"
SSTATE_RETRY = "RETRY"
SSTATE_BROKEN = "BROKEN"
SSTATE_DISABLED = "DISABLED"

SSTYPE_BIND9 = 'bind9'
SSTYPE_NSD3 = 'nsd3'
server_types = [SSTYPE_BIND9, SSTYPE_NSD3]

class CantRsyncServer(StateMachineError):
    """
    Rsync to the server failed.
    """
class CantRsyncDnssecKeysDrServer(CantRsyncServer):
    """
    Rsync of DNSSEC keys to DR replica server failed
    """
class CantRndcServer(StateMachineError):
    """
    Rndc to the server failed.
    """
class CantSoaQueryServer(StateMachineError):
    """
    Cant SOA query Server - retry
    """
class BrokenServer(CantSoaQueryServer):
    """
    Broken action - DNS server non functional. Keep retrying.
    """
class ServerAlreadyDisabled(StateMachineFatalError):
    """
    Server already disabled.
    """
class ServerAlreadyEnabled(StateMachineFatalError):
    """
    Server already enabled.
    """
class ServerEnableFailure(StateMachineFatalError):
    """
    Server already enabled.
    """

# Server State Machine Events
@synceventregister
class ServerSMEnable(SMSyncEvent):
    """
    Enable Server
    """
    pass

@synceventregister
class ServerSMDisable(SMSyncEvent):
    """
    Disable Server
    """
@synceventregister
class ServerSMReset(SMSyncEvent):
    """
    Reset Server
    """

@eventregister
class ServerSMConfigure(SMEvent):
    """
    Server configured
    """
    pass

@eventregister
class ServerSMConfigChange(SMEvent):
    """
    Configuration change for configured server
    """

@eventregister
class ServerSMCheckServer(SMEvent):
    """
    Check a configured server to check that it is running
    """

@smregister
class ServerSM(StateMachine):
    """
    Server State Machine

    Implements Server State machine
    """
    _table = 'sm_servers'
    _sm_events = (ServerSMEnable, ServerSMDisable, 
                ServerSMReset, ServerSMConfigure,
                ServerSMConfigChange, ServerSMCheckServer )

    def __init__(self, server_name, address, sg_name, server_type,
                    ssh_address):
        """
        Create a server SM object
        """
        self.name = server_name
        self.address = address
        self.server_type = server_type
        self.ssh_address = ssh_address
        self.state = SSTATE_DISABLED
        self.ctime = None
        self.mtime = None
        self.last_reply = None
        self.retry_msg = None
    
    def set_sg(self, sg):
        """
        Set the server group this zone is served on.
        """
        if hasattr(self, 'sg') and self.sg:
            old_sg = self.sg
            old_sg.servers.remove(self)
            # do the following if relationships are set up for lazy='dynamic'
            #self.sg = None
            #del(self.sg)
        sg.servers.append(self)
        self.sg = sg

    def _to_engine_stuff(self, time_format):
        """
        Backend common function to fill out timestamps etc for
        to_engine methods.
        """
        if hasattr(self, 'sg') and self.sg:
            sg_name = self.sg.name
        else:
            sg_name = None
        if not time_format:
            ctime = (self.ctime.isoformat(sep=' ') 
                               if self.ctime else None)
            mtime = (self.mtime.isoformat(sep=' ') 
                               if self.mtime else None)
            last_reply = (self.last_reply.isoformat(sep=' ') 
                               if self.last_reply else None)
        else:
            ctime = (self.ctime.strftime(time_format) 
                               if self.ctime else None)
            mtime = (self.mtime.strftime(time_format) 
                               if self.mtime else None)
            last_reply = (self.last_reply.strftime(time_format) 
                               if self.last_reply else None)
        return (sg_name, ctime, mtime, last_reply)


    def to_engine_brief(self, time_format=None):
        """
        Output server SM attributes as JSON
        """
        sg_name, ctime, mtime, last_reply = self._to_engine_stuff(time_format)
        return {'server_id': self.id_, 'server_name': self.name,
                'address': self.address, 'state': self.state,
                'ctime': ctime, 'mtime': mtime,
                'is_master': self.is_master(),
                'last_reply': last_reply,
                'retry_msg': self.retry_msg,
                'ssh_address': self.ssh_address}

    def to_engine(self, time_format=None):
        """
        Output server SM attributes as JSON
        """
        sg_name, ctime, mtime, last_reply = self._to_engine_stuff(time_format)
        return {'server_id': self.id_, 'server_name': self.name,
                'address': self.address,
                'state': self.state, 'server_type': self.server_type, 
                'sg_id': self.sg_id, 'sg_name': sg_name,
                'ctime': ctime, 'mtime': mtime,
                'is_master': self.is_master(),
                'last_reply': last_reply,
                'retry_msg': self.retry_msg,
                'ssh_address': self.ssh_address, 
                'zone_count': self.zone_count}

    def is_this_server(self):
        """
        Return whether this server is actually this server

        Server can be congfigured in DB for DR use
        """
        return self.address in settings['this_servers_addresses']

    def is_disabled(self):
        """
        Return whether the server is DISABLED or not
        """
        return self.state == SSTATE_DISABLED

    def query_is_disabled(self, query):
        """
        Add DISABLED query term 
        """
        return query.filter(ServerSM.state == SSTATE_DISABLED)

    def query_is_not_disabled(self, query):
        """
        Add not DISABLED query term 
        """
        return query.filter(ServerSM.state != SSTATE_DISABLED)

    def is_master(self):
        """
        Return if this server definition is currently the master
        """
        if (hasattr(self, 'master_sm') and self.master_sm):
            return True
        return False

    def _rsync_dnssec_keys(self, event):
        """
        Rsync DNSSEC key files across to DR replica server
        """
        if not(self.sg and hasattr(self.sg, 'master_sm') 
                and self.sg.master_sm):
            # OK, we are not interested in DNSSEC stuff
            return
        key_dir = settings['master_dnssec_key_dir'] 
        try:
            cmdline = (settings['rsync_path'] 
                    + ' ' + settings['rsync_dnssec_args'] 
                    + ' --password-file ' 
                    + settings['rsync_dnssec_password_file'] 
                    + ' ' + key_dir + '/'
                    + ' ' + settings['rsync_dnssec_target'])
            # Add IPv6 address squares
            address_string = '[' + self.address + ']' \
                        if self.address.find(':') else self.address
            cmdline_str = cmdline % address_string
            cmdline = cmdline_str.split(' ')
            output = check_output(cmdline, stderr=STDOUT)
        except CalledProcessError as exc:
            if exc.output:
                # Here is something a bit untidy
                output = str(exc.output)[2:-3].replace('\\n', ', ')
                msg = (
                    "Server '%s': failed to rsync dnssec keys, %s, %s" 
                    % (self.name, str(exc), output))
            else:
                msg = (
                    "Server '%s': failed to rsync dnssec keys, %s" 
                    % (self.name, str(exc)))
            raise CantRsyncDnssecKeysDrServer(msg)

    def _rsync_includes(self, event):
        """
        Rsync include files across to a server
        """
        include_dir = self.sg.get_include_dir()
        try:
            cmdline = (settings['rsync_path'] + ' ' + settings['rsync_args'] 
                    + ' --password-file ' + settings['rsync_password_file'] 
                    + ' ' + include_dir + '/' + ' ' + settings['rsync_target'])
            # Add IPv6 address squares
            address_string = '[' + self.address + ']' \
                        if self.address.find(':') else self.address
            cmdline_str = cmdline % address_string
            cmdline = cmdline_str.split(' ')
            output = check_output(cmdline, stderr=STDOUT)
        except CalledProcessError as exc:
            if exc.output:
                # Here is something a bit untidy
                output = str(exc.output)[2:-3].replace('\\n', ', ')
                msg = (
                    "Server '%s': failed to rsync include files, %s, %s" 
                    % (self.name, str(exc), output))
            else:
                msg = (
                    "Server '%s': failed to rsync include files, %s" 
                    % (self.name, str(exc)))
            raise CantRsyncServer(msg)

    def _rndc_server(self, event, *rndc_args):
        """
        Run rndc
        """
        output = ''
        try:
            cmdline = [settings['rndc_path']]
            if not self.is_master():
                cmdline.extend([ '-s', self.name])
            cmdline.extend(rndc_args)
            output = check_output(cmdline, universal_newlines=True)
        except CalledProcessError as exc:
            msg = ("Server '%s': %s failed, %s" 
                    % (self.name, settings['rndc_path'], str(exc)))
            raise CantRndcServer(msg)
        if (rndc_args[-1] == 'status' and output):
            try:
                output = output.split('\n')
                output = [s for s in output
                        if s.find(settings['bind9_zone_count_tag']) != -1]
                if not len(output):
                    raise IndexError("Can't gather zone Count")
                zone_stuff = output[0].split()
                self.zone_count = int(zone_stuff[-1])
            except (IndexError, ValueError)as exc:
                log_error("Server '%s': can't gather zone count")

    def _soa_query_server(self, zone_name):
        """
        Use dnspython to read the SOA record of a Zone from the DNS server.

        This function returns whether the server is speaking inteligible DNS
        or not.  It function is as a keep alive check.
        """
        zone = dns.name.from_text(zone_name)
        rdtype = dns.rdatatype.from_text(RRTYPE_SOA)
        rdclass = dns.rdataclass.IN
        query = dns.message.make_query(zone, rdtype, rdclass)
        exc = None
        try:
            # Use TCP as dnspython can't track replies to multithreaded
            # queries
            answer = dns.query.tcp(query, self.address,
                    timeout=float(settings['dns_query_timeout']))
            if not query.is_response(answer):
                msg = ("Server '%s': SOA query - reply from unexpected source,"
                        " retrying" % self.name)
                raise CantSoaQueryServer(msg)
        except dns.query.BadResponse as exc:
            msg = ("Server '%s': SOA query - received incorrectly"
                    " formatted query."  % self.name)
            raise BrokenServer(msg)
        except dns.exception.Timeout:
            msg =  ("Server '%s': SOA query - timeout waiting for response,"
                    " retrying" % self.name)
            raise CantSoaQueryServer(msg)
        except dns.query.UnexpectedSource as exc:
            # For UDP, FormError and BadResponse here are also failures
            msg = ("Server '%s': SOA query - reply from unexpected source,"
                    " retrying" % self.name)
            raise CantSoaQueryServer(msg)
        except dns.exception.FormError as exc:
            msg = ("Server '%s': SOA query - remote responded incorrectly"
                    " formatted query."  % self.name)
            raise BrokenServer(msg)
        except (socket.error, OSError, IOError) as exc:
            if errno in (errno.EACCES, errno.EPERM, errno.ECONNREFUSED, 
                    errno.ENETUNREACH, errno.ETIMEDOUT):
                msg = ("Server '%s': SOA query - can't query server %s - %s"
                        % (self.name, self.address, exc.strerror))
                raise CantSoaQueryServer(msg)
            msg = ("Server '%s': server %s, SOA query - fatal error %s."
                   % (self.name, self.address, exc.strerror))
            raise BrokenServer(msg)
        finally:
            # Clean up memory
            del query
        try:
            # Check and process result codes
            # with 0, check that answer.answer contains stuff, and check type of
            # 1st element is dns.rrset.RRset via isinstance()
            rcode = answer.rcode()
            rcode_text = dns.rcode.to_text(answer.rcode())
            if rcode in _soaquery_rcodes['success']:
                if (len(answer.answer) 
                        and isinstance(answer.answer[0], dns.rrset.RRset)):
                    return
                msg = ("Server '%s': SOA query - bad response received."
                        % self.name)
                raise BrokenServer(msg)
            elif rcode in _soaquery_rcodes['ok']:
                return
            elif rcode in _soaquery_rcodes['retry']:
                msg = ("Server '%s': SOA query - temporary failure - rcode '%s'"
                        % (self.name, rcode_text))
                raise CantSoaQueryServer(msg)
            elif rcode in _soaquery_rcodes['broken']:
                msg = ("Server '%s': SOA query - broken - rcode '%s'"
                        % (self.name, rcode_text))
                raise BrokenServer(msg)
            else:
                msg = ("Server '%s': SOA query - response with indeterminate"
                        " error - broken?" % self.name)
                raise BrokenServer(msg)
                
        finally:
            # clean up memory
            del answer

    def _process_sm_exc(self, db_session, exc, msg, new_state=None):
        """
        Process a state machine exception.  For putting as much code as
        possible on a common call path.
        """
        delay_factor = 1 + random()
        delay_period = timedelta(
                minutes=delay_factor*float(settings['master_hold_timeout']))
        old_state = self.state
        if new_state:
            self.state = new_state
        log_msg = str(exc)
        log_info(log_msg)
        self.retry_msg = log_msg
        create_event(ServerSMConfigure, db_session=db_session,
            sm_id=self.id_, server_id=self.id_, delay=delay_period, 
            server_name=self.name)
        state_str = ''
        if old_state != self.state:
            state_str = ("old state %s, new state %s - " 
                                    % (old_state, self.state) )
        return (RCODE_OK, "Server '%s': %s%s" 
                    % (self.name, state_str, msg))
    
    def _create_check(self, event):
        """
        Process a state machine exception.  For putting as much code as
        possible on a common call path.
        """
        db_session = event.db_session

        # Check every half to full holdout time
        master_hold_timeout = float(settings['master_hold_timeout'])
        delay_factor = (1 + random()) * 0.5
        delay_period = timedelta(minutes=delay_factor*master_hold_timeout)
        hold_period = timedelta(minutes=master_hold_timeout)

        # See if a check event already exists for this ServerSM
        current_checks = find_events(ServerSMCheckServer, db_session,
                                                    server_id=self.id_)
        current_checks = [e for e in current_checks if e.id_ != event.id_]
        if len(current_checks):
            return

        create_event(ServerSMCheckServer, db_session=db_session,
            sm_id=self.id_, server_id=self.id_, delay=delay_period, 
            server_name=self.name)

    def _disable(self, event):
        """
        Disable the Server
        """
        self.state = SSTATE_DISABLED
        self.last_reply = None
        self.retry_msg = None
        return (RCODE_OK, "Server '%s': disabled" % self.name)

    def _already_disabled(self, event):
        """
        Disable the Server
        """
        raise ServerAlreadyDisabled("server already disabled")

    def _enable(self, event):
        """
        Enable the Server
        """
        try:
            query = event.db_session.query(ServerSM)\
                    .filter(ServerSM.address == self.address)\
                    .filter(ServerSM.state != SSTATE_DISABLED)
            result = query.all()
            if result:
                raise ServerEnableFailure(
                    "Server '%s' - server '%s' with same address enabled"
                        % (self.name, result[0].name))
        except NoResultFound:
            pass
        self.state = SSTATE_CONFIG
        create_event(ServerSMConfigure, db_session=event.db_session,
                sm_id=self.id_, server_id=self.id_, server_name=self.name)
        return (RCODE_OK, "Server '%s': enabling" % self.name)

    def _already_enabled(self, event):
        """
        Disable the Server
        """
        raise ServerAlreadyEnabled("server already enabled")

    def _config_change(self, event):
        """
        Start the reconfiguration process
        """
        self.state = SSTATE_CONFIG
        self.retry_msg = None
        create_event(ServerSMConfigure, db_session=event.db_session,
                sm_id=self.id_, server_id=self.id_, server_name=self.name)
        return (RCODE_OK, "Server '%s': reconfiguring" % self.name)

    def _configure(self, event):
        """
        Configure a server
        """
        db_session = event.db_session
        if not self.is_this_server():
            # rsync configuration
            try:
                self._rsync_includes(event)
                self._rsync_dnssec_keys(event)
            except CantRsyncServer as exc:
                return self._process_sm_exc(db_session, exc,
                        "retrying config process", SSTATE_RETRY)

        # Test that server is talking sanely
        try:
            self._soa_query_server(settings['serversm_soaquery_domain'])
        except BrokenServer as exc:
            return self._process_sm_exc(db_session, exc, 
                        "retrying config process", SSTATE_BROKEN)
        except CantSoaQueryServer as exc:
            return self._process_sm_exc(db_session, exc, 
                        "retrying config process", SSTATE_RETRY)

        if self.is_this_server():
            # This means we are master - DON'T DO ANYTHING as this can
            # cause an rndc race in bind, which can trash dynamic zones.
            self.state = SSTATE_OK
            self.retry_msg = None
            self.last_reply = db_clock_time(db_session)
            self._create_check(event)
            return (RCODE_OK, 
                    "Server '%s': now master - SSM slot reserved" 
                        % self.name)
        if self.server_type == 'bind9':
            self.last_reply = db_clock_time(db_session)
            db_session.flush()
            try:
                self._rndc_server(event, 'reconfig')
            except CantRndcServer as exc:
                return self._process_sm_exc(db_session, 
                        exc, "retrying config process", SSTATE_RETRY)
        
        self.state = SSTATE_OK
        self.retry_msg = None
        # create check event
        self.last_reply = db_clock_time(db_session)
        self._create_check(event)
        return (RCODE_OK, "Server '%s': configured" % self.name)

    def _check_server(self, event):
        """
        Check that a server is running and gather some statistics
        """
        db_session = event.db_session

        # Test that server is talking sanely
        try:
            self._soa_query_server(settings['serversm_soaquery_domain'])
        except BrokenServer as exc:
            return self._process_sm_exc(db_session, exc, 
                        "retrying config process", SSTATE_BROKEN)
        except CantSoaQueryServer as exc:
            return self._process_sm_exc(db_session, exc, 
                        "retrying config process", SSTATE_RETRY)

        # Check that rndc is working and gather some stats
        if self.server_type == 'bind9':
            self.last_reply = db_clock_time(db_session)
            db_session.flush()
            try:
                self._rndc_server(event, 'status')
            except CantRndcServer as exc:
                return self._process_sm_exc(db_session, 
                        exc, "retrying config process", SSTATE_RETRY)

        self.last_reply = db_clock_time(db_session)
        self._create_check(event)
        return (RCODE_OK, "Server '%s': alls well" % self.name)

    _sm_table = {   
            SSTATE_DISABLED: {
                ServerSMEnable: _enable,
                ServerSMDisable: _already_disabled,
                },
            SSTATE_CONFIG: {
                ServerSMDisable: _disable,
                ServerSMEnable: _already_enabled,
                ServerSMConfigure: _configure,
                ServerSMReset: _config_change,
                },
            SSTATE_RETRY: {
                ServerSMDisable: _disable,
                ServerSMEnable: _already_enabled,
                ServerSMConfigure: _configure,
                ServerSMReset: _config_change,
                },
            SSTATE_BROKEN: {
                ServerSMDisable: _disable,
                ServerSMEnable: _already_enabled,
                ServerSMConfigure: _configure,
                ServerSMReset: _config_change,
                },
            SSTATE_OK: {
                ServerSMDisable: _disable,
                ServerSMEnable: _already_enabled,
                ServerSMConfigChange: _config_change,
                ServerSMReset: _config_change,
                ServerSMCheckServer: _check_server,
                },
            }
                

def exec_server_sm(server_sm, sync_event_type, 
                exception_type=ServerSmFailure,
                **event_kwargs):
    """
    Execute a synchronous event of the server state machine
    """
    if not issubclass(sync_event_type, SMSyncEvent):
        raise TypeError("'%s' is not a Synchonous Event." % sync_event_type)

    event = sync_event_type(sm_id=server_sm.id_,
                                    server_id=server_sm.id_,
                                    **event_kwargs)
    results = event.execute()
    if results['state'] != ESTATE_SUCCESS:
        # By std Python convention exceptions don't have default value
        # arguments. Do the following to take care of 2 or 3 argument
        # variants for the exception.
        raise exception_type(server_sm.name, results['message'], results)
    return results

def new_server(db_session, server_name, address, sg_name, server_type=None,
                ssh_address=None):
    """
    Create a new server
    """
    server_name = server_name.lower()
    if server_name.endswith('.'):
        server_name = server_name[:-1]
    if not sg_name:
        sg_name = zone_cfg.get_row_exc(db_session, 'default_sg')
    if not sg_name in list_all_sgs(db_session):
        raise NoSgFound(sg_name)
    try:
        server_list = db_session.query(ServerSM)\
                        .filter(ServerSM.name == server_name).all()
        if len(server_list):
            raise ServerExists(server_name)
    except NoResultFound:
        pass
    if not server_type:
        server_type = zone_cfg.get_row(db_session, 'default_stype', 
                        raise_exc=True)
    server_sm = ServerSM(server_name, address, sg_name, server_type,
                            ssh_address)
    try:
        db_session.add(server_sm)
        db_session.flush()
    except IntegrityError as exc:
        raise ServerAddressExists(address)
    sg = find_sg_byname(db_session, sg_name, raise_exc=True)
    server_sm.set_sg(sg)
    db_session.flush()
    return server_sm


def del_server(db_session, server_name):
    """
    Delete a server
    """
    # Get the Server from the DB.
    try:
        server_sm = db_session.query(ServerSM)\
                    .filter(ServerSM.name == server_name).one()
    except NoResultFound:
        raise NoServerFound(server_name)
    if not server_sm.is_disabled():
        raise ServerNotDisabled(server_name)
    db_session.delete(server_sm)
    db_session.flush()

def find_server_byname(db_session, server_name, raise_exc=True):
    """
    Find a server by name
    """
    query = db_session.query(ServerSM)\
            .filter(ServerSM.name == server_name)
    try:
        server_sm = query.one()
    except NoResultFound:
        server_sm = None
    if raise_exc and not server_sm:
        raise NoServerFound(server_name)
    return server_sm

def find_server_byaddress(db_session, address, raise_exc=True):
    """
    Find a server by name
    """
    query = db_session.query(ServerSM)\
            .filter(ServerSM.address == address)
    try:
        server_sm = query.one()
    except NoResultFound:
        server_sm = None
    if raise_exc and not server_sm:
        raise NoServerFoundByAddress(address)
    return server_sm

def rename_server(db_session, server_name=None, new_server_name=None,
        server_sm=None):
    """
    Rename a server
    """
    if not server_sm:
        server_sm = find_server_byname(db_session, server_name)
    new_server_name = new_server_name.lower()
    if new_server_name.endswith('.'):
        new_server_name = server_name[:-1]
    try:
        result = db_session.query(ServerSM)\
                .filter(ServerSM.name == new_server_name).all()
    except NoResultFound:
        pass
    if len(result):
        raise ServerExists(new_server_name)
    server_sm.name = new_server_name

def set_server_ssh_address(db_session, server_name, ssh_address):
    """
    Set a servers ssh_address
    """
    server_sm = find_server_byname(db_session, server_name)
    server_sm.ssh_address = ssh_address
    db_session.flush()

def set_server(db_session, server_name, new_server_name=None, address=None,
                server_type=None, ssh_address=None):
    """
    Change a servers data.  Can on only be done when it is disabled.
    """
    server_sm = find_server_byname(db_session, server_name)
    if not server_sm.is_disabled():
        raise ServerNotDisabled(server_sm.name)
    if address:
        server_sm.address = address
    if ssh_address:
        server_sm.ssh_address = ssh_address
    if new_server_name:
        rename_server(db_session, new_server_name=new_server_name,
                server_sm=server_sm)
    if server_type:
        server_sm.server_type = server_type
    db_session.flush()

def move_server_sg(db_session, server_name, sg_name=None):
    """
    Move a server between SGs
    """
    server_sm = find_server_byname(db_session, server_name)
    if not server_sm.is_disabled():
        raise ServerNotDisabled(server_sm.name)
    if not sg_name:
        sg_name = zone_cfg.get_row_exc(db_session, 'default_sg')
    if not sg_name in list_all_sgs(db_session):
        raise NoSgFound(sg_name)
    sg = find_sg_byname(db_session, sg_name, raise_exc=True)
    server_sm.set_sg(sg)

# Set up SOA query rcodes
_soaquery_rcodes = {}
def init_soaquery_rcodes():
    """
    Setup SOA query keep alive rcodes
    """
    #Transform settings for DYNDNS RCODES to something we can understand
    _soaquery_rcodes['success'] = [dns.rcode.from_text(x) 
        for x in 
            settings['serversm_soaquery_success_rcodes'].strip().split()]
    _soaquery_rcodes['ok'] = [dns.rcode.from_text(x) 
        for x in settings['serversm_soaquery_ok_rcodes'].strip().split()]
    _soaquery_rcodes['retry'] = [dns.rcode.from_text(x) 
        for x in settings['serversm_soaquery_retry_rcodes'].strip().split()]
    _soaquery_rcodes['broken'] = [dns.rcode.from_text(x) 
        for x in 
            settings['serversm_soaquery_broken_rcodes'].strip().split()]



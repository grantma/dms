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
Module for ZoneEngine base class
"""


import datetime
import re
import socket
from io import StringIO

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy import desc
from pyparsing import ParseBaseException

from magcode.core.globals_ import *
from dms.globals_ import *
from magcode.core.database import *
from magcode.core.database import *
from magcode.core.database.event import find_events
from magcode.core.database.event import ESTATE_FAILURE
from magcode.core.database.event import create_event
from magcode.core.database.event import Event
# import all possible types used here so that they intialise in zone-tool
from dms.database.master_sm import zone_sm_dnssec_schedule
from dms.database.zone_sm import ZoneSM
from dms.database.zone_sm import ZoneSMEdit
from dms.database.zone_sm import ZoneSMEditExit
from dms.database.zone_sm import ZoneSMEditTimeout
from dms.database.zone_sm import ZoneSMEditLockTickle
from dms.database.zone_sm import ZoneSMEditUpdate
from dms.database.zone_sm import ZoneSMUpdate
from dms.database.zone_sm import ZoneSMEditSaved
from dms.database.zone_sm import ZoneSMEnable
from dms.database.zone_sm import ZoneSMDisable
from dms.database.zone_sm import ZoneSMDoReconfig
from dms.database.zone_sm import ZoneSMDoBatchConfig
from dms.database.zone_sm import ZoneSMDoConfig
from dms.database.zone_sm import ZoneSMEditSavedNoLock
from dms.database.zone_sm import ZoneSMDelete
from dms.database.zone_sm import ZoneSMUndelete
from dms.database.zone_sm import ZoneSMDoReset
from dms.database.zone_sm import ZoneSMDoRefresh
from dms.database.zone_sm import ZoneSMDoDestroy
from dms.database.zone_sm import ZoneSMDoSgSwap
from dms.database.zone_sm import ZoneSMDoSetAltSg
from dms.database.zone_sm import ZLSTATE_EDIT_LOCK
from dms.database.zone_sm import ZSTATE_DISABLED
from dms.database.zone_sm import ZSTATE_UNCONFIG
from dms.database.zone_sm import ZSTATE_DELETED
from dms.database.zone_sm import ZSTATE_PUBLISHED
from dms.database.zone_sm import exec_zonesm
from dms.database.zone_sm import new_zone
from dms.database.zone_sm import DynDNSZoneSM
from dms.database.zone_instance import ZoneInstance
from dms.database.zone_instance import new_zone_zi
from dms.database.resource_record import ResourceRecord
from dms.database.resource_record import data_to_rr
import dms.database.zone_cfg as zone_cfg
from dms.database.reference import Reference
from dms.database.rr_comment import RRComment
from dms.database.zone_sectag import ZoneSecTag
from dms.database.zone_sectag import list_all_sectags
# import securitytags so that sql_data is initialised
import dms.database.zone_sectag
from dms.database.master_sm import show_master_sm
from dms.database.master_sm import get_mastersm_replica_sg
from dms.database.sg_utility import list_all_sgs
from dms.database.sg_utility import find_sg_byname
from dms.database.reference import new_reference
from dms.database.reference import del_reference
from dms.database.reference import find_reference
from dms.database.reference import rename_reference
from dms.database.server_sm import ServerSM
from dms.database.server_group import ServerGroup
from magcode.core.wsgi.jsonrpc_server import InvalidParamsJsonRpcError
from dms.exceptions import *
from dms.database.zone_query import rr_query_db_raw
from dms.zone_data_util import ZoneDataUtil
from dms.dns import is_inet_domain
from dms.dns import is_network_address
from dms.dns import wellformed_cidr_network
from dms.dns import zone_name_from_network
from dms.dns import new_soa_serial_no
from dms.database.reverse_network import new_reverse_network
from dms.database.reverse_network import ReverseNetwork
from dms.zone_text_util import data_to_bind
from dms.zone_text_util import bind_to_data


class ZoneEngine(ZoneDataUtil):
    """
    Base Zone Editing/control Engine container class

    Contains common code and stub methods.
    """
    def __init__(self, time_format=None, sectag_label=None):
        """
        Initialise engine. Get a scoped DB session.
        """
        self.time_format = time_format
        self.sectag = ZoneSecTag(sectag_label=sectag_label)
        self.refresh_db_session()
        if self.sectag not in list_all_sectags(self.db_session):
            raise ZoneSecTagConfigError(self.sectag.sectag)

    def refresh_db_session(self):
        self.db_session = sql_data['scoped_session_class']()

    def rollback(self):
        self.db_session.rollback()

    def _finish_op(self):
        self.db_session.commit()
    
    def _begin_op(self):
        # Refresh SA session
        self.refresh_db_session()
        self.db_session.commit()

    _login_id_char_re = re.compile(r'^[\-_a-zA-Z0-9.@]+$')
    _login_id_start_re = re.compile(r'^[0-9a-zA-Z][\-_a-zA-Z0-9.@]*$')
    def _make_change_by(self, login_id):
        """
        Create a change_by string from a login_id
        """
        # Check that the supplied login_id is acceptable
        if not login_id:
            raise LoginIdInvalidError("a login_id must be given" )
        if not isinstance(login_id, str):
            raise LoginIdInvalidError("login_id must be a string" )
        if len(login_id) > 512:
            error_msg = "too long, must be <= 512."
            raise LoginIdInvalidError(error_msg)
        if not self._login_id_char_re.match(login_id):
            error_msg = "can only contain characters '-_a-zA-Z0-9.@'"
            raise LoginIdFormatError(login_id, error_msg)
        if not self._login_id_start_re.match(login_id):
            error_msg = "must start with 'a-zA-Z0-9'"
            raise LoginIdFormatError(login_id, error_msg)

        return login_id + '/' + self.sectag.sectag      

    def _list_zone(self, names=None, reference=None, sg_name=None,
            include_deleted=False, toggle_deleted=False,
            include_disabled=True):
        """
        Backend search for the given names.  Multiple names may be given.
        Wildcards can be used for partial matches.  No name will list all 
        zones.
        """

        def build_query(query):
            """
            Common query code
            """
            if reference:
                query = query.join(Reference)\
                        .filter(Reference.reference.ilike(reference))
            if sg_name and self.sectag.sectag == settings['admin_sectag']:
                if sg_name not in list_all_sgs(self.db_session):
                    raise NoSgFound(sg_name)
                query = query.join(ServerGroup,
                         ServerGroup.id_ == ZoneSM.sg_id)\
                        .filter(ServerGroup.name == sg_name)
            if include_deleted:
                pass
            elif toggle_deleted:
                query = query.filter(ZoneSM.state == ZSTATE_DELETED)
            else:
                query = query.filter(ZoneSM.state != ZSTATE_DELETED)
            if not include_disabled:
                query = query.filter(ZoneSM.state != ZSTATE_DISABLED)
            return(query)
       
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        db_query_slice = get_numeric_setting('db_query_slice', int)
        if not names:
            # No arguments
            query = self.db_session.query(ZoneSM)
            query = build_query(query)
            query = query.order_by(ZoneSM.name)
            # Set up query so that server side curses are used, and the whole
            # zone database is not grabbed all at once, stopping extreme
            # allocation of memory...
            query = query.yield_per(db_query_slice)
            zones = []
            for z in query:
                if (self.sectag.sectag != settings['admin_sectag']
                        and self.sectag not in z.sectags):
                    continue
                zones.append(z.to_engine_brief())
            self._finish_op()
            if not zones:
                raise NoZonesFound('')
            return zones
       
        # We were given some arguments
        zones = []
        # We keep domains and labels in database lowercase
        name_pattern = ' '.join(names).lower()
        names = [x.lower() for x in names]
        names = [x.replace('*', '%') for x in names]
        names = [x.replace('?', '_') for x in names]
        # Perform limit checks to prevent RAM hoggery DOS Death By SQL
        if ('%' in names and len(names) > 1):
            raise OnlyOneLoneWildcardValid(name_pattern)
        # Check that reference is given for non admin sectag accesses
        if (self.sectag.sectag != settings['admin_sectag'] 
                and not reference):
            raise ReferenceMustBeGiven(name_pattern)
        for name in names:
            network_address_flag = is_network_address(name)
            network = wellformed_cidr_network(name, filter_mask_size=False)
            query = self.db_session.query(ZoneSM)
            if network_address_flag:
                query = query.join(ReverseNetwork)\
                        .filter( ':name <<= reverse_networks.network')\
                        .params(name=name)\
                        .order_by(ReverseNetwork.network)
            elif network:
                query = query.join(ReverseNetwork)\
                        .filter( ':network >>= reverse_networks.network')\
                        .params(network=network)\
                        .order_by(ReverseNetwork.network)
            else:
                if not name.endswith('.') and not name.endswith('%'):
                    name += '.'
                query = query.filter(ZoneSM.name.like(name))
            query = build_query(query)
            query = query.yield_per(db_query_slice)
            for z in query:
                if (self.sectag.sectag != settings['admin_sectag']
                        and self.sectag not in z.sectags):
                    continue
                zones.append(z.to_engine_brief())
        zones = sorted(zones, key=lambda zone: zone['name'])
        if not zones:
            raise NoZonesFound(name_pattern)
        self._finish_op()
        return zones

    def list_zone(self, names=None, reference=None):
        """
        1st domains level list_zone call
        """
        return self._list_zone(names=names, reference=reference)

    def list_zone_admin(self, names=None, reference=None, 
            sg_name=None, include_deleted=False, toggle_deleted=False,
            include_disabled=True):
        """
        Admin privilege list_zone()
        """
        return self._list_zone(names=names, reference=reference,
                sg_name=sg_name, include_deleted=include_deleted,
                toggle_deleted=toggle_deleted,
                include_disabled=include_disabled)

    def _get_zone_sm(self, name, zone_id=None, check_sectag=True,
            toggle_deleted=False, include_deleted=False, exact_network=False):
        """
        Get zone_sm.
        """
        db_session = self.db_session
        # We keep domains and labels in database lowercase
        name = name.lower()
        multiple_results = False
        network_address_flag = is_network_address(name)
        # Don't reassign name so that error messages follow what user supplied
        # as input
        network = wellformed_cidr_network(name)
        try:
            query = db_session.query(ZoneSM)
            if network_address_flag and not exact_network:
                query = query.join(ReverseNetwork)\
                        .filter( ':inet <<= reverse_networks.network')\
                        .params(inet=name)\
                        .order_by(ReverseNetwork.network.desc())
            elif network_address_flag and exact_network:
                raise ZoneNotFound(name)
            elif network and not exact_network:
                query = query.join(ReverseNetwork)\
                        .filter( ':inet <<= reverse_networks.network')\
                        .params(inet=network)\
                        .order_by(ReverseNetwork.network.desc())
            elif network and exact_network:
                query = query.join(ReverseNetwork)\
                        .filter( ':inet = reverse_networks.network')\
                        .params(inet=network)\
                        .order_by(ReverseNetwork.network.desc())
            else:
                query = query.filter(ZoneSM.name == name)
            if zone_id:
                query = query.filter(ZoneSM.id_ == zone_id)
            if include_deleted:
                pass
            elif toggle_deleted:
                query = query.filter(ZoneSM.state == ZSTATE_DELETED)
            else:
                query = query.filter(ZoneSM.state != ZSTATE_DELETED)
            if network or network_address_flag:
                query = query.limit(1)
            zone_sm = query.one()
        except NoResultFound:
            zone_sm = None
        except MultipleResultsFound:
            multiple_results = True
        # Decoupled exception traces
        if multiple_results:
            raise ZoneMultipleResults(name)
        if not zone_sm:
            raise ZoneNotFound(name)
        if not check_sectag:
            return zone_sm
        # Check security tag
        if self.sectag.sectag == settings['admin_sectag']:
            return zone_sm
        if self.sectag not in zone_sm.sectags:
            raise ZoneNotFound(name)
        return zone_sm

    def _get_zone_sm_byid(self, zone_id):
        """
        Get zone_sm.
        """
        db_session = self.db_session
        # Get active zi_id
        try:
            zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
        except NoResultFound:
            zone_sm = None
        # Decoupled exception traces
        if not zone_sm:
            raise ZoneNotFoundByZoneId(zone_id)
        # Check security tag
        if self.sectag.sectag == settings['admin_sectag']:
            return zone_sm
        if self.sectag not in zone_sm.sectags:
            raise ZoneNotFoundByZoneId(zone_id)
        return zone_sm

    def _get_zi(self, zi_id):
        """
        Get zi.
        """
        db_session = self.db_session
        # Get active zi_id
        zi = self._resolv_zi_id(None, zi_id,
                        specific_zi_id=True)
        if not zi:
            raise ZiNotFound('*', zi_id)
        return zi
  
    # Parsing regexps for zi_id.  Also see _zi_id_human_str in 
    # dms.exceptions
    _zi_am_pm_str = r'am|pm|AM|PM|aM|pM|Pm|Am|a|A|p|P'
    
    _zi_adj_re = re.compile(r'^\^(-+|\++|-\S+|\+\S+)$')
    _zi_adj_minus_re = re.compile(r'^-+$')
    _zi_adj_plus_re = re.compile(r'^\++$')
    _zi_adj_minusn_re = re.compile(r'^-(\S+)$')
    _zi_adj_plusn_re = re.compile(r'^\+(\S+)$')
    
    _zi_unit_re = re.compile(r'^\@(\S+)([smhdw])$')
    _zi_ddmmyyyy_hhmm_re = re.compile(r'^(\S+)\/(\S+)\/(\S+),(\S+):(\S+?)('
                                + _zi_am_pm_str + r'){0,1}$')
    _zi_iso_date_hhmm_re = re.compile(r'^(\S+)-(\S+)-(\S+),(\S+):(\S+?)(' 
                                            + _zi_am_pm_str + r'){0,1}$')
    _zi_ddmmyyyy_re = re.compile(r'^(\S+)\/(\S+)\/(\S+)$')
    _zi_iso_date_re = re.compile(r'^(\S+)-(\S+)-(\S+)$')
    _zi_ddslashmm_re = re.compile(r'^(\S+)\/(\S+)$')
    _zi_hhmm_re = re.compile(r'^(\S+):(\S+?)(' + _zi_am_pm_str + r'){0,1}$')
    _zi_int_adj_re = re.compile(r'^(\S+)(-+|\++|-\S+|\+\S+)$')
    def _resolv_zi_id(self, zone_sm, zi_id, specific_zi_id=False):
        """
        Resolve a zi_id from a string form
        """
        def new_query():
            if not zone_sm:
                query = db_session.query(ZoneInstance)
            else:
                query = zone_sm.all_zis
            query = query.yield_per(db_query_slice)
            return query

        def resolv_adj_str(adj_str):
            nonlocal query
            minusn_match = self._zi_adj_minusn_re.search(adj_str)
            plusn_match = self._zi_adj_plusn_re.search(adj_str)
            try:
                if self._zi_adj_minus_re.search(adj_str):
                    delta = -1 * len(adj_str)
                elif self._zi_adj_plus_re.search(adj_str):
                    delta = len(adj_str)
                elif minusn_match:
                    delta = -1 * int(minusn_match.group(1))
                elif plusn_match:
                    delta = int(plusn_match.group(1))
                else:
                    raise ZiIdAdjStringSyntaxError(zi_id)
            except ValueError:
                raise ZiIdAdjStringSyntaxError(zi_id)
            
            # A bit of SQL magic to get offset from pivot ID
            subq = db_session.query(ZoneInstance)\
                    .filter(ZoneInstance.id_ == pivot_zi_id).subquery()
            if delta < 0:
                query = query.filter(ZoneInstance.ctime <= subq.c.ctime)\
                        .order_by(ZoneInstance.ctime.desc())
                delta *= -1
            else:
                query = query.filter(ZoneInstance.ctime >= subq.c.ctime)\
                        .order_by(ZoneInstance.ctime.asc())
            try:
                result = query.offset(delta).limit(1).one()
            except NoResultFound:
                result = None
            return result

        def ctime_query(target_ctime):
            nonlocal query
            query = query.filter(ZoneInstance.ctime <= target_ctime)\
                        .order_by(ZoneInstance.ctime.desc()).limit(1)
            try:
                result = query.one()
            except NoResultFound:
                result = None
            return result

        def do_year_date_time(regexp_match, date_exception, iso_format_date):
            """
            Work out target_ctime, given a complete date 
            """
            match_args = regexp_match.groups()
            try:
                if iso_format_date:
                    year = int(match_args[0])
                    month = int(match_args[1])
                    day = int(match_args[2])
                else:
                    day = int(match_args[0])
                    month = int(match_args[1])
                    year = int(match_args[2])
            except ValueError:
                raise date_exception(zi_id)

            if len(match_args) == 3:
                # time not given, assume midnight
                hour = 0
                minute = 0
            else:
                try:
                    hour = int(match_args[3])
                    minute = int(match_args[4])
                except ValueError:
                    raise ZiIdHhMmSyntaxError(zi_id)
                # Process AM/PM
                if len(match_args) > 5 and match_args[5]:
                    am_pm = match_args[5].lower()
                    if (am_pm.startswith('p') and hour < 12):
                        hour += 12

            # Sort out 2 digit years
            if (70 <= year <= 99):
                year += 1900
            elif ( 0 <= year < 70):
                year += 2000
            # Use DB server as time base
            now = db_clock_time(db_session)
            try:
                target_time = datetime.time(hour, minute, tzinfo=now.tzinfo)
                target_date = datetime.date(year, month, day)
                target_ctime = datetime.datetime.combine(target_date,
                        target_time)
            except ValueError:
                raise ZiIdHhMmSyntaxError(zi_id)
            return ctime_query(target_ctime)

        # Easy as pie and basket case, quicker to do first
        if zone_sm:
            if not zi_id or zi_id == '^':
                return zone_sm.zi
        else:
            if not zi_id:
                return None
        
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        # Fast path - check and see if zi_id is a straight integer
        query = new_query()
        try:
            zi_id = int(zi_id)
            zi = query.filter(ZoneInstance.id_ == zi_id).one()
            return zi
        except NoResultFound:
            return None
        except ValueError:
            pass
        if specific_zi_id:
            return None
        
        # Put the brakes on
        # Only zone_tool related parsing from here on 
        if (self.sectag.sectag != settings['admin_sectag'] 
                and settings['process_name'] != 'zone_tool'):
            return None

        # Try
        match_adj = self._zi_adj_re.search(zi_id)
        if match_adj:
            adj_str = match_adj.group(1)
            pivot_zi_id = zone_sm.zi.id_
            return resolv_adj_str(adj_str)
        
        # Has to be done here as regexp is greedy
        # Try nnn[smhdw] 
        match_unit = self._zi_unit_re.search(zi_id)
        if match_unit:
            amount = match_unit.group(1)
            unit = match_unit.group(2)
            try:
                amount = float(amount)
            except ValueError:
                raise ZiIdTimeAmountSyntaxError(zi_id)
            # Use DB server as time base
            now = db_clock_time(db_session)
            try:
                if unit == 's':
                    delta_time = datetime.timedelta(seconds=amount)
                elif unit == 'm':
                    delta_time = datetime.timedelta(minutes=amount)
                elif unit == 'h':
                    delta_time = datetime.timedelta(hours=amount)
                elif unit == 'd':
                    delta_time = datetime.timedelta(days=amount)
                elif unit == 'w':
                    delta_time = datetime.timedelta(weeks=amount)
                else:
                    raise ZiIdTimeUnitSyntaxError(zi_id)
            except ValueError:
                raise ZiIdTimeAmountSyntaxError(zi_id)
            target_ctime = now - delta_time
            query = query.filter(ZoneInstance.ctime <= target_ctime)\
                        .order_by(ZoneInstance.ctime.desc()).limit(1)
            try:
                result = query.one()
            except NoResultFound:
                result = None
            return result
        
        # Try DD/MM/YYYY,hh:mm
        match_ddmmyyyy_hhmm = self._zi_ddmmyyyy_hhmm_re.search(zi_id)
        if match_ddmmyyyy_hhmm:
            return do_year_date_time(match_ddmmyyyy_hhmm,
                                    ZiIdDdMmYyyySyntaxError,
                                    iso_format_date=False)
        # Try YYYY-MM-DD,hh:mm
        match_iso_date_hhmm = self._zi_iso_date_hhmm_re.search(zi_id)
        if match_iso_date_hhmm:
            return do_year_date_time(match_iso_date_hhmm,
                                    ZiIdIsoDateSyntaxError,
                                    iso_format_date=True)
        # Try DD/MM/YYYY
        match_ddmmyyyy = self._zi_ddmmyyyy_re.search(zi_id)
        if match_ddmmyyyy:
            return do_year_date_time(match_ddmmyyyy, ZiIdDdMmYyyySyntaxError,
                                    iso_format_date=False)
        # Try YYYY-MM-DD
        match_iso_date = self._zi_iso_date_re.search(zi_id)
        if match_iso_date:
            return do_year_date_time(match_iso_date, ZiIdIsoDateSyntaxError,
                                    iso_format_date=True)

        # Try DD/MM
        match_ddslashmm = self._zi_ddslashmm_re.search(zi_id)
        if match_ddslashmm:
            day = match_ddslashmm.group(1)
            month = match_ddslashmm.group(2)
            try:
                day = int(day)
            except ValueError:
                raise ZiIdDdSlashMmSyntaxError(zi_id)
            try:
                month = int(month)
            except ValueError:
                raise ZiIdDdSlashMmSyntaxError(zi_id)
            now = db_clock_time(db_session)
            midnight = datetime.time(0, 0, 0, tzinfo=now.tzinfo)
            now_year = now.year
            last_year = now_year - 1
            try:
                target_date = datetime.date(now_year, month, day)
                target_ctime = datetime.datetime.combine(target_date, midnight)
                if target_ctime > now:
                    target_date = datetime.date(last_year, month, day)
                    target_ctime = datetime.datetime.combine(target_date,
                            midnight)
            except ValueError:
                raise ZiIdDdSlashMmSyntaxError(zi_id)
            return ctime_query(target_ctime)

        # Try HH:MM
        match_hhmm = self._zi_hhmm_re.search(zi_id)
        if match_hhmm:
            match_args = match_hhmm.groups()
            hour = match_args[0]
            minute = match_args[1]
            try:
                hour = int(hour)
            except ValueError:
                raise ZiIdHhMmSyntaxError(zi_id)
            try:
                minute = int(minute)
            except ValueError:
                raise ZiIdHhMmSyntaxError(zi_id)
            # Process AM/PM
            if len(match_args) > 2 and match_args[2]:
                am_pm = match_args[2].lower()
                if (am_pm.startswith('p') and hour < 12):
                    hour += 12
            # Use DB server as time base
            now = db_clock_time(db_session)
            now_date = now.date()
            try:
                target_time = datetime.time(hour, minute, tzinfo=now.tzinfo)
                yesterday_date = now_date - datetime.timedelta(days=1)
                target_ctime = datetime.datetime.combine(now_date, target_time)
                if target_ctime > now:
                    # Use yesterday
                    target_ctime = datetime.datetime.combine(yesterday_date, 
                            target_time)
            except ValueError:
                raise ZiIdHhMmSyntaxError(zi_id) 
            return ctime_query(target_ctime)
    
        # Try nnn+++/---/+n/-n
        match_int_adj = self._zi_int_adj_re.search(zi_id)
        if match_int_adj:
            pivot_zi_id = match_int_adj.group(1)
            adj_str = match_int_adj.group(2)
            return resolv_adj_str(adj_str)
        
        # Can't understand whats been given
        raise ZiIdSyntaxError(zi_id)

    def list_zi(self, name):
        """
        Given a zone name, return all its zis briefly, 
        fully showing the currently active one.
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        result = zone_sm.to_engine(time_format=self.time_format)
        if zone_sm.zi:
            result['zi'] = zone_sm.zi.to_engine(time_format=self.time_format)
        # Ineffecient but portable code:
        #result['all_zis'] = list(zone_sm.all_zis)
        #result['all_zis'].sort(key=(lambda zi : zi.mtime))
        #result['all_zis'] = [zi.to_engine_brief(time_format=self.time_format)
        #                        for zi in zone_sm.all_zis]
        # Efficient code:
        result['all_zis'] = [zi.to_engine_brief(time_format=self.time_format)
                        for zi in zone_sm.all_zis.order_by(ZoneInstance.ctime)]
        return result

    def _get_comment(self, comment_id):
        """
        Give a comment ID, get the contents of the comment
        """
        db_session = self.db_session
        result = db_session.query(RRComment) \
                .filter(RRComment.id_ == comment_id).one()
        if result:
            rr_comment = result[0].comment
        else:
            rr_comment = None
        return rr_comment

    def _show_zone(self, zone_sm, zi_id=None, all_rrs=False):
        """
        Given a zone_sm, return all the values stored in its ZoneSM
        record, current zi, RRs, and comments
        """
        if not zone_sm:
            return {}
        result = zone_sm.to_engine(time_format=self.time_format)
        if self.sectag.sectag == settings['admin_sectag']:
            result['sectags'] = zone_sm.list_sectags(self.db_session)
        # This is a bit rabbit-pathed, but it works...
        zi = self._resolv_zi_id(zone_sm, zi_id)
        if not zi:
            raise ZiNotFound(zone_sm.name, zi_id)
        result['zi'] = zi.to_data(self.time_format,
                                        zone_sm.use_apex_ns, all_rrs)
        # Note alternative code up in list_zi() for different relN loading
        # strategy
        result['all_zis'] = [zi.to_engine_brief(time_format=self.time_format)
                        for zi in zone_sm.all_zis.order_by(ZoneInstance.ctime)]
        return result

    def show_zone(self, name, zi_id=None):
        """
        Given a zone name, return all the values stored in its ZoneSM
        record, current zi, RRs, and comments
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        return self._show_zone(zone_sm, zi_id)
    
    def show_zone_byid(self, zone_id, zi_id=None):
        """
        Given a zone id, return all the values stored in its ZoneSM
        record, current zi, RRs, and comments
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm_byid(zone_id)
        return self._show_zone(zone_sm, zi_id)

    def show_zone_text(self, name, zi_id=None, all_rrs=True):
        """
        Given a zone name and optional zi_id, return the ZI as zone file text
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        result = {}
        zone_sm = self._get_zone_sm(name)
        data_result = self._show_zone(zone_sm, zi_id, all_rrs=all_rrs)
        result['zi_text'] = data_to_bind(data_result['zi'], 
                                name=data_result['name'], 
                                reference=data_result.get('reference'))
        result['name'] = data_result['name']
        result['zi_id'] = data_result['zi']['zi_id']
        result['zi_ctime'] = data_result['zi']['ctime']
        result['zi_mtime'] = data_result['zi']['mtime']
        result['zi_ptime'] = data_result['zi']['ptime']
        result['soa_serial'] = data_result['zi']['soa_serial']
        result['zone_id'] = data_result['zone_id']
        return result

    def show_zi(self, name, zi_id=None):
        """
        Given a domain name and optionally a zi_id, return all values
        stored in ZoneInstance record
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        zi = self._resolv_zi_id(zone_sm, zi_id)
        if not zi:
            raise ZiNotFound(name, zi_id)
        result = zi.to_engine(time_format=self.time_format)
        return result

    def show_zi_byid(self, zi_id):
        """
        Given a zi_id, return all values stored in ZoneInstance record
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zi = self._get_zi(zi_id)
        result = zi.to_engine(time_format=self.time_format)
        return result

    def _edit_zone(self, name, login_id, zi_id=None, all_rrs=False,
                    admin_privilege=False):
        """
        Backend for zone editing.

        Start editing a zone, by returning editing data

        If zone has edit locking enabled, change state and obtain a
        token
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        locked_by = self._make_change_by(login_id)
        zone_sm = self._get_zone_sm(name)
        # Privilege check for no apex zones - admin only 
        if not zone_sm.use_apex_ns and not admin_privilege:
            raise ZoneAdminPrivilegeNeeded(name)
        edit_lock_token = None
        if zone_sm.edit_lock:
            # This is where we synchronously call the Zone_sm state
            # machine Have to obtain lock before getting current data
            lock_results = exec_zonesm(zone_sm, ZoneSMEdit, EditLockFailure,
                    locked_by=locked_by)
            edit_lock_token = lock_results['edit_lock_token']
       
        # All locking now done, get zone data and return it!
        try:
            zone_zi_data = self._show_zone(zone_sm, zi_id, all_rrs)
        except ZoneNotFound:
            # If fail to obtain data release edit lock
            if zone_sm.state == ZLSTATE_EDIT_LOCK:
                #Cancel Edit lock
                exec_zonesm(zone_sm, ZoneSMEditExit, 
                            edit_lock_token=edit_lock_token)
            raise
        # return with THE HIDDEN TREASURE
        return zone_zi_data, edit_lock_token

    def edit_zone(self, name, login_id, zi_id=None):
        """
        Start editing a zone, by returning editing data

        If zone has edit locking enabled, change state and obtain a
        token
        """
        return self._edit_zone(name, login_id, zi_id)
    
    def edit_zone_admin(self, name, login_id, zi_id=None):
        """
        Start editing a zone, by returning editing data

        If zone has edit locking enabled, change state and obtain a
        token
        """
        return self._edit_zone(name, login_id, zi_id, all_rrs=True,
                                admin_privilege=True)

    def tickle_editlock(self, name, edit_lock_token=None):
        """
        Tickle the edit_lock timeout event
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)

        exec_zonesm(zone_sm, ZoneSMEditLockTickle, 
                    TickleEditLockFailure,
                    edit_lock_token=edit_lock_token)
        return True

    def cancel_edit_zone(self, name, edit_lock_token=None):
        """
        Operation to cancel an edit locked session
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        cancel_results = exec_zonesm(zone_sm, ZoneSMEditExit,
                                    CancelEditLockFailure,
                                    edit_lock_token=edit_lock_token)
        return True

    def _update_zone(self, name, zi_data, login_id, edit_lock_token=None,
            normalize_ttls=False, admin_privilege=False,
            helpdesk_privilege=False):
        """
        Backend for updating the zone by adding a new ZI,
        and emitting a publish event
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        change_by = self._make_change_by(login_id)
        zone_sm = self._get_zone_sm(name, exact_network=True)
        # Privilege check for no apex zones - admin only 
        if not zone_sm.use_apex_ns and not admin_privilege:
            raise ZoneAdminPrivilegeNeeded(name)
        # Save data
        zi, auto_ptr_data = self._data_to_zi(name, zi_data, change_by,
                                normalize_ttls, 
                                admin_privilege, helpdesk_privilege)
        # put zi in place, issue appropriate zone SM event
        if not zone_sm.edit_lock:
            exec_zonesm(zone_sm, ZoneSMEditSavedNoLock,
                                zi_id=zi.id_)

            # Do auto_ptr_data operation here.
            self._queue_auto_ptr_data(auto_ptr_data)
            return True

        try:
            exec_zonesm(zone_sm, ZoneSMEditSaved,
                                UpdateZoneFailure,
                                zi_id=zi.id_,
                                edit_lock_token=edit_lock_token)
        except UpdateZoneFailure as exc:
            # Remove zi as we don't want to keep it around
            # - Obviates edit locking in the first place.
            self.db_session.delete(zi)
            self.db_session.commit()
            raise
        
        # Do auto_ptr_data operation here.
        self._queue_auto_ptr_data(auto_ptr_data)
        return True
        
    def _update_zone_text(self, name, zi_text, login_id, edit_lock_token=None,
            normalize_ttls=False, admin_privilege=False,
            helpdesk_privilege=False):
        """
        Backend for updating the zone by adding a new ZI as a text blob,
        and emitting a publish event
        """
        zi_data, origin_name, update_type, zone_reference \
                                = self._parse_zi_text(name, zi_text)
        # Use normalize_ttls with imported data to stop surprises
        results = self._update_zone(name=name, login_id=login_id, 
                            zi_data=zi_data, edit_lock_token=edit_lock_token,
                            normalize_ttls=normalize_ttls,
                            admin_privilege=admin_privilege,
                            helpdesk_privilege=helpdesk_privilege)
        return results

    def update_zone_admin(self, name, zi_data, login_id, edit_lock_token=None, 
                            normalize_ttls=False):
        """
        Update a zone with admin privilege
        """
        return self._update_zone(name, zi_data, login_id, edit_lock_token, 
                    normalize_ttls, admin_privilege=True)

    def update_zone_text_admin(self, name, zi_text, login_id, 
                            edit_lock_token=None, normalize_ttls=False):
        """
        Update a zone with admin privilege
        """
        return self._update_zone_text(name, zi_text, login_id, 
                            edit_lock_token, normalize_ttls, 
                            admin_privilege=True)

    def _find_src_zi(self, src_name, src_zi_id, admin_privilege):
        """
        Find a src_zi, src_zone_sm given a name and zi_id

        Common peice of code between _create_zone and _copy_zi
        """
        db_session = self.db_session
        src_zone_sm = None
        src_zi = None
        if src_name:
            src_zone_sm = self._get_zone_sm(src_name)
            src_zi = self._resolv_zi_id(src_zone_sm, src_zi_id)
            if not src_zi:
                raise ZiNotFound(src_zone_sm.name, src_zi_id)
        elif src_zi_id and admin_privilege:
            src_zi = self._resolv_zi_id(None, src_zi_id,
                            specific_zi_id=True)
            if not src_zi:
                raise ZiNotFound('*', src_zi_id)
        return src_zone_sm, src_zi


    def _copy_src_zi(self, src_zi, zone_sm, change_by,
                    preserve_time_stamps=False):
        """
        Given a src_zi, copy it

        Common peice of code between _create_zone and _copy_zi
        """
        db_session = self.db_session
        if preserve_time_stamps:
            src_ctime = src_zi.ctime
            src_mtime = src_zi.mtime
        zi = src_zi.copy(db_session, change_by)
        auto_ptr_data = zi.get_auto_ptr_data(zone_sm)
        # Tie to zone
        zi.zone = zone_sm
        zone_sm.all_zis.append(zi)
        db_session.flush()
        # Update apex if needed
        zi.update_apex(db_session)
        # Update Zone TTLs for clean initialisation
        zi.update_zone_ttls()
        # Make sure SOA serial number is fresh
        new_soa_serial = new_soa_serial_no(zi.soa_serial, zone_sm.name)
        zi.update_soa_serial(new_soa_serial)
        if preserve_time_stamps:
            zi.ctime = src_ctime
            zi.mtime = src_mtime
        db_session.flush()
        return zi, auto_ptr_data

    def _create_zone(self, name, zi_data, login_id,
                        use_apex_ns, edit_lock, auto_dnssec, nsec3, 
                        inc_updates,
                        reference=None, sg_name=None, sectags=None,
                        batch_load=False, src_name=None, src_zi_id=None,
                        admin_privilege=False,
                        helpdesk_privilege=False):
        """
        Given a name, create a zone

        Currently just creates a row in the sm_zone table, as well as
        initial zi (provided or default), leaving  zone_sm.state as UNCONFIG
        """

        def check_parent_domains(name):
            """
            Handle all checks for when creating sub domain

            ie - only allow sub domain creation for like references etc
            """
            nonlocal reference

            # Check if sub domain exists
            parent_name_list = name.split('.')[1:]
            while (len(parent_name_list) > 1):
                parent_name  = '.'.join(parent_name_list)
                parent_name_list = parent_name_list[1:]
                try:
                    parent_zone_sm = self._get_zone_sm(parent_name,
                            check_sectag=False, exact_network=True)
                except ZoneNotFound:
                    continue
                parent_zone_ref = parent_zone_sm.reference
                if self.sectag.sectag == settings['admin_sectag']:
                    # admin can do anything - creating a sub domain 
                    # with any reference defaulting to that of parent
                    if not reference:
                        reference = parent_zone_ref.reference \
                            if hasattr(parent_zone_ref, 'reference') \
                                and parent_zone_ref.reference \
                            else None
                    return
                if not reference:
                    reference = zone_cfg.get_row_exc(db_session, 'default_ref')
                ref_obj = new_reference(db_session, reference,
                        return_existing=True)
                if parent_zone_ref and ref_obj != parent_zone_ref:
                    raise ZoneExists(name)
                return
            return

        self._begin_op()
        db_session = self.db_session
       
        # Login ID must be checked and processed
        change_by = self._make_change_by(login_id)

        # If given source information for copying into creation ZI, check
        # it out.
        src_zone_sm, src_zi = self._find_src_zi(src_name, src_zi_id, 
                                admin_privilege)

        try:
            # No point in hiding existence of zone if asked directly with 
            # name when creating a zone.
            zone_sm = self._get_zone_sm(name, check_sectag=False, 
                            exact_network=True)
            # reached the end of the road...
            raise ZoneExists(name)
        except ZoneNotFound:
            # Inverted exception
            pass

        # Check name syntax and convert networks to valid reverse domain names
        reverse_network = None
        if name.find('/') > -1:
            result = zone_name_from_network(name)
            if not result:
                raise InvalidDomainName(name)
            rev_name, rev_network = result
            reverse_network = new_reverse_network(db_session, rev_network)
            name = rev_name
            inc_updates = True if inc_updates == None else inc_updates
        elif (name.lower().endswith('ip6.arpa.') 
                or name.lower().endswith('in-addr.arpa.')):
            raise ReverseNamesNotAccepted(name)
        elif not is_inet_domain(name):
            raise InvalidDomainName(name)

        # Check parent domains when creating a sub domain
        check_parent_domains(name)

        # Set reference if copying and none given.
        # Parent domains will override this
        if src_zone_sm and not reference:
            if src_zone_sm.reference and src_zone_sm.reference.reference:
                reference = src_zone_sm.reference.reference

        # Check that the security tag exists
        sectag = self.sectag
        if not sectag in list_all_sectags(db_session):
            raise ZoneSecTagDoesNotExist(sectag.sectag)

        # If copying zone, set zone flags from src if not given
        if src_zone_sm:
            if use_apex_ns is None:
                use_apex_ns = src_zone_sm.use_apex_ns
            if edit_lock is None:
                edit_lock = src_zone_sm.edit_lock
            if auto_dnssec is None:
                auto_dnssec = src_zone_sm.auto_dnssec
            if nsec3 is None:
                nsec3 = src_zone_sm.nsec3
            if inc_updates is None:
                inc_updates = src_zone_sm.inc_updates

        # create the zone
        zone_sm = new_zone(db_session, DynDNSZoneSM, name=name, 
                    use_apex_ns=use_apex_ns, edit_lock=edit_lock,
                    auto_dnssec=auto_dnssec, nsec3=nsec3,
                    inc_updates=inc_updates, sectag=self.sectag,
                    sg_name=sg_name, reference=reference)
        # Add extra sectags
        if sectags:
            if self.sectag.sectag == settings['admin_sectag']:
                self.replace_zone_sectags(name, sectags)
            else:
                raise SecTagPermissionDenied(self.sectag.sectag)
        
        # If Admin and copying, copy sectags from source zone
        if self.sectag.sectag == settings['admin_sectag']:
            if src_zone_sm:
                zone_sm.copy_zone_sectags(db_session, src_zone_sm)

        # Fill out zi
        if src_zi:
            zi, auto_ptr_data = self._copy_src_zi(src_zi, zone_sm, change_by)
        elif zi_data:
            zi, auto_ptr_data = self._data_to_zi(name, zi_data,
                                change_by=change_by,
                                admin_privilege=admin_privilege, 
                                helpdesk_privilege=helpdesk_privilege,
                                normalize_ttls=True)
            # Set new SOA serial if it is old.  This is for load_zone(s), and
            # new incoming domains
            new_soa_serial = new_soa_serial_no(zi.soa_serial, name)
            zi.update_soa_serial(new_soa_serial)
        else:
            zi = new_zone_zi(db_session, zone_sm, change_by)
            auto_ptr_data = None

        zone_sm.soa_serial = zi.soa_serial
        # Add reverse network if that exists
        if reverse_network:
            zone_sm.reverse_network = reverse_network
        # Get commands going with working backend first
        if (batch_load and not zone_sm.auto_dnssec):
            exec_zonesm(zone_sm, ZoneSMDoBatchConfig, zi_id=zi.id_)
        else:
            exec_zonesm(zone_sm, ZoneSMDoConfig, zi_id=zi.id_)

        # Do auto_ptr_data operation here.
        self._queue_auto_ptr_data(auto_ptr_data)
        # Commit everything.
        self._finish_op()
        return True

    def create_zone_admin(self, name, login_id, zi_data=None, 
                use_apex_ns=None, edit_lock=None, auto_dnssec=None,
                nsec3=None, inc_updates=None, reference=None, sg_name=None,
                sectags=None):
        """
        Create a zone with admin privilege
        """
        return self._create_zone(name, zi_data, login_id, use_apex_ns,
                edit_lock, auto_dnssec, nsec3, inc_updates, 
                reference, sg_name, sectags, admin_privilege=True)

    def copy_zone_admin(self, src_name, name, login_id, zi_id=None, 
                use_apex_ns=None, edit_lock=None, auto_dnssec=None,
                nsec3=None, inc_updates=None, reference=None, sg_name=None,
                sectags=None):
        """
        Create a zone with admin privilege
        """
        return self._create_zone(name, src_name=src_name, src_zi_id=zi_id,
                use_apex_ns=use_apex_ns, edit_lock=edit_lock, 
                auto_dnssec=auto_dnssec, nsec3=nsec3, inc_updates=inc_updates, 
                reference=reference, sg_name=sg_name, sectags=sectags,
                login_id=login_id, zi_data=None, admin_privilege=True)

    def destroy_zone(self, zone_id):
        """
        Destroy a zone backend
        """
        self._begin_op()
        zone_sm = self._get_zone_sm_byid(zone_id)
        
        if not zone_sm.is_deleted():
            raise ZoneNotDeleted(zone_sm.name)

        # Delete the zone
        # Database integrity constraints/triggers will do all the rest...
        exec_zonesm(zone_sm, ZoneSMDoDestroy, ZoneFilesStillExist)
        self._finish_op()
        return True

    def delete_zone(self, name):
        """
        Delete a zone backend
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        exec_zonesm(zone_sm, ZoneSMDelete, ZoneBeingCreated)
        self._finish_op()        

    def undelete_zone(self, zone_id):
        """
        Delete a zone backend
        """
        self._begin_op()
        zone_sm = self._get_zone_sm_byid(zone_id)
        exec_zonesm(zone_sm, ZoneSMUndelete, ActiveZoneExists)
        self._finish_op()

    def copy_zi(self, src_name, name, login_id, zi_id=None):
        """
        Copy a zi from src_zone to destination zone
        """
        self._begin_op()
        change_by = self._make_change_by(login_id)
        src_zone_sm, src_zi = self._find_src_zi(src_name, zi_id, 
                                admin_privilege=False)
        zone_sm = self._get_zone_sm(name)
        self._copy_src_zi(src_zi, zone_sm, change_by, 
                        preserve_time_stamps=True)
        self._finish_op()

    def delete_zi(self, name, zi_id):
        """
        Given a zone name and zi_id, delete the zi_id
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        
        if zone_sm.zi_id == zi_id:
            raise ZiInUse(name, zi_id)
        zi = self._resolv_zi_id(zone_sm, zi_id, specific_zi_id=True)
        if not zi:
            raise ZiNotFound(name, zi_id)
        self.db_session.delete(zi)
        self._finish_op()

    def _parse_zi_text(self, name, zi_text):
        """
        Backend function to parse zi_text and trap/translate PyParsing
        exceptions.
        """
        zone_stringio = StringIO(initial_value=zi_text)
        try:
            return bind_to_data(zone_stringio, name)
        except ParseBaseException as exc:
            raise ZiTextParseError(name, exc)

    def _load_zone(self, name, zi_text, login_id,
                        use_apex_ns, edit_lock, auto_dnssec, nsec3, 
                        inc_updates,
                        reference=None, sg_name=None, sectags=None,
                        admin_privilege=False,
                        helpdesk_privilege=False):
        """
        Load a zone from a zi_text blob. Backend.
        """
        zi_data, origin_name, update_type, zone_reference \
                        = self._parse_zi_text(name, zi_text)
        if not reference:
            reference = zone_reference
        results = self._create_zone(name, zi_data, login_id,
                        use_apex_ns, edit_lock, auto_dnssec, nsec3, 
                        inc_updates,
                        reference, sg_name, sectags,
                        admin_privilege=admin_privilege,
                        helpdesk_privilege=helpdesk_privilege)
        return results

    def _load_zi(self, name, zi_text, login_id, admin_privilege=False,
            helpdesk_privilege=False):
        """
        Load a ZI into a zone. Backend.
        """
        zone_sm_data, edit_lock_token = self._edit_zone(name=name,
                                login_id=login_id, 
                                admin_privilege=admin_privilege)
        zi_data, origin_name, update_type, zone_reference \
                                = self._parse_zi_text(name, zi_text)
        # Use normalize_ttls with imported data to stop surprises
        load_results = self._update_zone(name=name, login_id=login_id, 
                            zi_data=zi_data, edit_lock_token=edit_lock_token,
                            normalize_ttls=True,
                            admin_privilege=admin_privilege,
                            helpdesk_privilege=helpdesk_privilege)
        return load_results

    def _set_zone(self, name, **kwargs):
        """
        Set the settable attributes on a zone.  This call also issues
        an event to update the zone.
        """
        for arg in kwargs:
            if arg not in ('use_apex_ns', 'edit_lock', 'auto_dnssec', 'nsec3',
                            'inc_updates'):
                raise InvalidParamsJsonRpcError("Argument '%s' not supported."
                                                    % arg)

        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
       
        if 'use_apex_ns' in kwargs:
            use_apex_ns = kwargs['use_apex_ns']
            if use_apex_ns == None:
                use_apex_ns = zone_cfg.get_key(self.db_session, 'use_apex_ns')
            if use_apex_ns == True:
                if not zone_sm.use_apex_ns:
                    zone_sm.use_apex_ns = True
                    create_event(ZoneSMUpdate, commit=True,
                            signal_queue_daemon=True, 
                            sm_id=zone_sm.id_, zone_id=zone_sm.id_,
                            name=zone_sm.name)
            elif use_apex_ns == False:
                if zone_sm.use_apex_ns:
                    zone_sm.use_apex_ns = False
                    create_event(ZoneSMUpdate, commit=True,
                            signal_queue_daemon=True, 
                            sm_id=zone_sm.id_, zone_id=zone_sm.id_,
                            name=zone_sm.name)
            else:
                assert(False)

        if 'edit_lock' in kwargs:
            edit_lock = kwargs['edit_lock']
            if edit_lock == None:
                edit_lock = zone_cfg.get_key(self.db_session, 'edit_lock')
            if edit_lock == True:
                zone_sm.edit_lock = True
            elif edit_lock == False:
                zone_sm.edit_lock = False
            elif edit_lock == None:
                pass
            else:
                assert(False)

        if 'inc_updates' in kwargs:
            inc_updates = kwargs['inc_updates']
            if inc_updates == None:
                inc_updates = zone_cfg.get_key(self.db_session, 'inc_updates')
            if inc_updates == True:
                zone_sm.inc_updates = True
            elif inc_updates == False:
                zone_sm.inc_updates = False
            elif inc_updates == None:
                pass
            else:
                assert(False)

        if 'auto_dnssec' in kwargs:
            auto_dnssec = kwargs['auto_dnssec']
            if auto_dnssec == None:
                auto_dnssec = zone_cfg.get_key(self.db_session, 'auto_dnssec')
            if auto_dnssec == True:
                if not zone_sm.auto_dnssec:
                    zone_sm.auto_dnssec = True
                    exec_zonesm(zone_sm, ZoneSMDoReconfig)
            elif auto_dnssec == False:
                if zone_sm.auto_dnssec:
                    zone_sm.auto_dnssec = False
                    exec_zonesm(zone_sm, ZoneSMDoReconfig)
            elif auto_dnssec == None:
                pass
            else:
                assert(False)

        if 'nsec3' in kwargs:
            nsec3 = kwargs['nsec3']
            if nsec3 == None:
                nsec3 = zone_cfg.get_key(self.db_session, 'nsec3')
            if nsec3 == True:
                if not zone_sm.nsec3:
                    zone_sm.nsec3 = True
                    if zone_sm.auto_dnssec:
                        exec_zonesm(zone_sm, ZoneSMDoReconfig)
            elif nsec3 == False:
                if zone_sm.nsec3:
                    zone_sm.nsec3 = False
                    if zone_sm.auto_dnssec:
                        exec_zonesm(zone_sm, ZoneSMDoReconfig)
            elif nsec3 == None:
                pass
            else:
                assert(False)
        self._finish_op()
        return

    def set_zone_admin(self, name, **kwargs):
        return self._set_zone(name, **kwargs)

    def show_sectags(self):
        """
        Return all security tags as JSON
        """
        if self.sectag.sectag != settings['admin_sectag']:
            raise SecTagPermissionDenied(self.sectag.sectag)
        self._begin_op()
        result = []
        all_sectags = list_all_sectags(self.db_session)
        if not len(all_sectags):
            raise NoSecTagsExist()
        for sectag in all_sectags:
            result.append(sectag.to_engine(self.time_format))
        self._finish_op()
        return result

    def show_zone_sectags(self, name):
        """
        Return all the sectags configured for a zone
        """
        if self.sectag.sectag != settings['admin_sectag']:
            raise SecTagPermissionDenied(self.sectag.sectag)
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        result = zone_sm.list_sectags(self.db_session)
        if not result:
            raise NoZoneSecTagsFound(name)
        self._finish_op()
        return result

    def add_zone_sectag(self, name, sectag_label):
        """
        Add a sectag to a zone
        """
        if self.sectag.sectag != settings['admin_sectag']:
            raise SecTagPermissionDenied(self.sectag.sectag)
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        sectag = ZoneSecTag(sectag_label)
        if sectag not in list_all_sectags(self.db_session):
            raise ZoneSecTagDoesNotExist(sectag_label)
        result = zone_sm.add_sectag(self.db_session, sectag)
        self._finish_op()
    
    def delete_zone_sectag(self, name, sectag_label):
        """
        Add a sectag to a zone
        """
        if self.sectag.sectag != settings['admin_sectag']:
            raise SecTagPermissionDenied(self.sectag.sectag)
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        sectag = ZoneSecTag(sectag_label)
        if sectag not in list_all_sectags(self.db_session):
            raise ZoneSecTagDoesNotExist(sectag_label)
        result = zone_sm.remove_sectag(self.db_session, sectag)
        self._finish_op()

    def replace_zone_sectags(self, name, sectag_labels):
        """
        Replace all sectags for given zone
        """
        if self.sectag.sectag != settings['admin_sectag']:
            raise SecTagPermissionDenied(self.sectag.sectag)
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        sectag_list = []
        all_sectags = list_all_sectags(self.db_session)
        for sectag_thing in sectag_labels:
            try:
                sectag = ZoneSecTag(sectag_thing['sectag_label'])
            except (TypeError, IndexError):
                raise InvalidParamsJsonRpcError('Sectag list format invalid.')
            if sectag not in all_sectags:
                raise ZoneSecTagDoesNotExist(sectag_thing['sectag_label'])
            sectag_list.append(sectag)
        result = zone_sm.replace_all_sectags(self.db_session, *sectag_list)
        self._finish_op()
   
    def enable_zone(self, name):
        """
        Enable a zone
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        exec_zonesm(zone_sm, ZoneSMEnable)
        self._finish_op()


    def disable_zone(self, name):
        """
        Disable a zone
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        exec_zonesm(zone_sm, ZoneSMDisable)
        self._finish_op()

    def show_mastersm(self):
        """
        Show the MasterSM
        """
        self._begin_op()
        result = show_master_sm(self.db_session, time_format=self.time_format)
        self._finish_op()
        return result

    def sign_zone(self, name):
        """
        Schedule a zone for signing event
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if not zone_sm.auto_dnssec:
            raise ZoneNotDnssecEnabled(name)
        zone_sm_dnssec_schedule(self.db_session, zone_sm, 'sign')
        self._finish_op()
    
    def loadkeys_zone(self, name):
        """
        Schedule a zone key loading event
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if not zone_sm.auto_dnssec:
            raise ZoneNotDnssecEnabled(name)
        zone_sm_dnssec_schedule(self.db_session, zone_sm, 'loadkeys')
        self._finish_op()

    def reset_zone(self, name, zi_id=None):
        """
        Schedule a zone reset event
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        reset_args = {}
        if zi_id:
            zi = self._resolv_zi_id(zone_sm, zi_id, specific_zi_id=False)
            if not zi:
                raise ZiNotFound(zone_sm.name, zi_id)
            reset_args['zi_id'] = zi.id_
        results = exec_zonesm(zone_sm, ZoneSMDoReset, **reset_args)
        self._finish_op()

    def refresh_zone(self, name, zi_id=None):
        """
        Refresh a zone by issuing an update.
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        refresh_args = {}
        if zi_id:
            zi = self._resolv_zi_id(zone_sm, zi_id, specific_zi_id=False)
            if not zi:
                raise ZiNotFound(zone_sm.name, zi_id)
            refresh_args['zi_id'] = zi.id_
            results = exec_zonesm(zone_sm, ZoneSMDoRefresh, 
                    exception_type=UpdateZoneFailure, **refresh_args)
        else:
            results = exec_zonesm(zone_sm, ZoneSMDoRefresh, **refresh_args)
        self._finish_op()

    def poke_zone_set_serial(self, name, soa_serial=None,
                                            force_soa_serial_update=False):
        """
        Set zone SOA serial number to given value if possible
        """
        return self._poke_zone(name, soa_serial=soa_serial,
                            force_soa_serial_update=force_soa_serial_update)

    def poke_zone_wrap_serial(self, name):
        """
        Wrap current zone SOA serial number
        """
        return self._poke_zone(name, wrap_soa_serial=True)

    def _poke_zone(self, name, soa_serial=None,
                                wrap_soa_serial=False,
                                force_soa_serial_update=False):
        """
        Manipulate a zone's serial number on the DNS servers via update.
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        if zone_sm.state != ZSTATE_PUBLISHED:
            raise ZoneNotPublished(name)
        # If candidate serial given, test it
        if soa_serial:
            # Check that incoming argument is an integer
            if not isinstance(soa_serial, int):
                raise SOASerialTypeError(name)
            if not ( 0 < soa_serial <= (2**32 -1 )):
                raise SOASerialRangeError(name)
            # Assume that current is previously published SOA serial
            test_soa_serial = new_soa_serial_no(zone_sm.soa_serial, name,
                    candidate=soa_serial)
            if test_soa_serial != soa_serial:
                raise SOASerialCandidateIgnored(name)
        refresh_args = {'candidate_soa_serial': soa_serial, 
                        'wrap_soa_serial': wrap_soa_serial,
                        'force_soa_serial_update': force_soa_serial_update}
        results = exec_zonesm(zone_sm, ZoneSMDoRefresh, 
                exception_type=UpdateZoneFailure, **refresh_args)
        self._finish_op()

    def create_reference(self, reference):
        """
        Create a new reference
        """
        self._begin_op()
        new_reference(self.db_session, reference)
        self._finish_op()

    def delete_reference(self, reference):
        """
        Delete a reference
        """
        self._begin_op()
        del_reference(self.db_session, reference)
        self._finish_op()

    def rename_reference(self, reference, dst_reference):
        """
        Rename a reference
        """
        self._begin_op()
        rename_reference(self.db_session, reference, dst_reference)
        self._finish_op()
    
    def list_reference(self, *references):
        """
        List references
        """
        self._begin_op()
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        if not references:
            references = '*'
        ref_list = []
        ref_pattern = ' '.join(references)
        references = [x.replace('*', '%') for x in references]
        references = [x.replace('?', '_') for x in references]
        for ref in references:
            query = self.db_session.query(Reference)\
                    .filter(Reference.reference.ilike(ref))\
                    .yield_per(db_query_slice)
            for ref in query:
                ref_list.append(ref.to_engine_brief())
        if not ref_list:
            raise NoReferenceFound('*')
        ref_list = sorted(ref_list, 
                key=lambda reference: reference['reference'].lower())
        self._finish_op()
        return ref_list

    def set_zone_reference(self, name, reference=None):
        """
        Set the reference for a zone
        """
        self._begin_op()
        db_session = self.db_session
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if reference:
            reference = find_reference(db_session, reference)
            reference.set_zone(zone_sm)
        else:
            zone_sm.ref_id = None
        self._finish_op()

    def list_sg(self):
        """
        List all server groups
        """
        self._begin_op()
        sgs = self.db_session.query(ServerGroup).all()
        result = []
        for sg in sgs:
            result.append(sg.to_engine_brief())
        if not result:
            raise NoSgFound('*')
        self._finish_op()
        return result

    def set_zone_sg(self, name, sg_name=None):
        """
        Set the SG a zone is associated with
        """
        self._begin_op()
        db_session = self.db_session
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if not zone_sm.is_disabled():
            raise ZoneNotDisabled(name)
        if not sg_name:
            sg_name = zone_cfg.get_row_exc(db_session, 'default_sg')
        sg = find_sg_byname(db_session, sg_name, raise_exc=True)
        zone_sm.set_sg(sg)
        self._finish_op()

    def set_zone_alt_sg(self, name, sg_name=None):
        """
        Set the alternate SG a zone is associated with
        """
        self._begin_op()
        db_session = self.db_session
        zone_sm = self._get_zone_sm(name, exact_network=True)
        exec_zonesm(zone_sm, ZoneSMDoSetAltSg, ZoneSmFailure, 
                alt_sg_name=sg_name)
        self._finish_op()

    def swap_zone_sg(self, name):
        """
        Swap a live zone's sg over with its alt_sg
        """
        self._begin_op()
        db_session = self.db_session
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if not zone_sm.alt_sg:
            raise ZoneNoAltSgForSwap(name)
        exec_zonesm(zone_sm, ZoneSMDoSgSwap)
        self._finish_op()
        

    def rr_query_db(self, label, name=None, type=None,
        rdata=None, zi_id=None, show_all=False):
        """
        Query the DB for RRs matching the given pattern 
        """
        self._begin_op()
        db_session = self.db_session
        try:
            result = rr_query_db_raw(db_session, label=label, name=name,
                    type_=type, rdata=rdata, include_disabled=show_all,
                    zi_id=zi_id, sectag=self.sectag)
        except ValueError as exc:
            raise RrQueryDomainError(name)
        if result:
            rrs = result.get('rrs')
            if not rrs:
                return None
            result['rrs'] = [rr.to_engine() for rr in rrs]
            result['zone_disabled'] = result['zone_sm'].is_disabled()
            result.pop('zone_sm', None)
        self._finish_op()
        return result

    def _update_rrs(self, name, update_data, update_type, login_id,
                    admin_privilege=False, helpdesk_privilege=False):
        """
        Do Incremental Updates for a zone.  Takes same ZI data format as
        _create_zone().  Will produce a JSON Error if an exception is thrown.
        """
        self._begin_op()
        change_by = self._make_change_by(login_id)
        auto_ptr_data = self._data_to_update(name, update_data, update_type,
                            change_by,
                            admin_privilege=admin_privilege,
                            helpdesk_privilege=helpdesk_privilege)
        # Do auto_ptr_data operation here.
        self._queue_auto_ptr_data(auto_ptr_data)
        # Commit everything.
        self._finish_op()

    def update_rrs_admin(self, name, update_data, update_type, login_id):
        """
        Incremental updates, admin privilege
        """
        return self._update_rrs(name, update_data, update_type, login_id, 
                                admin_privilege=True)

    def refresh_zone_ttl(self, name, zone_ttl=None):
        """
        Refresh a zones TTL by issuing an update.
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name, exact_network=True)
        if not zone_ttl:
            zone_ttl = zone_cfg.get_row_exc(self.db_session, 'zone_ttl', 
                                    sg_name=zone_sm.sg.name)
        if zone_sm.zi_candidate:
            zone_sm.zi_candidate.update_zone_ttls(zone_ttl=zone_ttl)
        elif zone_sm.zi:
            zone_sm.zi.update_zone_ttls(zone_ttl=zone_ttl)
        else:
            raise ZoneHasNoZi(name)

        results = exec_zonesm(zone_sm, ZoneSMDoRefresh)
        self._finish_op()
    
    def list_pending_events(self):
        """
        List pending events
        """
        self._begin_op()
        db_query_slice = get_numeric_setting('db_query_slice', int)
        db_session = self.db_session
        query = db_session.query(Event).filter(Event.processed == None)\
                .order_by(Event.id_).yield_per(db_query_slice)
        results = []
        for event in query:
            json_event = event.to_engine_brief(time_format=self.time_format)
            results.append(json_event)
        self._finish_op()
        return results

    def _find_sg_byname(self, sg_name):
        """
        Given an sg_id, return the server group
        """
        db_session = self.db_session
        return find_sg_byname(db_session, sg_name, raise_exc=True)
    
    def _show_sg(self, sg):
        """
        Back end - Show the details of an SG
        """
        result = sg.to_engine()
        servers = []
        for server in sg.servers:
            servers.append(server.to_engine_brief()) 
        result['servers'] = servers if servers else None
        self._finish_op()
        return result

    def show_sg(self, sg_name):
        """
        Show the details of an SG
        """
        self._begin_op()
        sg = self._find_sg_byname(sg_name)
        return self._show_sg(sg)

    def show_replica_sg(self):
        """
        Show Master SG - sub call for status display
        """
        self._begin_op()
        db_session = self.db_session
        replica_sg = get_mastersm_replica_sg(db_session)
        if not replica_sg:
            raise NoReplicaSgFound()
        return self._show_sg(replica_sg)

    def list_server(self, *servers, sg_name=None, show_all=True, 
            show_active=False):
        """
        List servers
        """
        self._begin_op()
        if not servers:
            servers = '*'
        server_list = []
        # 
        server_pattern = ' '.join(servers)
        servers = [x.replace('*', '%') for x in servers]
        servers = [x.replace('?', '_') for x in servers]
        for s in servers:
            query = self.db_session.query(ServerSM)\
                    .filter(ServerSM.name.like(s))\
                    .order_by(ServerSM.name)
            if sg_name:
                if sg_name not in list_all_sgs(self.db_session):
                    raise NoSgFound(sg_name)
                query = query.join(ServerGroup,
                         ServerGroup.id_ == ServerSM.sg_id)\
                        .filter(ServerGroup.name == sg_name)
            server_list.extend(query.all())
        replica_sg = get_mastersm_replica_sg(self.db_session)
        if not show_all:
            replica_sg = get_mastersm_replica_sg(self.db_session)
            server_list = [s for s in server_list if s.sg != replica_sg ]
        if show_active:
            server_list = [s for s in server_list if (not s.is_disabled())]
        if not server_list:
            raise NoServerFound('*')
        server_list = [ s.to_engine_brief(time_format=self.time_format)
                            for s in server_list ]
        server_list = sorted(server_list, key=lambda s: s['server_name'])
        self._finish_op()
        return server_list

    def show_dms_status(self):
        """
        Show DMS system status
        """
        result = {}
        try:
            result['show_replica_sg'] = self.show_replica_sg()
        except NoReplicaSgFound:
            result['show_replica_sg'] = None
        result['show_mastersm'] = self.show_mastersm()
        try:
            result['list_server'] = self.list_server()
        except NoServerFound:
            result['list_server'] = None
        result['list_pending_events'] = self.list_pending_events()
        return result

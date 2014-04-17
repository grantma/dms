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
Module to contain Text Editor Zone editing engine
"""


from datetime import timedelta
import tempfile
import io
import os
import re
import errno
import pwd
import grp
from os.path import basename
from subprocess import check_call
from subprocess import check_output
from subprocess import CalledProcessError
from subprocess import STDOUT
from base64 import b64encode

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.sql import or_
from sqlalchemy.sql import and_
from sqlalchemy.sql import func
from sqlalchemy.sql import not_
from sqlalchemy.sql import select
from sqlalchemy.sql import delete
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import desc

from magcode.core.globals_ import *
from dms.globals_ import *
from magcode.core.utility import get_numeric_setting
from magcode.core.database import sql_types
from magcode.core.database import sql_data
from magcode.core.database.event import Event
from magcode.core.database.event import ESTATE_NEW
from magcode.core.database.event import ESTATE_RETRY
from magcode.core.database.event import ESTATE_FAILURE
from magcode.core.database.event import ESTATE_SUCCESS
from magcode.core.database.event import cancel_event
from magcode.core.database.event import event_processed_states
from dms.exceptions import *
from dms.zone_engine import ZoneEngine
from dms.database import zone_cfg
from dms.database.zone_cfg import ZoneCfg
from dms.database.zone_sm import ZoneSM
from dms.database.zone_sm import ZSTATE_DELETED
from dms.database.zone_sm import ZSTATE_DISABLED
from dms.database.zone_sm import ZSTATE_PUBLISHED
from dms.database.zone_sm import exec_zonesm
from dms.database.zone_sm import ZoneSMDoRefresh
from dms.database.zone_sm import ZoneSMNukeStart
from dms.database.zone_sm import ZoneSMDoDestroy
from dms.database.zone_sm import ZoneSMDoReset
from dms.database.server_group import ServerGroup
from dms.exceptions import ZoneNotFound
from dms.exceptions import ZiNotFound
from dms.exceptions import NoZonesFound
from dms.dns import validate_zi_ttl
from dms.dns import validate_zi_hostname
from dms.database.zone_sectag import new_sectag
from dms.database.zone_sectag import del_sectag
from dms.database.master_sm import reset_master_sm
from dms.database.master_sm import reconfig_all
from dms.database.master_sm import reconfig_sg
from dms.database.master_sm import reconfig_master
from dms.database.master_sm import get_master_sm
from dms.database.master_sm import get_mastersm_replica_sg
from dms.database.zone_instance import ZoneInstance
from dms.database.sg_utility import find_sg_byname
from dms.database.sg_utility import find_sg_byid
from dms.database.sg_utility import list_all_sgs
from dms.database.sg_utility import new_sg
from dms.database.sg_utility import set_sg_config
from dms.database.sg_utility import set_sg_master_address
from dms.database.sg_utility import set_sg_master_alt_address
from dms.database.sg_utility import set_sg_replica_sg
from dms.database.sg_utility import del_sg
from dms.database.sg_utility import rename_sg
from dms.database.server_sm import ServerSM
from dms.database.server_sm import SSTYPE_BIND9
from dms.database.server_sm import SSTYPE_NSD3
from dms.database.server_sm import server_types
from dms.database.server_sm import find_server_byname
from dms.database.server_sm import find_server_byaddress
from dms.database.server_sm import new_server
from dms.database.server_sm import del_server
from dms.database.server_sm import set_server
from dms.database.server_sm import rename_server
from dms.database.server_sm import set_server_ssh_address
from dms.database.server_sm import move_server_sg
from dms.database.server_sm import exec_server_sm
from dms.database.server_sm import ServerSMEnable
from dms.database.server_sm import ServerSMDisable
from dms.database.server_sm import ServerSMReset
from dms.database.syslog_msg import SyslogMsg


config_keys = ['soa_mname', 'soa_rname', 'soa_refresh', 'soa_retry',
            'soa_expire', 'soa_minimum', 'soa_ttl', 'zone_ttl', 'use_apex_ns',
            'edit_lock', 'auto_dnssec', 'default_sg', 'default_ref',
            'default_stype', 'zi_max_age', 'zi_max_num', 'zone_del_pare_age',
            'zone_del_age', 'event_max_age', 'syslog_max_age',
            'nsec3', 'inc_updates']

tsig_key_algorithms = ('hmac-md5', 'hmac-sha1', 'hmac-sha224', 'hmac-sha256',
        'hmac-sha384', 'hmac-512')

# 2 simple exceptions for restore_named_db to enable MasterSM.write_named_conf 
# and ZoneSM.write_zone_file to be called.
class ZoneFileWriteInternalError(Exception):
    pass
class NamedConfWriteInternalError(Exception):
    pass

class CmdLineEngine(ZoneEngine):
    """
    Zone Editing Engine for use with the command line and a text editor.
    """
    
    def __init__(self, sectag_label=None):
        super().__init__(time_format="%a %b %e %H:%M:%S %Y", 
                sectag_label=sectag_label)
    
    def show_zone_full(self, name, zi_id=None):
        """
        Given a zone name, return all the values stored in its ZoneSM
        record, current zi, all RRs, and comments
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        return self._show_zone(zone_sm, zi_id, all_rrs=True)

    def show_zone_byid_full(self, zone_id, zi_id=None):
        """
        Given a zone id, return all the values stored in its ZoneSM
        record, current zi, RRs, and comments
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        zone_sm = self._get_zone_sm_byid(zone_id)
        return self._show_zone(zone_sm, zi_id, all_rrs=True)

    def get_config_default(self, config_key):
        """
        Get the default value for a configuration key
        """
        self.refresh_db_session()
        return zone_cfg.get_row_exc(self.db_session, config_key)

    def set_config(self, config_key, value, sg_name=None):
        """
        Set a configuration item in the zone_cfg table
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        if config_key in ['soa_mname', 'soa_rname']:
            validate_zi_hostname(None, config_key, value)
        if config_key in ['soa_refresh', 'soa_retry', 'soa_expire', 'soa_ttl',
                'zone_ttl']:
            validate_zi_ttl(None, config_key, value)
        if config_key in ['soa_mname',]:
            if not sg_name:
               raise SgNameRequired(config_key)
        else:
            sg_name = None
        zone_cfg.set_row(self.db_session, config_key, value, sg_name=sg_name)
        self._finish_op()
        return {}

    def show_config(self):
        """
        Display all the configuration keys
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        db_session = self.db_session
        result = db_session.query(ZoneCfg)\
                    .filter(ZoneCfg.key.in_(config_keys)).all()
        result_list = []
        for zone_cfg in result:
            result_list.append(zone_cfg.to_engine())
        return result_list

    def show_apex_ns(self, sg_name=None):
        """
        Display the apex NS server settings
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        sg = find_sg_byname(self.db_session, sg_name)
        if not sg:
            raise NoSgFound(sg_name)
        result = zone_cfg.get_rows_exc(self.db_session, 
                                        settings['apex_ns_key'],
                                        sg_name=sg_name)
        return result
    
    def set_apex_ns(self, ns_servers, sg_name):
        """
        Set the apex NS server settings
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        # Strip blank lines
        ns_servers = [ns for ns in ns_servers if ns]
        # Fix up people not giving FQDN including root zone!
        ns_servers = [ (ns + '.' if not ns.endswith('.') else ns) 
                            for ns in ns_servers]
        result = zone_cfg.set_rows(self.db_session, settings['apex_ns_key'],
                                    ns_servers, sg_name=sg_name)
        self._finish_op()
        return result

    def nuke_zones(self, *names, include_deleted=False, toggle_deleted=False, 
            sg_name=None, reference=None):
        """
        Destroy multiple zones.  Multiple names may be given.  Wildcards
        can be used for partial matches.

        This is mainly a command for testing, or cleaning up after a large
        batch zone load goes awry.

        Zones being nuked have their deleted_start set to 1/1/1970, midnight.
        This means they will be immediately reaped by the next vacuum_zones
        command.
        """
        # Deal with SA auto-BEGIN - want fresh transaction to see fresh data
        self._begin_op()
        if not names:
            # No arguments
            self._finish_op()
            raise NoZonesFound('')
       
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        # We were given some arguments
        zones = []
        # We keep domains and labels in database lowercase
        names = [x.lower() for x in names]
        name_pattern = ' '.join(names)
        names = [x.replace('*', '%') for x in names]
        names = [x.replace('?', '_') for x in names]
        for name in names:
            if not name.endswith('.') and not name.endswith('%'):
                name += '.'
            query = db_session.query(ZoneSM)\
                    .filter(ZoneSM.name.like(name))
            # Don't delete any reverse zones with this command
            query = query.filter(not_(ZoneSM.name.like('%.in-addr.arpa.')))\
                    .filter(not_(ZoneSM.name.like('%.ip6.arpa.')))
            if reference:
                query = query.join(Reference)\
                        .filter(Reference.reference.ilike(reference))
            if sg_name and self.sectag.sectag == settings['admin_sectag']:
                if sg_name not in list_all_sgs(self.db_session):
                    raise NoSgFound(sg_name)
                query = query.join(ServerGroup, ZoneSM.sg_id 
                                    == ServerGroup.id_)\
                        .filter(ServerGroup.name == sg_name)
            if include_deleted:
                pass
            elif toggle_deleted:
                query = query.filter(ZoneSM.state == ZSTATE_DELETED)
            else:
                query = query.filter(ZoneSM.state != ZSTATE_DELETED)
            query = query.yield_per(db_query_slice)
            # The following gives less RAM piggery even though it is slower
            for z in query:
                zones.append(z)
        # Take note of security tags
        if self.sectag.sectag != settings['admin_sectag']:
            zones = [x for x in zones if self.sectag in x.sectags]
        if not zones:
            if len(name_pattern) > 240:
                name_pattern = '* - %s names' % len(names)
            raise NoZonesFound(name_pattern)
        # Mark them all as deleted.
        for zone in zones:
            exec_zonesm(zone, ZoneSMNukeStart)
        self._finish_op()

    def create_sectag(self, sectag_label):
        """
        Create a new security tag
        """
        self._begin_op()
        new_sectag(self.db_session, sectag_label)
        self._finish_op()

    def delete_sectag(self, sectag_label):
        """
        Delete a security tag
        """
        self._begin_op()
        del_sectag(self.db_session, sectag_label)
        self._finish_op()
    
    def reset_mastersm(self):
        """
        Reset the Configuration state machine 
        """
        self._begin_op()
        reset_master_sm(self.db_session)
        self._finish_op()
    
    def _find_sg_byid(self, sg_id):
        """
        Given an sg_id, return the server group
        """
        db_session = self.db_session
        return find_sg_byid(db_session, sg_id, raise_exc=True)

    def create_sg(self, sg_name, config_dir=None, address=None, 
            alt_address=None, replica_sg=False):
        """
        Create a new SG
        """
        self._begin_op()
        new_sg(self.db_session, sg_name, config_dir, address, alt_address,
                replica_sg)
        self._finish_op()

    def rename_sg(self, sg_name, new_sg_name):
        """
        Rename an SG 
        """
        self._begin_op()
        rename_sg(self.db_session, sg_name, new_sg_name)
        self._finish_op()
        
    def set_sg_config(self, sg_name, config_dir=None):
        """
        Set the SG config dir
        """
        self._begin_op()
        set_sg_config(self.db_session, sg_name, config_dir)
        self._finish_op()

    def set_sg_master_address(self, sg_name, address=None):
        """
        Set the SG master server address
        """
        self._begin_op()
        set_sg_master_address(self.db_session, sg_name, address)
        self._finish_op()

    def set_sg_master_alt_address(self, sg_name, alt_address=None):
        """
        Set the alternate SG master server address
        """
        self._begin_op()
        set_sg_master_alt_address(self.db_session, sg_name, alt_address)
        self._finish_op()

    def set_sg_replica_sg(self, sg_name):
        """
        Set the replica_sg flag on an SG
        """
        self._begin_op()
        set_sg_replica_sg(self.db_session, sg_name)
        self._finish_op()

    def delete_sg(self, sg_name):
        """
        Delete an SG
        """
        self._begin_op()
        del_sg(self.db_session, sg_name)
        self._finish_op()

    def reconfig_all(self):
        """
        Reconfigure all servers
        """
        self._begin_op()
        reconfig_all(self.db_session)
        self._finish_op()

    def reconfig_sg(self, sg_name):
        """
        Reconfigure an SGs servers
        """
        self._begin_op()
        sg = self._find_sg_byname(sg_name)
        reconfig_sg(self.db_session, sg.id_, sg.name)
        self._finish_op()

    def reconfig_replica_sg(self):
        """
        Reconfigure replica SG.  
        
        This forces an rsync of DNSSEC key material and Zone data to DR
        replica servers.
        """
        self._begin_op()
        db_session = self.db_session
        replica_sg = get_mastersm_replica_sg(db_session)
        if not replica_sg:
            # If no replica_sg, return with no error
            return
        reconfig_sg(db_session, replica_sg.id_, replica_sg.name)
        self._finish_op()

    def reconfig_master(self):
        """
        Reconfigure the master DNS server
        """
        self._begin_op()
        reconfig_master(self.db_session)
        self._finish_op()

    def refresh_all(self):
        """
        Reconfigure all zones
        """
        self._begin_op()
        db_session = self.db_session
        id_query = db_session.query(ZoneSM.id_, ZoneSM.name)
        id_query = ZoneSM.query_is_configured(id_query)
        id_result = id_query.all()
        for zone_id, zone_name in id_result:
            try:
                zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
            except NoResultFound:
                raise ZoneNotFoundByZoneId(zone_id)
            exec_zonesm(zone_sm, ZoneSMDoRefresh)
        self._finish_op()

    def refresh_sg(self, sg_name):
        """
        Refresh all zones on an SG
        """
        self._begin_op()
        db_session = self.db_session
        sg = self._find_sg_byname(sg_name)
        id_query = db_session.query(ZoneSM.id_, ZoneSM.name)\
                .filter(ZoneSM.sg_id == sg.id_) 
        id_query = ZoneSM.query_is_configured(id_query)
        id_result = id_query.all()
        for zone_id, zone_name in id_result:
            try:
                zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
            except NoResultFound:
                raise ZoneNotFoundByZoneId(zone_id)
            exec_zonesm(zone_sm, ZoneSMDoRefresh)
        self._finish_op()

    def create_zone_batch(self, name, login_id, zi_data=None, 
                use_apex_ns=None, edit_lock=None, auto_dnssec=None,
                nsec3=None, inc_updates=None, reference=None, 
                sg_name=None, sectags=None):

        """
        Create a zone with admin privilege when doing a batch load
        """
        return self._create_zone(name, zi_data, login_id, use_apex_ns,
                edit_lock, auto_dnssec, nsec3, inc_updates, 
                reference, sg_name, sectags, admin_privilege=True,
                batch_load=True)

    def create_zi_zone_admin(self, zi_id, name, login_id,
            use_apex_ns=None, edit_lock=None, auto_dnssec=None,
            nsec3=None, inc_updates=None, reference=None, sg_name=None,
            sectags=None):
        """
        Create a zone with admin privilege
        """
        return self._create_zone(name, src_zi_id=zi_id,
                use_apex_ns=use_apex_ns, edit_lock=edit_lock, 
                auto_dnssec=auto_dnssec, nsec3=nsec3, inc_updates=inc_updates, 
                reference=reference, sg_name=sg_name, sectags=sectags,
                login_id=login_id, zi_data=None, admin_privilege=True)

    def vacuum_event_queue(self, age_days=None):
        """
        Destroy events processed more than age_days ago
        """
        self._begin_op()
        db_session = self.db_session
        if age_days is None:
            age_days = float(zone_cfg.get_row_exc(db_session,
                                key='event_max_age'))
        age_days = timedelta(days=age_days)
        count = 0
        # Do a straight SQL DELETE first to speed things along
        # Count events to be deleted
        event_table = sql_data['tables'][Event]
        where_stmt = and_(Event.state.in_(event_processed_states),
                            Event.processed != None,
                            (func.now() - Event.processed) > age_days)
        count_select = select([func.count(event_table.c.get('id'))],
                                where_stmt)
        result = db_session.execute(count_select).fetchall()
        count += result[0][0]
        db_session.execute(event_table.delete().where(where_stmt))
                    
        result = {'num_deleted': count}
        self._finish_op()
        return result

    def vacuum_zones(self, age_days=None):
        """
        Destroy zones older than age_days
        """
        self._begin_op()
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        age_days_from_config = float(zone_cfg.get_row_exc(db_session,
                                    key='zone_del_age'))
        if age_days_from_config <= 0 and age_days is None:
            age_days = get_numeric_setting('zone_del_off_age', float)
        elif age_days is None:
            age_days = age_days_from_config
        age_days = timedelta(days=age_days)
        count = 0
        # Clear old and nuked zones one by one
        id_query = db_session.query(ZoneSM.id_)\
                .filter(ZoneSM.state == ZSTATE_DELETED)\
                .filter(or_(ZoneSM.deleted_start == None,
                            (func.now() - ZoneSM.deleted_start) > age_days))\
                .filter(ZoneSM.zone_files == False)\
                .yield_per(db_query_slice)
        id_results = []
        for zone_id, in id_query:
            id_results.append(zone_id)
        for zone_id in id_results:
            try:
                zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
            except NoResultFound:
                continue
            if zone_sm.state != ZSTATE_DELETED:
                # Skip this if a customer has undeleted zone in the mean time..
                continue
            db_session.delete(zone_sm)
            db_session.commit()
            count += 1
                    
        # Finally do zone_sm destroy operation to 
        query = db_session.query(ZoneSM)\
                .filter(ZoneSM.state == ZSTATE_DELETED)\
                .filter(or_(ZoneSM.deleted_start == None,
                    (func.now() - ZoneSM.deleted_start) > age_days))
        for zone_sm in query:
            if zone_sm.state != ZSTATE_DELETED:
                # Skip this if a customer has undeleted zone in the mean time..
                continue
            try:
                exec_zonesm(zone_sm, ZoneSMDoDestroy)
            except ZoneSmFailure:
                continue
            count += 1
        result = {'num_deleted': count}
        self._finish_op()
        return result


    def vacuum_zis(self, age_days=None, zi_max_num=None):
        """
        Age ZIs according to age_days and zi_max_num
        """
        self._begin_op()
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        if age_days is None:
            age_days = float(zone_cfg.get_row_exc(db_session,
                                key='zi_max_age'))
        age_days = timedelta(days=age_days)
        if zi_max_num is None:
            zi_max_num = int(zone_cfg.get_row_exc(db_session, 
                    key='zi_max_num'))
        stmt = db_session.query(ZoneInstance.zone_id,
                func.count(ZoneInstance.id_).label('zi_count'))\
                        .group_by(ZoneInstance.zone_id).subquery()
        zone_sm_query = db_session.query(ZoneSM)\
                .filter(ZoneSM.state != ZSTATE_DELETED)\
                .outerjoin(stmt, ZoneSM.id_ == stmt.c.zone_id)\
                .filter(stmt.c.zi_count > zi_max_num)\
                .yield_per(db_query_slice)
        count = 0
        for zone_sm in zone_sm_query:
            zi_keep = db_session.query(ZoneInstance.id_)\
                    .filter(ZoneInstance.zone_id == zone_sm.id_)\
                    .order_by(desc(ZoneInstance.mtime))\
                    .limit(zi_max_num)
            zi_query = db_session.query(ZoneInstance)\
                    .filter(ZoneInstance.zone_id == zone_sm.id_)\
                    .filter(ZoneInstance.id_ != zone_sm.zi_id)\
                    .filter(not_(ZoneInstance.id_.in_(zi_keep)))\
                    .filter(ZoneInstance.mtime < (func.now() - age_days))
            for zi in zi_query:
                if (zi.id_ == zone_sm.zi_id 
                        or zi.id_ == zone_sm.zi_candidate_id):
                    # Skip if this ZI has ben selected for republishing in 
                    # the mean time
                    continue
                db_session.delete(zi)
                count += 1
        result = {'num_deleted': count}
        self._finish_op()
        return result
   
    def vacuum_pare_deleted_zone_zis(self, age_days=None):
        """
        Pare ZIs on deleted zones older than age_days
        """
        self._begin_op()
        db_session = self.db_session
        db_query_slice = get_numeric_setting('db_query_slice', int)
        age_days_from_config = float(zone_cfg.get_row_exc(db_session, 
                                                    key='zone_del_pare_age'))
        if age_days_from_config <= 0 and age_days is None:
            return {'num_deleted': 0}
        if age_days is None:
            age_days = age_days_from_config
        age_days = timedelta(days=age_days)

        stmt = db_session.query(ZoneInstance.zone_id,
                func.count(ZoneInstance.id_).label('zi_count'))\
                        .group_by(ZoneInstance.zone_id).subquery()
        zone_sm_query = db_session.query(ZoneSM)\
                .filter(ZoneSM.state == ZSTATE_DELETED)\
                .outerjoin(stmt, ZoneSM.id_ == stmt.c.zone_id)\
                .filter(stmt.c.zi_count > 1)\
                .filter(and_(ZoneSM.deleted_start != None,
                    (func.now() - ZoneSM.deleted_start) > age_days))\
                .yield_per(db_query_slice)
        count = 0
        for zone_sm in zone_sm_query:
            zi_query = db_session.query(ZoneInstance)\
                    .filter(ZoneInstance.zone_id == zone_sm.id_)\
                    .filter(ZoneInstance.id_ != zone_sm.zi_id)
            if zone_sm.state != ZSTATE_DELETED:
                # Skip this if a customer has undeleted zone in the mean time..
                continue
            for zi in zi_query:
                if (zi.id_ == zone_sm.zi_id 
                        or zi.id_ == zone_sm.zi_candidate_id):
                    # Skip if this ZI has published or selected to be published
                    continue
                db_session.delete(zi)
                count += 1
        
        result = {'num_deleted': count}
        self._finish_op()
        return result

    def vacuum_syslog (self, age_days=None):
        """
        Destroy syslog messages received more than age_days ago
        """
        self._begin_op()
        db_session = self.db_session
        if age_days is None:
            age_days = float(zone_cfg.get_row_exc(db_session,
                key='syslog_max_age'))
        age_days = timedelta(days=age_days)
        count = 0
        # Do a straight SQL DELETE first to speed things along
        # Count events to be deleted
        syslog_table = sql_data['tables'][SyslogMsg]
        where_stmt = and_(SyslogMsg.receivedat != None,
                            (func.now() - SyslogMsg.receivedat) > age_days)
        count_select = select([func.count(syslog_table.c.get('id'))],
                                where_stmt)
        result = db_session.execute(count_select).fetchall()
        count += result[0][0]
        db_session.execute(syslog_table.delete().where(where_stmt))
                    
        result = {'num_deleted': count}
        self._finish_op()
        return result


    def _show_server(self, server_sm):
        """
        Show server backend
        """
        result = server_sm.to_engine(time_format=self.time_format)
        self._finish_op()
        return result

    def show_server(self, server_name):
        """
        Show a server, by name
        """
        self._begin_op()
        server_sm = find_server_byname(self.db_session, server_name)
        return self._show_server(server_sm)

    def show_server_byaddress(self, address):
        """
        Show a server, by address
        """
        self._begin_op()
        server_sm = find_server_byaddress(self.db_session, address)
        return self._show_server(server_sm)

    def create_server(self, server_name, address, sg_name=None,
                    server_type=None, ssh_address=None):
        """
        Create a Server SM
        """
        self._begin_op()
        new_server(self.db_session, server_name, address, sg_name, server_type,
                    ssh_address)
        self._finish_op()

    def delete_server(self, server_name):
        """
        Delete a Server SM
        """
        self._begin_op()
        del_server(self.db_session, server_name)
        self._finish_op()

    def set_server_ssh_address(self, server_name, ssh_address):
        """
        Perform set_server_ssh_address
        """
        self._begin_op()
        set_server_ssh_address(self.db_session, server_name, ssh_address)
        self._finish_op()
    
    def set_server(self, server_name, new_server_name=None,
                address=None, server_type=None, ssh_address=None):
        """
        Perform set_server
        """
        self._begin_op()
        set_server(self.db_session, server_name, new_server_name,
                address, server_type, ssh_address)
        self._finish_op()
    
    def rename_server(self, server_name, new_server_name=None,
                address=None, server_type=None):
        """
        Perform rename_server
        """
        self._begin_op()
        rename_server(self.db_session, server_name, new_server_name)
        self._finish_op()
    
    def move_server_sg(self, server_name, sg_name):
        """
        Move a server between SGs
        """
        self._begin_op()
        move_server_sg(self.db_session, server_name, sg_name)
        self._finish_op()

    def enable_server(self, server_name):
        """
        Enable a server
        """
        self._begin_op()
        db_session = self.db_session
        server_sm = find_server_byname(db_session, server_name)
        exec_server_sm(server_sm, ServerSMEnable) 
        self._finish_op()

    def disable_server(self, server_name):
        """
        Disable a server
        """
        self._begin_op()
        db_session = self.db_session
        server_sm = find_server_byname(db_session, server_name)
        exec_server_sm(server_sm, ServerSMDisable) 
        self._finish_op()

    def reset_server(self, server_name):
        """
        Reset server SM
        """
        self._begin_op()
        db_session = self.db_session
        server_sm = find_server_byname(db_session, server_name)
        exec_server_sm(server_sm, ServerSMReset) 
        self._finish_op()
    
    def write_rndc_conf(self):
        """
        Write out a new rndc.conf file
        """
        self._begin_op()
        db_session = self.db_session
        # Create temporary file for new rndc.conf
        rndc_conf_header = settings['rndc_header_template']
        rndc_conf_server = settings['rndc_server_template']
        rndc_conf_file = settings['rndc_conf_file']

        header_template = open(rndc_conf_header).readlines()
        header_template = ''.join(header_template)
        server_template = open(rndc_conf_server).readlines()
        server_template = ''.join(server_template)
        (fd, tmp_filename) = tempfile.mkstemp(
                    dir=settings['master_bind_config_dir'],
                    prefix='.' + basename(rndc_conf_file) + '-')
        tmp_file = io.open(fd, mode='wt')
        tmp_file.write(header_template)
        query = db_session.query(ServerGroup)
        for sg in query:
            for server_sm in sg.servers:
                # Also do disabled servers, as we want to be able to rndc them
                # when they are again enabled.
                filler = server_sm.to_engine()
                tmp_file.write(server_template % filler)
        tmp_file.close()
        # Rename tmp file into place so that replacement is atomic
        os.chown(tmp_filename, 0, 0)
        os.chmod(tmp_filename, int(settings['rndc_conf_file_mode'],8))
        os.rename(tmp_filename, rndc_conf_file)
        self._finish_op()

    def generate_tsig_key(self, file_name, key_name, 
            hmac_type='hmac-sha256'):
        """
        Generate a new tsig key in BIND named.conf format
        """
        if hmac_type.lower() not in tsig_key_algorithms:
            raise InvalidHmacType(algorithm)
        # Key size is optimally the full blocksize usablefor the hash in the
        # HMAC algorithm - RFC 2104
        if hmac_type.lower() in ('hmac-md5', 'hmac-sha1'):
            key_size = 64 #bytes
        elif hmac_type.lower() in ('hmac-sha224', 'hmac-sha256'):
            key_size = 128 # bytes
        elif hmac_type.lower() in ('hmac-sha384', 'hmac-512'):
            key_size = 256 #bytes
        else:
            key_size = 256 #bytes
        # Read key from /dev/random
        randev = open('/dev/random', 'rb')
        key_material = randev.read(key_size)
        randev.close()
        key_material = b64encode(key_material).decode()
        
        template_file = settings['tsig_key_template']
        key_template = open(template_file).readlines()
        key_template = ''.join(key_template)
        filler = {'key_name': key_name, 'algorithm': hmac_type, 
                'secret': key_material}
        key_text = key_template % filler

        old_umask = None
        write_file =  isinstance(file_name, str)
        if write_file:
            if file_name[0] != '/':
                file_name = (settings['dms_bind_config_dir'] 
                                + '/' + file_name)
            old_umask = os.umask(0o00077)
            output_file = open(file_name, 'wt') 
        else:
            output_file = sys.stdout
        print(key_text, file=output_file)
        output_file.flush()
        if write_file:
            os.chmod(file_name, int(settings['key_file_mode'],8))
            uid = pwd.getpwnam(settings['key_file_owner']).pw_uid
            gid = grp.getgrnam(settings['key_file_group']).gr_gid
            os.chown(file_name, uid, gid)
            output_file.close()
            os.umask(old_umask)
        return

    def rsync_server_admin_config(self, server_name, no_rndc=False):
        """
        Rsync configuration files to a server, and rndc reconfig it
        """
        self._begin_op()
        db_session = self.db_session
        server_sm = find_server_byname(db_session, server_name)
        config_dir = (settings['server_admin_config_dir'] + '/'
                            + server_sm.server_type)
        cmdline = (settings['rsync_path'] + ' ' + settings['rsync_args'] 
                + ' --password-file ' + settings['rsync_password_file'] 
                + ' ' + config_dir + '/' + ' ' + settings['rsync_target'])
        # Add IPv6 address squares
        address_string = '[' + server_sm.address + ']' \
                    if server_sm.address.find(':') else server_sm.address
        cmdline_str = cmdline % address_string
        cmdline = cmdline_str.split(' ')
        output = check_call(cmdline)
        if not no_rndc:
            cmdline = [settings['rndc_path'], '-s', server_sm.name, 'reconfig']
            output = check_call(cmdline)
        self._finish_op()

    def reset_all_zones(self):
        """
        Reset all zones
        """
        self._begin_op()
        db_session = self.db_session
        id_query = db_session.query(ZoneSM.id_, ZoneSM.name)
        id_query = ZoneSM.query_is_not_disabled_deleted(id_query)
        id_result = id_query.all()
        for zone_id, zone_name in id_result:
            try:
                zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
            except NoResultFound:
                raise ZoneNotFoundByZoneId(zone_id)
            exec_zonesm(zone_sm, ZoneSMDoReset)
        self._finish_op()

    def list_resolv_zi_id(self, name, zi_id):
        """
        Extra functionality for zone_tool ls_zi command.  Allows ls_zi to take
        a zi_id argument
        """
        self._begin_op()
        zone_sm = self._get_zone_sm(name)
        zi = self._resolv_zi_id(zone_sm, zi_id)
        if not zi:
            raise ZiNotFound(name, zi_id)
        resolv_result = zi.to_engine_brief(time_format=self.time_format)
        result = {'all_zis': [resolv_result], 'zi_id': zone_sm.zi_id}
        self._finish_op()
        return result

    def restore_named_db(self):
        """
        Dump dms DB to Named zone files and include file

        For quick DR secnario
        """
        self._begin_op()
        
        # Exception processing make the both of the following a bit of a 
        # rats nest
        # Check that named is not running
        cmdline = [settings['rndc_path'], 'status']
        try:
            check_output(cmdline, stderr=STDOUT)
        except CalledProcessError as exc:
            if exc.returncode != 1:
                raise exc
            pass
        else:
            raise NamedStillRunning(0)

        # Check that dmsdmd is not running
        try:
            pid_file = open(settings['pid_file'],'r')
            dmsdmd_pid = int(pid_file.readline().strip())
            pid_file.close()
            # The following throws exceptions if process does not exist etc!
            # Sending signal 0 does not touch process, but  call succeeds
            # if it exists
            os.kill(dmsdmd_pid, 0)
        except ValueError as exc:
            # Error from int() type conversion above
            raise PidFileValueError(pid_file, exc)
        except (IOError,OSError) as exc:
            if (exc.errno in (errno.ESRCH,)):
                # This is from kill()
                raise DmsdmdStillRunning(dmsdmd_pid)
            # File IO causes this
            elif (exc.errno in (errno.ENOENT,)):
                # This file may be removed by dameon nicely shutting down.
                pass
        else:
            # No exceptions, dmsdmd is running!!!
            raise DmsdmdStillRunning(dmsdmd_pid)

        # Dump out each zone file
        db_session = self.db_session
        id_query = db_session.query(ZoneSM.id_, ZoneSM.name)
        id_query = ZoneSM.query_is_not_disabled_deleted(id_query)
        id_result = id_query.all()
        for zone_id, zone_name in id_result:
            try:
                zone_sm = db_session.query(ZoneSM)\
                        .filter(ZoneSM.id_ == zone_id).one()
            except NoResultFound:
                raise ZoneNotFoundByZoneId(zone_id)
            try:
                zone_sm.write_zone_file(db_session, ZoneFileWriteInternalError)
                zone_sm.state = ZSTATE_PUBLISHED
                db_session.commit()
            except ZoneFileWriteInternalError as exc:
                db_session.rollback()
                raise ZoneFileWriteError(str(exc))
        
        # Write out config file include
        master_sm = get_master_sm(db_session)
        try:
            master_sm.write_named_conf_includes(db_session, 
                    NamedConfWriteInternalError)
        except NamedConfWriteInternalError as exc:
            raise NamedConfWriteError(str(exc))
        self._finish_op()

    def list_failed_events(self, last_limit=None):
        """
        List failed events
        """
        self._begin_op()
        if not last_limit:
            last_limit = get_numeric_setting('list_events_last_limit', 
                                                float)
        db_query_slice = get_numeric_setting('db_query_slice', int)
        db_session = self.db_session
        query = db_session.query(Event).filter(Event.state == ESTATE_FAILURE)\
                .order_by(desc(Event.id_)).limit(last_limit)\
                .yield_per(db_query_slice)
        results = []
        for event in query:
            json_event = event.to_engine_brief(time_format=self.time_format)
            results.append(json_event)
        self._finish_op()
        return results

    def list_events(self, last_limit=None):
        """
        List failed events
        """
        self._begin_op()
        if not last_limit:
            last_limit = get_numeric_setting('list_events_last_limit', 
                                                float)
        db_query_slice = get_numeric_setting('db_query_slice', int)
        db_session = self.db_session
        query = db_session.query(Event)\
                .order_by(desc(Event.id_)).limit(last_limit)\
                .yield_per(db_query_slice)
        results = []
        for event in query:
            json_event = event.to_engine_brief(time_format=self.time_format)
            results.append(json_event)
        self._finish_op()
        return results

    def _find_event(self, event_id):
        """
        Find an event by ID
        """
        db_session = self.db_session
        try:
            query = db_session.query(Event).filter(Event.id_ == event_id)
            event = query.one()
        except NoResultFound as exc:
            raise EventNotFoundById(event_id)
        return event

    def show_event(self, event_id):
        """
        Show an event
        """
        self._begin_op()
        event = self._find_event(event_id)
        result = event.to_engine(time_format = self.time_format)
        self._finish_op()
        return result

    def fail_event(self, event_id):
        """
        Fail an event
        """
        self._begin_op()
        event = self._find_event(event_id)
        if not event.state in (ESTATE_NEW, ESTATE_RETRY):
            raise CantFailEventById(event_id)
        cancel_event(event.id_, self.db_session)
        self._finish_op()


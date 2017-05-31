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
Module for ZoneDataUtil mix in class for zone_engine

Split out so that changes can be seen more easily
"""


import re
from copy import copy

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import text

from magcode.core.globals_ import *
from magcode.core.database import sql_types
from dms.globals_ import *
from dms.exceptions import *
from dms.auto_ptr_util import check_auto_ptr_privilege
from dms.dns import RRTYPE_SOA
from dms.dns import RRTYPE_NS
from dms.dns import RRTYPE_A
from dms.dns import RRTYPE_AAAA
from dms.dns import RRTYPE_CNAME
from dms.dns import RRTYPE_MX
from dms.dns import RRTYPE_SRV
from dms.dns import RRTYPE_PTR
from dms.dns import RROP_DELETE
from dms.dns import RROP_UPDATE_RRTYPE
from dms.dns import RROP_ADD
from dms.dns import RROP_PTR_UPDATE
from dms.dns import RROP_PTR_UPDATE_FORCE
from dms.dns import validate_zi_hostname
from dms.dns import validate_zi_ttl
from dms.dns import is_inet_hostname
from dms.dns import label_from_address
from dms.dns import new_zone_soa_serial
import dms.database.zone_cfg as zone_cfg
from dms.database.zone_sm import exec_zonesm
from dms.database.zone_sm import ZoneSMDoRefresh
from dms.database.zone_sm import ZoneSM
from dms.database.reverse_network import ReverseNetwork
from dms.database.zone_instance import ZoneInstance
from dms.database.rr_comment import RRComment
from dms.database.resource_record import data_to_rr
from dms.database.resource_record import RR_PTR
from dms.database.resource_record import ResourceRecord
from dms.database.reference import find_reference
from dms.database.zi_update import ZiUpdate
from dms.database.update_group import new_update_group


class DataTools(object):
    """
    Container class for methods and runtime data for consistency 
    checking code 
    """

    def __init__(self, db_session, zone_sm, zi_cname_flag=False):
        """
        Initialise runtime data
        """
        self.db_session = db_session
        self.zone_sm = zone_sm
        self.name = zone_sm.name
        self.zi_cname_flag = zi_cname_flag
        self.zi_rr_data = {}
        self.auto_ptr_data = []
        self.apex_comment = None

    def check_rr_consistency(self, rrs, rr, rr_data, update_group):
        """
        Check that RR can be consistently added to zone
        """
        # Skip for any RROP_DELETE
        if update_group and rr.update_op and rr.update_op == RROP_DELETE:
            return

        if (not update_group or not rr.update_op 
                or rr.update_op != RROP_UPDATE_RRTYPE): 
            # Duplicate Record check
            if rr in rrs:
                raise DuplicateRecordInZone(self.name, rr_data)
            
            # Can't add another SOA if there is one there already
            if rr.type_ == RRTYPE_SOA:
                num_soa = len([r for r in rrs if r.type_ == RRTYPE_SOA])
                if num_soa:
                    raise ZoneAlreadyHasSOARecord(self.name, rr_data)

        # CNAME addition check
        if rr.type_ == RRTYPE_CNAME:
            self.zi_cname_flag = True

        # anti-CNAME addition check
        if self.zi_cname_flag:
            # Find any cnames with rr label and barf
            num_lbls = len([ r for r in rrs 
                            if (r.type_ == RRTYPE_CNAME 
                                and r.label == rr.label)])
            # Check that we are not updating an existing CNAME
            if (num_lbls and update_group and rr.update_op 
                    and rr.update_op == RROP_UPDATE_RRTYPE
                    and rr.type_ == RRTYPE_CNAME):
                num_lbls = 0
            if num_lbls:
                raise ZoneCNAMEExists(self.name, rr_data)

    def check_zi_consistency(self, rrs):
        """
        Check consistency of zone instance
        """
        # CNAME check
        rr_cnames = [r for r in rrs if r.type_ == RRTYPE_CNAME]
        for rr in rr_cnames:
            clash = len([ r for r in rrs 
                    if (r.label == rr.label and r.type_ != RRTYPE_CNAME)])
            if clash:
                raise ZoneCNAMELabelExists(self.name, self.zi_rr_data[str(rr)])
        # Check NS MX and SRV records point to actual A 
        # and AAAA records if they are in zone 
        # (Bind Option check-integrity)
        # NS
        rr_nss = [r for r in rrs if r.type_ == RRTYPE_NS 
                                                and r.label != '@']
        for rr in rr_nss:
            if not rr.rdata.endswith('.'):
                target_hosts = [r for r in rrs if r.label == rr.rdata]
                if not len(target_hosts):
                    raise ZoneCheckIntegrityNoGlue(self.name, 
                            self.zi_rr_data[str(rr)], rr.rdata)
        # MX
        rr_mxs = [r for r in rrs if r.type_ == RRTYPE_MX]
        for rr in rr_mxs:
            if not rr.rdata.endswith('.'):
                rdata = rr.rdata.split()
                target_hosts = [r for r in rrs if r.label == rdata[1]]
                if not len(target_hosts):
                    raise ZoneCheckIntegrityNoGlue(self.name, 
                            self.zi_rr_data[str(rr)], rdata[1])

        #SRV
        rr_srvs = [r for r in rrs if r.type_ == RRTYPE_SRV]
        for rr in rr_srvs:
            if not rr.rdata.endswith('.'):
                rdata = rr.rdata.split()

                target_hosts = [r for r in rrs if r.label == rdata[3]]
                if not len(target_hosts):
                    raise ZoneCheckIntegrityNoGlue(self.name, 
                            self.zi_rr_data[str(rr)], rdata[3])

        # If NS records are part of the zone, no point in doing
        # sanity checks as client will not be sending any SOAs
        if self.zone_sm.use_apex_ns:
            return
        # Check that zi has 1 SOA, and that its for the apex '@'
        rr_soas = [r for r in rrs if r.type_ == RRTYPE_SOA]
        if not rr_soas:
            raise ZoneHasNoSOARecord(self.name)
        if len(rr_soas) > 1:
            raise ZoneAlreadyHasSOARecord(self.name, 
                                self.zi_rr_data[str(rr_soas[1])])
        if rr_soas[0].label != '@':
            raise ZoneSOARecordNotAtApex(self.name, 
                                self.zi_rr_data[str(rr_soas[0])])
        # Check that apex has at least 1 NS record
        rr_nss = [r for r in rrs if r.type_ == RRTYPE_NS 
                and r.label == '@']
        if not rr_nss:
            raise ZoneHasNoNSRecord(self.name, 
                                        self.zi_rr_data[str(rr_soas[0])])

    def put_zi_rr_data(self, key, rr_data):
        """
        Store rr_data for later use
        """
        self.zi_rr_data[key] = rr_data
            
    def get_auto_ptr_data(self):
        """
        Return auto_ptr_data
        """
        return self.auto_ptr_data

    def handle_auto_ptr_data(self, rr, rr_data):
        """
        Handle auto reverse IP functionality.

        This is brief to quickly come up with a list of candidates
        that can be filtered for netblock reverse zone later on.
        """
        # We only look at IP address records
        if (rr.type_ != RRTYPE_A 
            and rr.type_ != RRTYPE_AAAA):
            return
       
        # We ignore DELETE update_ops, as algorithm will ignore that
        if (rr.update_op and rr.update_op == RROP_DELETE):
            return

        # Use the dnspython rewritten rdata to make sure that IPv6
        # addresses are uniquely written.
        hostname = rr.label + '.' + self.name if rr.label != '@' else self.name
        # Force reverse is once only, and not saved to DB, track_reverse is 
        # force reverse all the time
        force_reverse = False
        if rr_data.get('force_reverse'):
            force_reverse = True if rr_data['force_reverse'] else False
        if rr_data.get('track_reverse'):
            force_reverse = True if rr_data['track_reverse'] else force_reverse
        disable = False
        if rr_data.get('disable'):
            disable = True if rr_data['disable'] else False
        zone_ref = self.zone_sm.reference
        zone_ref_str = zone_ref.reference if zone_ref else None
        self.auto_ptr_data.append({ 'address': rr.rdata,
                                    'disable': disable,
                                    'force_reverse': force_reverse,
                                    'hostname': hostname,
                                    'reference': zone_ref_str})

    def check_reference_string(self, ref_str):
        """
        Check that the supplied reference string is complete
        """
        if not re.match(r'^[\-_a-zA-Z0-9.@]+$', ref_str):
            error_msg = "can only contain characters '-_a-zA-Z0-9.@'"
            raise ReferenceFormatError(ref_str, error_msg)
        if not re.match(r'^[0-9a-zA-Z][\-_a-zA-Z0-9.@]*$', ref_str):
            error_msg = "must start with 'a-zA-Z0-9'"
            raise ReferenceFormatError(ref_str, error_msg)
        if len(ref_str) > 1024:
            error_msg = "too long, must be <= 1024."
            raise ReferenceFormatError(ref_str, error_msg)

    def check_extra_data_privilege(self, rr_data, admin_privilege, 
                                    helpdesk_privilege):
        """
        Check privilege for use of extra data items to do with auto
        reverse IP setting and pyparsing error finformation
        """
        if (not admin_privilege):
            if (rr_data.get('lock_ptr')):
                raise AdminPrivilegeNeeded(self.name, rr_data,
                                        'lock_ptr')
                rr_data.pop('lock_ptr', None)
        if (not admin_privilege and not helpdesk_privilege):
            if rr_data.get('reference'):
                raise HelpdeskPrivilegeNeeded(self.name, rr_data,
                                        'reference')
                rr_data.pop('reference', None)

    def add_comment(self, top_comment, comment=None, tag=None, **kwargs):
        """
        Add a new comment or apex_comment
        """
        # Don't do anything unless 'comment' is supplied!
        if not comment and not top_comment:
            return None

        db_session = self.db_session
        # Deal with Apex comment - special, even set text to default 
        # if none!
        if (top_comment or tag == settings['apex_rr_tag']):
            if self.zone_sm.use_apex_ns:
                # If Apex done by global config, update routines 
                # will create an appropriate Apex comment
                return None
            if not comment:
                comment = settings['apex_comment_template'] % self.name
            tag = settings['apex_rr_tag']

        # Create a new comment
        rr_comment = RRComment(comment=comment, tag=tag)
        db_session.add(rr_comment)
        # Need to flush to get a new id from database
        db_session.flush()
        if (rr_comment.tag == settings['apex_rr_tag']):
            self.apex_comment = rr_comment
        return rr_comment.id_

    def get_apex_comment(self):
        """
        Return Apex Comment
        """
        return self.apex_comment
    
    def rr_data_create_comments(self, zi_data, zone_ttl, 
            creating_real_zi=True):
        """
        Common code for creating comments, and creating comment IDs
        """
        # Get comment IDs created and established.
        rr_group_data = zi_data.get('rr_groups')
        for rr_group in rr_group_data:
            rr_groups_index = rr_group_data.index(rr_group)
            top_comment = creating_real_zi and rr_groups_index == 0
            comment_group_id =  self.add_comment(top_comment, **rr_group)
            rr_group['comment_group_id'] = comment_group_id
            for rr_data in rr_group['rrs']:
                # get rr_groups_index and rrs_index for error handling
                rr_data['rrs_index'] = rr_group['rrs'].index(rr_data)
                rr_data['rr_groups_index'] = rr_groups_index
                # Handle comment IDs
                rr_data['comment_rr_id'] = self.add_comment(False, **rr_data)
                rr_data['comment_group_id'] = comment_group_id
                # Following needed to initialise dnspython RRs correctly
                rr_data['zone_ttl'] = zone_ttl
        self.rr_group_data = rr_group_data
        zi_data.pop('rr_groups', None)


    def add_rrs(self, rrs_func, add_rr_func, 
                admin_privilege, helpdesk_privilege,
                update_group=None):
        """
        Add RR to data base
        
        Note use of rrs_func so that list of rrs is always refreshed in
        function.  Can be supplied by using a no argument lambda function.
        This is so that in the case of a full ZI, rrs can be added to it,
        which is different to the case of incremental updates, where the 
        list of RRs is constructed, and the rrs just added directly to the
        resource records table.
        """
        db_session = self.db_session
        for rr_group in self.rr_group_data:
            for rr_data in rr_group['rrs']:
                # Remove unneeded keys from rr_data
                rr_data.pop('comment', None)
                rr_data.pop('zone_id', None)
                # Check privilege
                self.check_extra_data_privilege(rr_data, admin_privilege,
                        helpdesk_privilege)
                rr = data_to_rr(self.name, rr_data)
                self.check_rr_consistency(rrs_func(), rr, rr_data, update_group)
                # Store rr_data for zi consistency checks
                self.put_zi_rr_data(str(rr), rr_data)
                # Add rr to SQLAlchemy data structures
                db_session.add(rr)
                # Sort out RR reference part of the data structure
                rr_ref_str = rr_data.get('reference')
                if rr_ref_str: 
                    self.check_reference_string(rr_ref_str)
                    rr_ref = find_reference(db_session, rr_ref_str)
                    rr.ref_id = rr_ref.id_ if rr_ref else None
                    rr.reference = rr_ref
                # Sort out update_group if given
                if update_group:
                    update_group.update_ops.append(rr)
                add_rr_func(rr)
                self.handle_auto_ptr_data(rr, rr_data)

class PseudoZi(ZiUpdate):
    """
    Dummy ZI class so that ZiUpdate operations can do a trial run, so that 
    incremental updates can be consistency checked by zi checking code.
    """

    def __init__(self, db_session, zi):
        # make sure ZiUpdate runs in trial mode
        ZiUpdate.__init__(self, db_session=db_session, trial_run=True)
        # Copy rrs list so that changes do not trigger SQAlchemy
        self.rrs = []
        for rr in zi.rrs:
            rr_type = sql_types[type(rr).__name__]
            new_rr = rr_type(label=rr.label, domain=zi.zone.name, 
                    ttl=rr.ttl, zone_ttl=rr.zone_ttl,
                    rdata=rr.rdata, lock_ptr=rr.lock_ptr, disable=rr.disable,
                    track_reverse=rr.track_reverse)
            self.rrs.append(new_rr)


    def add_rr(self, rr):
        """
        Add RR to rrs list
        """
        self.rrs.append(rr)

    def remove_rr(self, rr):
        """
        Remove rr from rrs list
        """
        self.rrs.remove(rr)

class ZoneDataUtil(object):
    """
    Mix in class for ZoneEngine, containing _data_to_zi and _data_to_incr
    functions
    """

    def _data_to_zi(self, name, zi_data, change_by, normalize_ttls=False,
                admin_privilege=False, helpdesk_privilege=False):
        """
        Construct a new ZI, RRS and comments, from zone_data.
        """
            
        def set_missing_zi_data():
            """
            Set missing fields in supplied zi_data to prevent problems
            """
            # Set ZI Zone ttl if not already set
            if 'zone_ttl' not in zi_data:
                zi_data['zone_ttl'] = zone_ttl
            # Set other SOA values in zi_data from defaults 
            # if they are not there. soa_ttl can be None
            for field in ['soa_mname', 'soa_rname', 'soa_refresh', 'soa_retry', 
                    'soa_expire', 'soa_minimum']:
                if not zi_data.get(field):
                    zi_data[field] = zone_cfg.get_row_exc(db_session, field,
                                                        sg=zone_sm.sg)
            # We always update serial number on zone udpdate/publish
            # but it is nicer and probably less troublesome to replace 
            # an existing serial number that may be out there
            if not zi_data.get('soa_serial'):
                if zone_sm.soa_serial:
                    zi_data['soa_serial'] = zone_sm.soa_serial
                else:
                    # Obviously a new zone
                    zi_data['soa_serial'] = new_zone_soa_serial(db_session)

        def check_zi_data():
            """
            Check incoming zi_data attributes for correctness
            """
            for field in ['soa_mname', 'soa_rname']:
                validate_zi_hostname(name, field, zi_data[field])
            for field in ['soa_refresh', 'soa_retry', 'soa_expire',
                    'soa_minimum', 'soa_ttl', 'zone_ttl']:
                if field == 'soa_ttl' and not zi_data.get(field):
                    # SOA TTL can be None
                    continue
                validate_zi_ttl(name, field, zi_data[field])
            for field in ['soa_serial']:
                if field == 'soa_serial' and zi_data.get(field, None) == None:
                    # SOA serial can be None
                    continue
                # Check incoming data type of soa_serial
                if not isinstance(zi_data['soa_serial'], int):
                    raise SOASerialTypeError(name)
                if not ( 0 < zi_data['soa_serial'] <= (2**32-1)):
                    # RFC 2136 Section 4.2 AO serial cannot be zero
                    raise SOASerialRangeError(name)
            
        # Function start
        db_session = self.db_session
        # Get zone_sm to get zone ID etc
        zone_sm = self._get_zone_sm(name)
        zone_id = zone_sm.id_
        
        # initialise data and zone consistency checking
        data_tools = DataTools(db_session, zone_sm)
        
        # Sort out a candidate value for zone_ttl so that RRs can be created
        zone_ttl = zi_data.get('zone_ttl',
                zone_cfg.get_row_exc(db_session, 'zone_ttl', sg=zone_sm.sg))
        zone_ttl_supplied = 'zone_ttl' in zi_data

        # Create comments, and set up comment IDs, and stuff for handlng
        # RR Groups zi_data structures
        data_tools.rr_data_create_comments(zi_data, zone_ttl)

        # Deal with ZI data problems, and supply defaults if missing
        set_missing_zi_data()
        check_zi_data()
        # This constructor call sets attributes in zi as well!
        zi = ZoneInstance(change_by=change_by, **zi_data)
        db_session.add(zi)
        apex_comment = data_tools.get_apex_comment()
        if apex_comment:
            zi.add_apex_comment(apex_comment)
        # Get zi.id_ zi.zone_id from database
        db_session.flush()
        
        # Add RRs to zi
        # Note use of lambda so that list of rrs is always refreshed in
        # function
        data_tools.add_rrs(lambda :zi.rrs, zi.add_rr,
                admin_privilege, helpdesk_privilege)

        # tie zi into data_structures
        zone_sm.all_zis.append(zi)
        zi.zone = zone_sm
        db_session.flush()
        # Normalise TTLs here
        if normalize_ttls and zone_ttl_supplied:
            zi.normalize_ttls()
        # Update SOA and NS records - can't hurt to do it here
        # This also cleans out any incoming apex NS records if
        # client should not be setting them.
        zi.update_apex(db_session)
        # Update Zone TTLs for clean initialisation
        zi.update_zone_ttls()
        db_session.flush()
        # Check zone consistency. Do this here as Apex RRs need to be complete.
        data_tools.check_zi_consistency(zi.rrs)
        return zi, data_tools.get_auto_ptr_data()
    
    def _data_to_update(self, name, update_data, update_type, change_by,
            admin_privilege=False, helpdesk_privilege=False):
        """
        Construct an update group for a zone, from supplied RRS and comments.

        Functional equivalent of _data_to_zi() above, but for incremental 
        updates
        """
        # Function start
        db_session = self.db_session
        # Check that update_type is supplied
        if not update_type:
            raise UpdateTypeRequired(name)
        # Get zone_sm to get zone ID etc
        zone_sm = self._get_zone_sm(name)
        zone_id = zone_sm.id_

        # See if incremental updates are enabled for zone before queuing any
        if not zone_sm.inc_updates:
            raise IncrementalUpdatesDisabled(name)
        # Don't queue updates for a disabled zone
        if zone_sm.is_disabled():
            raise ZoneDisabled(name)
        # Privilege check for no apex zones - admin only 
        if not zone_sm.use_apex_ns and not admin_privilege:
            raise ZoneAdminPrivilegeNeeded(name)
       
        # Use candidate ZI as it always is available.  zi is published zi
        zi = self._get_zi(zone_sm.zi_candidate_id)
        if not zi:
            raise ZiNotFound(name, zone_sm.zi_candidate_id)

        # Get value of zone_ttl so that RRs can be created
        zone_ttl = zi.zone_ttl

        # Create RRs list from published ZI
        pzi = PseudoZi(db_session, zi)

        # initialise data and zone consistency checking
        zi_cname_flag = False
        if len([r for r in pzi.rrs if r.type_ == RRTYPE_CNAME]):
            zi_cname_flag = True
        data_tools = DataTools(db_session, zone_sm, zi_cname_flag)

        # Create comments, and set up comment IDs, and stuff for handlng
        # RR Groups zi_data structures
        data_tools.rr_data_create_comments(update_data, zone_ttl, 
                        creating_real_zi=False)
        try:
            # Create new update_group
            update_group = new_update_group(db_session, update_type, 
                                zone_sm, change_by)
        except IntegrityError as exc:
            raise UpdateTypeAlreadyQueued(name, update_type)

        # Add RRs to DB and operate on Pseudo ZI
        data_tools.add_rrs(lambda :pzi.rrs, pzi.trial_op_rr,
            admin_privilege, helpdesk_privilege, update_group=update_group)

        data_tools.check_zi_consistency(pzi.rrs)

        # Get all data out to DB, and ids etc established.
        db_session.flush()
        # Refresh zone to implement updates
        exec_zonesm(zone_sm, ZoneSMDoRefresh)

        # Return auto update info
        return data_tools.get_auto_ptr_data()

    def _queue_auto_ptr_data(self, auto_ptr_data):
        """
        Queue auto PTR data as incremental updates against respective reverse
        zones.
        """
        if not auto_ptr_data:
            return
        if not len(auto_ptr_data):
            return
        if not settings['auto_reverse']:
            return
        db_session = self.db_session
        # Create new update_group
        ug_dict = {}
        auto_ptr_privilege_flag = False
        for ptr_data in auto_ptr_data:
            # Ignore addresses we don't have reverse zone for
            query = db_session.query(ZoneSM)\
                    .join(ReverseNetwork)\
                    .filter(text(":address  <<= reverse_networks.network"))\
                    .params(address = ptr_data['address'])
            query = ZoneSM.query_is_not_deleted(query)
            query = ZoneSM.query_inc_updates(query)
            query = query.order_by(ReverseNetwork.network.desc())\
                    .limit(1)
            try:
                zone_sm = query.one()
            except NoResultFound:
                continue

            # Ignore invalid host names
            if not is_inet_hostname(ptr_data['hostname'], absolute=True,
                                    wildcard=False):
                log_error("Hostname '%s' is not a valid hostname." 
                        % ptr_data['hostname'])
                continue

            # Determine proposed update operation
            update_op = RROP_PTR_UPDATE_FORCE if ptr_data['force_reverse'] \
                            else RROP_PTR_UPDATE

            # Execute privilege checks ahead of time to save unnecessary churn
            # Better than needlessly going through whole rigamorole of 
            # incremental update processing later on for no effect
            #1 See if old PTR exists to retrieve any RR reference
            # Both following also used lower down when generating RR_PTR
            label = label_from_address(ptr_data['address'])
            rr_ref = find_reference(db_session, ptr_data['reference'],
                                        raise_exc=False)
            # query for old record - this generates one select
            # Optimization  - if check has previously suceeded, don't check
            # again as this is all checked further in
            if not auto_ptr_privilege_flag:
                qlabel= label[:label.rfind(zone_sm.name)-1]
                query = db_session.query(ResourceRecord)\
                    .filter(ResourceRecord.label == qlabel)\
                    .filter(ResourceRecord.zi_id == zone_sm.zi_candidate_id)\
                    .filter(ResourceRecord.disable == False)\
                    .filter(ResourceRecord.type_ == RRTYPE_PTR)
                old_rrs = query.all()
                old_rr = old_rrs[0] if len(old_rrs) else None
                
            # Check that we can proceed, only if check has not succeded yet
                if not check_auto_ptr_privilege(rr_ref, self.sectag, zone_sm,
                    old_rr):
                    if old_rr:
                        log_debug("Zone '%s' - can't replace '%s' PTR"
                            " as neither"
                            " sectags '%s' vs '%s'"
                            " references '%s' vs '%s'/'%s' (old PTR/rev zone)"
                            "match ,"
                            " or values not given."
                        % (zone_sm.name, old_rr.label,
                            self.sectag.sectag, settings['admin_sectag'],    
                            rr_ref, old_rr.reference, zone_sm.reference))
                    else:
                        log_debug("Zone '%s' - can't add '%s' PTR as neither"
                                " sectags '%s' vs '%s'"
                                " references '%s' vs '%s' (rev zone) match,"
                                " or values not given."
                            % (zone_sm.name, qlabel,
                                self.sectag.sectag, settings['admin_sectag'],    
                                rr_ref, zone_sm.reference))
                    continue
                auto_ptr_privilege_flag = True

            # Create a new update group if zone has not been seen before.
            try:
                update_group, zone_ttl = ug_dict.get(zone_sm)
            except (ValueError, TypeError):
                # Obtain reverse zone_ttl so PTR rrs can be created
                # Use candidate ZI as it always is available.
                # zi is published zi
                zi = self._get_zi(zone_sm.zi_candidate_id)
                if not zi:
                    log_error("Zone '%s': does not have candidate zi." 
                                % zone_sm.name)
                    continue
                zone_ttl = zi.zone_ttl
                update_group = new_update_group(db_session, None, 
                                        zone_sm, None, ptr_only=True, 
                                        sectag=self.sectag.sectag)
                ug_dict[zone_sm] = (update_group, zone_ttl)
            
            # Allocate RR_PTR update record
            rr = RR_PTR(label=label, zone_ttl=zone_ttl, 
                    rdata=ptr_data['hostname'], disable=ptr_data['disable'],
                    domain=zone_sm.name, update_op=update_op)
            rr.ref_id = rr_ref.id_ if rr_ref else None
            rr.reference = rr_ref

            # Chain on  RR_PTR update record
            update_group.update_ops.append(rr)

        # Flush everything to disk
        db_session.flush()
        # Issue zone refreshes to implement PTR changes
        for zone_sm in ug_dict:
            if zone_sm.is_disabled():
                continue
            exec_zonesm(zone_sm, ZoneSMDoRefresh)
        # Make sure everything is committed
        db_session.commit()

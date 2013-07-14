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
Zone instance record incremental update code.  In an inherited
class to stop overpopulating zone_instance object.
"""


import copy

from magcode.core.globals_ import *
from magcode.core.database import sql_types
from dms.dns import *
from dms.database.zone_query import rr_query_db_raw
from dms.auto_ptr_util import check_auto_ptr_privilege


class ZiUpdate(object):
    """
    Container mix in class for ZI update code.
    """

    def __init__(self, db_session=None, trial_run=False, name=None):
        """
        This only for use with the PsuedoZi class, in zone_data_util.py
        """
        self.db_session = db_session
        self._trial_run = trial_run
        self.name = name
    
    def _rrop_find(self, query_rr, match_type=True, match_rdata=True):
        """
        Given an update_rr, find any matching records in this ZI

        Match is done using DNS python  and label rdata for accuracy.
        Type matches don't use dnspython data as dnspython rdata
        form may not exist.
        """
        # Some constants
        q_label = query_rr.dnspython_rr[0]
        q_type = query_rr.type_
        q_rdata = query_rr.dnspython_rr[2]
        # 1 Match label
        result = [rr for rr in self.rrs 
                if query_rr.dnspython_rr[0] == rr.dnspython_rr[0] ]
        # 2 Match type
        if not match_type or q_type == RRTYPE_ANY:
            return result
        result = [rr for rr in result if q_type == rr.type_]
        if not match_rdata or not q_rdata:
            return result
        # 3 Match RDATA
        result = [rr for rr in result if query_rr.dnspython_rr[2] == q_rdata]
        # return list of results
        return result

    def _rrop_finish(self, op_rr):
        """
        Detach a record from update group, and clear update_op
        """
        op_rr.unlink = True
        if hasattr(self, '_trial_run') and self._trial_run:
            return
        op_rr.update_op = None
        op_rr.ug_id = None
    
    def _rrop_update_rrtype(self, db_session, op_rr, sectag_label):
        """
        Implement update operation
        """
        # Find RRs
        old_rrs = self._rrop_find(op_rr, match_rdata=False)
        # update it
        for rr in old_rrs:
            self.remove_rr(rr)
        self.add_rr(op_rr)
        self._rrop_finish(op_rr)


    def _rrop_add(self, db_session, op_rr, sectag_label):
        """
        Implement add operation
        """
        # Find RRs
        old_rrs = self._rrop_find(op_rr)
        # Exit if it already exists!
        if len(old_rrs):
            self._rrop_finish(op_rr)
            return 
        self.add_rr(op_rr)
        self._rrop_finish(op_rr)

    def _rrop_delete(self, db_session, op_rr, sectag_label):
        """
        Implement delete operation
        """
        # Find RRs
        old_rrs = self._rrop_find(op_rr)
        # Delete RRs
        for rr in old_rrs:
            self.remove_rr(rr)
            if hasattr(self, '_trial_run') and self._trial_run:
                continue
            db_session.delete(rr)

    def _rrop_ptr_update(self, db_session, op_rr, sectag_label, force=False):
        """
        Implement PTR update operation on zone
        """
        # Handle auto reverse disbale settings
        if not settings['auto_reverse']:
            log_debug("Zone '%s' - can't process '%s' "
                                "- auto_reverse_enable off."
                        % (self.zone.name, op_rr.label))
            return
        # make proper sectag
        ZoneSecTag = sql_types['ZoneSecTag']
        sectag = ZoneSecTag(sectag_label)
        # Find old RRs
        old_rrs = self._rrop_find(op_rr, match_rdata=False)
        if len(old_rrs) > 1:
            log_error("Zone '%s' - multple PTR records for '%s', "
                        "contrary to RFC 1035 Section 3.5, not updating."
                        % (self.zone.name, op_rr.label))
            return
        old_rr = old_rrs[0] if len(old_rrs) else None
        
        # Check that we can proceed
        if not check_auto_ptr_privilege(op_rr.reference,
                sectag, self.zone, old_rr):
            if old_rr:
                log_debug("Zone '%s' - can't replace '%s' PTR as neither"
                    " sectags '%s' vs '%s'"
                    " references '%s' vs '%s'/'%s' (old PTR/rev zone) match,"
                    " or values not given."
                    % (self.zone.name, old_rr.label,
                        sectag.sectag, settings['admin_sectag'],    
                        op_rr.reference, old_rr.reference, self.zone.reference))
            else:
                log_debug("Zone '%s' - can't add '%s' PTR as neither"
                        " sectags '%s' vs '%s'"
                        " references '%s' vs '%s' (rev zone) match,"
                        " or values not given."
                    % (self.zone.name, op_rr.label,
                        sectag.sectag, settings['admin_sectag'],    
                        op_rr.reference, self.zone.reference))
            return
       
        if not force: 
            # Don't auto create PTRs if its not enabled.
            if (self.zone.name.endswith('in-addr.arpa.')
                    and not settings['auto_create_ipv4_ptr']):
                log_debug("Zone '%s' - can't process '%s' "
                                        "- auto_create_ipv4_ptr off."
                                % (self.zone.name, op_rr.label))
                return
            elif (self.zone.name.endswith('ip6.arpa.')
                    and not settings['auto_create_ipv6_ptr']):
                log_debug("Zone '%s' - can't process '%s' "
                                        "- auto_create_ipv6_ptr off."
                                % (self.zone.name, op_rr.label))
                return

        # See if forward still exists in DB
        if old_rr:
            if old_rr.lock_ptr:
                # Can't change if record locked
                log_debug("Zone '%s' - can't replace '%s' PTR as it is locked."
                    % (self.zone.name, old_rr.label)) 
                return
            # if new PTR same as old, ignore it!
            if op_rr == old_rr:
                log_debug("Zone '%s' - not replacing as '%s' PTR still the "
                        "same - rdata '%s'." 
                    % (self.zone.name, old_rr.label,
                        old_rr.rdata))
                return
            if not force:
                if self.zone.name.endswith('in-addr.arpa.'):
                    type_ = RRTYPE_A
                elif self.zone.name.endswith('ip6.arpa.'):
                    type_ = RRTYPE_AAAA
                else:
                    log_debug("Zone '%s' - can't determine Ip address "
                                            "record type" % self.zone.name)
                    return
                address = address_from_label(op_rr.label + '.' + self.zone.name)
                if not address:
                    log_warn("Zone '%s' - can't determine IP address from "
                            "label '%s' and domain!" 
                            % (self.zone.name, op_rr.label))
                    return
                result = rr_query_db_raw(db_session, 
                        label=old_rr.rdata, type_=type_, rdata=address)
                if result and len(result.get('rrs', [])):
                    # can't replace as old forward still active in DB
                    log_debug("Zone '%s' - can't replace '%s' PTR as old PTR "
                            "still valid - '%s'." 
                            % (self.zone.name, old_rr.label, 
                                old_rr.rdata))
                    return
            # Remove old RRs and update PTR
            for rr in old_rrs:
                self.remove_rr(rr)
        self.add_rr(op_rr)
        self._rrop_finish(op_rr)

    def _rrop_ptr_update_force(self, db_session, op_rr, sectag_label):
        """
        Implement PTR update operation on zone
        """
        self._rrop_ptr_update(db_session, op_rr, sectag_label, force=True)

    def trial_op_rr(self, op_rr):
        """
        Do a trial run of the operation
        """
        if not self._trial_run:
            # Should throw an Exception here.
            raise IncrementalUpdateNotInTrialRun(self.name)
        if not self._update_op_map.get(op_rr.update_op):
            log_error("Zone '%s': no method for update operation '%s'"
                        % (self.name, op_rr.update_op))
        op_rr.unlink = False
        # This is only trial execution of operation on zone that is 
        # already retrieved with sectag evaluation, sectag only for auto PTR
        # operations on a reverse zone
        sectag = None
        self._update_op_map[op_rr.update_op](self, self.db_session, 
                                                    op_rr, sectag)


    def exec_update_group(self, db_session, update_group):
        """
        Run an update group, and then clean up
        """
        ops_list = copy.copy(update_group.update_ops)
        for op_rr in ops_list:
            op_rr.unlink = False 
            if not self._update_op_map.get(op_rr.update_op):
                log_error("Zone '%s': no method for update operation '%s'"
                            % (self.zone.name, op_rr.update_op))
                continue
            self._update_op_map[op_rr.update_op](self, db_session, op_rr, 
                                                    update_group.sectag)
        # only go further than this if trial run
        if hasattr(self, '_trial_run') and self._trial_run:
            return
        # Complete addition of op_rrs to ZI
        for op_rr in ops_list:
            if not op_rr.unlink:
                db_session.delete(op_rr)
                continue
            update_group.update_ops.remove(op_rr)
        # Record source of the change
        if update_group.change_by:
            self.change_by = update_group.change_by
        # CASCADE constraint will remove all op_rrs not unlinked above
        db_session.delete(update_group)
        db_session.flush()

    # Map update operation functions to their OP tags   
    _update_op_map = {RROP_UPDATE_RRTYPE: _rrop_update_rrtype,
                        RROP_ADD: _rrop_add,
                        RROP_DELETE: _rrop_delete,
                        RROP_PTR_UPDATE: _rrop_ptr_update,
                        RROP_PTR_UPDATE_FORCE: _rrop_ptr_update_force
                        }


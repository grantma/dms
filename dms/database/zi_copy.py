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
Zone instance copying using internal python data structures   Mix in class to modularise ZI classes.
"""


from magcode.core.globals_ import *
from magcode.core.database import *
from dms.dns import RRTYPE_A
from dms.dns import RRTYPE_AAAA


class ZiCopy(object):
    """
    Contains methods for ZI copying via internal structures
    """

    def copy(self, db_session, change_by=None):
        """
        Copy ZI

        First initialise base ZI, coppy  comment structure set up,
        then add records.
        """
        ZoneInstance = sql_types['ZoneInstance']
        RRComment = sql_types['RRComment']
        # Keep previous change_by if it is not being changed. This is useful
        # for auto PTR updates
        if not change_by:
            change_by = self.change_by
        new_zi = ZoneInstance(zone_id=self.zone_id, soa_serial=self.soa_serial,
                soa_mname=self.soa_mname, soa_rname=self.soa_rname,
                soa_refresh=self.soa_refresh, soa_retry=self.soa_retry,
                soa_expire=self.soa_expire, soa_minimum=self.soa_minimum,
                soa_ttl=self.soa_ttl, zone_ttl=self.zone_ttl,
                change_by=change_by)
        db_session.add(new_zi)
        new_zi.zone = self.zone
        
        # Establish Apex comment, which is a special RR_Groups comment
        # This dict establishes relN between new group comment and old one
        # by indexing the new comment against the old comments id
        rr_group_comments = {}
        if self.apex_comment:
            new_apex_comment = RRComment(comment=self.apex_comment.comment,
                                        tag=self.apex_comment.tag)
            db_session.add(new_apex_comment)
            new_zi.apex_comment = new_apex_comment
            rr_group_comments[self.apex_comment.id_] = new_apex_comment
        
        # Establish rest of RR_Groups comments
        for comment in self.rr_group_comments:
            if self.apex_comment and comment is self.apex_comment:
                # Apex comment is already done above here
                continue
            new_comment = RRComment(comment=comment.comment, tag=comment.tag)
            db_session.add(new_comment)
            rr_group_comments[comment.id_] = new_comment
        
        # For the sake of making code clearer, do same for RR_Comments as
        # for group comments
        rr_comments = {}
        for comment in self.rr_comments:
            new_comment = RRComment(comment=comment.comment, tag=comment.tag)
            db_session.add(new_comment)
            rr_comments[comment.id_] = new_comment

        # Walk zi RRs, and copy them as we go
        for rr in self.rrs:
            rr_type = sql_types[type(rr).__name__]
            new_rr = rr_type(label=rr.label, domain=self.zone.name, 
                    ttl=rr.ttl, zone_ttl=rr.zone_ttl,
                    rdata=rr.rdata, lock_ptr=rr.lock_ptr, disable=rr.disable,
                    track_reverse=rr.track_reverse)
            db_session.add(new_rr)
            new_zi.rrs.append(new_rr)
            if rr_group_comments.get(rr.comment_group_id):
                rr_group_comment = rr_group_comments[rr.comment_group_id]
                new_rr.group_comment = rr_group_comment
                # Uncomment if above is not 'taking'
                # rr_group_comment.rr_group.append(new_rr)
            if rr_comments.get(rr.comment_rr_id):
                rr_comment = rr_comments[rr.comment_rr_id]
                new_rr.rr_comment = rr_comment
                # Uncomment if above is not 'taking'
                # rr_comment.rr = new_rr
            if hasattr(rr, 'reference') and rr.reference:
                # Done this way as relationship is 'loose', 
                # SA relN is 'viewonly=True'
                new_rr.ref_id = rr.ref_id
        # Flush to DB to fill in record IDs
        db_session.flush()
        return new_zi

    def get_auto_ptr_data(self, zone_sm):
        """
        Return auto_ptr_data for the zi
        """
        auto_ptr_data = []
        zone_ref = zone_sm.reference
        zone_ref_str = zone_ref.reference if zone_ref else None
        for rr in self.rrs:
            if rr.type_ not in (RRTYPE_A, RRTYPE_AAAA):
                continue
            # Use the dnspython rewritten rdata to make sure that IPv6
            # addresses are uniquely written.
            hostname = rr.label + '.' + zone_sm.name \
                        if rr.label != '@' else zone_sm.name
            disable = rr.disable
            auto_ptr_data.append({ 'address': rr.rdata,
                                        'disable': disable,
                                        'force_reverse': False,
                                        'hostname': hostname,
                                        'reference': zone_ref_str})
        return auto_ptr_data


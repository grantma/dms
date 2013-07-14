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
Zone instance record.  Maps a zi_id to zone_id
"""


import dns.ttl
from sqlalchemy.orm import relationship
from sqlalchemy.orm.session import object_session 
from sqlalchemy.orm.session import make_transient 

from magcode.core.database import *
from dms.database.zi_update import *
from dms.database.zi_copy import *
from dms.dns import RRTYPE_SOA
from dms.dns import RRTYPE_NS
from dms.dns import new_zone_soa_serial
import dms.database.zone_cfg as zone_cfg
from dms.database.resource_record import RR_SOA
from dms.database.resource_record import RR_NS

@saregister
class ZoneInstance(ZiUpdate, ZiCopy):
    """
    Zone Instance type.
    """
    _table="zone_instances"

    @classmethod
    def _mapper_properties(class_):
        """
        Set up relationship to resource_records table
        """
        zi_table = sql_data['tables'][sql_types['ZoneInstance']]
        rr_table = sql_data['tables'][sql_types['ResourceRecord']]
        rr_comments_table = sql_data['tables'][sql_types['RRComment']]
        zone_sm_type = sql_types['ZoneSM']
        rr_comment_type = sql_types['RRComment']
        rr_type = sql_types['ResourceRecord']
        zone_sm_table = sql_data['tables'][zone_sm_type]
        return {'rrs': relationship(sql_types['ResourceRecord'],
                                passive_deletes=True),
                # No backref given in zone_sm as all_zis is dynamic loading
                'zone':         relationship(zone_sm_type, 
                                primaryjoin=(zone_sm_table.c.get('id')
                                    == zi_table.c.zone_id), viewonly=True),
                'rr_group_comments': relationship(rr_comment_type,
                                primaryjoin=(zi_table.c.get('id')
                                    == rr_table.c.zi_id),
                                secondary=sql_data['tables'][rr_type],
                                secondaryjoin=(rr_table.c.comment_group_id
                                    == rr_comments_table.c.get('id')),
                                viewonly=True),
                'rr_comments': relationship(rr_comment_type,
                                primaryjoin=(zi_table.c.get('id')
                                    == rr_table.c.zi_id),
                                secondary=sql_data['tables'][rr_type],
                                secondaryjoin=(rr_table.c.comment_rr_id
                                    == rr_comments_table.c.get('id')),
                                viewonly=True),
                'apex_comment': relationship(rr_comment_type,
                                    uselist=False,
                                    primaryjoin=(
                                        zi_table.c.apex_comment_group_id 
                                        == rr_comments_table.c.get('id'))),
                }

    def __init__(self, zone_id=None,
            soa_serial=None, soa_refresh=None, soa_retry=None,
            soa_expire=None, soa_minimum=None, soa_mname=None, 
            soa_rname=None, soa_ttl=None, zone_ttl=None, change_by=None 
            ):
        """
        Initialise a Zone Instance row
        """
        self.zone_id = zone_id
        self.soa_serial = soa_serial
        self.soa_refresh = soa_refresh
        self.soa_retry = soa_retry
        self.soa_expire = soa_expire
        self.soa_minimum = soa_minimum
        self.soa_mname = soa_mname
        self.soa_rname = soa_rname
        self.soa_ttl = soa_ttl
        self.zone_ttl = zone_ttl
        self.change_by = change_by
        

    def add_rr(self, rr):
        """
        Add RR to rrs list
        """
        if (not hasattr(self, 'rrs') or not self.rrs):
            self.rrs = []
        self.rrs.append(rr)

    def remove_rr(self, rr):
        """
        Remove RR from self.rrs
        """
        if (not hasattr(self, 'rrs') or not self.rrs):
            self.rrs = []
        self.rrs.remove(rr)

    def get_soa_serial(self):
        """
        Update the SOA serial in the ZI, if it has an SOA (as it should
        when submitted to the update engine.
        """
        # Find SOA record, return if not there.
        rr = [r for r in self.rrs if type(r) == RR_SOA][0]
        serial = rr.get_serial()
        return serial

    def update_soa_serial(self, serial):
        """
        Update the SOA serial in the ZI, if it has an SOA (as it should
        when submitted to the update engine.
        """
        # Find SOA record, return if not there.
        rr = [r for r in self.rrs if type(r) == RR_SOA][0]
        self.soa_serial = serial
        rr.update_serial(serial)

    def update_soa_record(self, db_session):
        """
        Form new SOA record from the information stored in the zi
        """
        if self.zone.use_apex_ns:
            # Read in values from DB global config
            sg = self.zone.sg
            mname = zone_cfg.get_row(db_session, 'soa_mname', sg=sg)
            rname = zone_cfg.get_row(db_session, 'soa_rname', sg=sg)
            refresh = zone_cfg.get_row(db_session, 'soa_refresh', sg=sg)
            retry = zone_cfg.get_row(db_session, 'soa_retry', sg=sg)
            expire = zone_cfg.get_row(db_session, 'soa_expire', sg=sg)
            # Update zi if different
            if mname != self.soa_mname:
                self.soa_mname = mname
            if rname != self.soa_rname:
                self.soa_rname = rname
            if refresh != self.soa_refresh:
                self.soa_refresh = refresh
            if retry != self.soa_retry:
                self.soa_retry = retry
            if expire != self.soa_expire:
                self.soa_expire = expire
            # Set the SOA TTL from zone_ttl so no TTL 'funnies' happen
            # when use_apex_ns is set
            if self.soa_ttl:
                self.soa_ttl = None

        rdata = ("%s %s %s %s %s %s %s" 
                    % (self.soa_mname, self.soa_rname, self.soa_serial,
                            self.soa_refresh, self.soa_retry, self.soa_expire,
                            self.soa_minimum))
        ttl = self.soa_ttl
        zone_ttl = self.zone_ttl
        new_soa_rr = RR_SOA(label='@', ttl=ttl, zone_ttl=zone_ttl,
                rdata=rdata, domain=self.zone.name)
        
        # Put in new SOA record
        # Remove every soa rr but the first. Have to be careful as deleting
        # from lists while looping over them can be problematic, and ordering
        # can influence SQL statement ordering, which could be sensitive here.
        # Being hyper cautious here...
        old_soa_rrs = [r for r in self.rrs if type(r) == RR_SOA]
        if len(old_soa_rrs):
            # Remove every soa rr but the first, then grab comment, then remove
            # thold SOA RR.
            old_soa_rr = old_soa_rrs.pop(0)
            for rr in old_soa_rrs:
                self.remove_rr(rr)
                db_session.delete(rr)
            rr_comment = old_soa_rr.rr_comment
            self.remove_rr(old_soa_rr)
            db_session.delete(old_soa_rr)
        else:
            rr_comment = None
        self.add_rr(new_soa_rr)
        db_session.add(new_soa_rr)
        new_soa_rr.group_comment = self.apex_comment
        new_soa_rr.rr_comment = rr_comment

    def update_apex_ns_records(self, db_session):
        """
        Update the apex NS records
        """
        # Check that Apex NS servers are configured.
        apex_ns_names = zone_cfg.get_rows(db_session, settings['apex_ns_key'],
                                            sg=self.zone.sg)
        if not apex_ns_names:
            log_critical("No Apex NS servers are configured, " 
                                "using current ones")
            return False

        # Locate all apex NS records
        old_apex_ns_rrs = [r for r in self.rrs 
                if (type(r) == RR_NS and r.label == '@')]
        # delete them (seperate from above as delete can affect loop!)
        for rr in old_apex_ns_rrs:
            self.remove_rr(rr)
            db_session.delete(rr)

        # Add new apex NS records from zone_cfg table
        apex_comment = self.apex_comment
        for ns_name in apex_ns_names:
            rr = RR_NS('@', zone_ttl=self.zone_ttl, rdata=ns_name,
                        domain=self.zone.name)
            self.add_rr(rr)
            db_session.add(rr)
            rr.group_comment = apex_comment
        return True
    
    def update_apex(self, db_session, force_apex_ns=False):
        """
        Update Apex SOA and NS records, according to zone_sm.use_apex_ns 
        flag
        """
        self.update_apex_comment(db_session)
        self.update_soa_record(db_session)
        if self.zone.use_apex_ns or force_apex_ns:
            self.update_apex_ns_records(db_session)

    def update_apex_comment(self, db_session):
        """
        Maintain the Zone Apex RRComment
        """
        comment = settings['apex_comment_template'] % self.zone.name
        RRComment = sql_types['RRComment']
        if not self.apex_comment:
            rr_comment = RRComment(comment=comment,
                                    tag=settings['apex_rr_tag'])

            db_session.add(rr_comment)
            self.apex_comment = rr_comment
        else:
            if self.zone.use_apex_ns:
                self.apex_comment.comment = comment
            self.apex_comment.tag = settings['apex_rr_tag']

    def set_apex_comment_text(self, db_session, comment):
        """
        set the text of the Apex Comment
        """
        if not self.apex_comment:
            self.update_apex_comment(db_session)
        if self.zone.use_apex_ns:
            return
        # OK, we can set the apex comment
        self.apex_comment.comment = comment

    def add_apex_comment(self, apex_comment):
        """
        Add the apex comment to the zi
        """
        # only called when constructing zi to save in ZoneEngine._data_to_zi()
        self.apex_comment = apex_comment

    def update_zone_ttls(self, zone_ttl=None, reset_rr_ttl=False):
        """
        Update the zone_ttl across the zi
        """
        if (zone_ttl 
                and dns.ttl.from_text(str(zone_ttl)) 
                    != dns.ttl.from_text(self.zone_ttl)):
            # Only update zi.zone_ttl if it is different - don't
            # surprise people unless it is needed.
            self.zone_ttl = str(zone_ttl)
        for rr in self.rrs:
            rr.update_zone_ttl(self.zone_ttl, reset_rr_ttl)

    def normalize_ttls(self):
        """
        Fixes up ttls in records by finding most common ttl, and blanking the
        ttl field of the resource records with ttl, and setting the zone_ttl
        to the mode. This should find  a value $TTL 
        """
        # Find mode (the hard way!)
        ttl_dict = {}
        for rr in self.rrs:
            rr_ttl = dns.ttl.from_text(rr.ttl) if rr.ttl \
                            else dns.ttl.from_text(rr.zone_ttl) 
            if (rr_ttl in ttl_dict):
                ttl_dict[rr_ttl] += 1
            else:
                ttl_dict[rr_ttl] = 1
        if (not len(ttl_dict)):
            return
        ttl_mode = None
        ttl_max_freq = 0
        for ttl in ttl_dict:
            if ttl_mode is None:
                ttl_mode = ttl
            if ttl_dict[ttl] > ttl_max_freq:
                ttl_mode = ttl
                ttl_max_freq = ttl_dict[ttl]
        self.update_zone_ttls(ttl_mode, reset_rr_ttl=True)
        return

    def iterate_dnspython_rrs(self):
        """
        Iterate through all the dnspython_rr tuples in this zone instance
        """
        for rr in self.rrs:
            if rr.disable:
                # If Record disabled, skip it.
                continue
            yield(tuple(rr.dnspython_rr))

    def to_engine_brief(self, time_format=None):
        """
        Supply data output in brief as a dict.  
        Just zi_id, zone_id, ctime, mtime.
        """
        if not time_format:
            mtime = self.mtime.isoformat(sep=' ') if self.mtime else None
            ctime = self.ctime.isoformat(sep=' ') if self.ctime else None
            ptime = self.ptime.isoformat(sep=' ') if self.ptime else None
        else:
            mtime = self.mtime.strftime(time_format) if self.mtime else None
            ctime = self.ctime.strftime(time_format) if self.ctime else None
            ptime = self.ptime.strftime(time_format) if self.ptime else None

        return {'zi_id': self.id_, 'zone_id': self.zone_id, 
                'ctime': ctime, 'mtime': mtime, 'ptime': ptime, 
                'soa_serial': self.soa_serial, 'change_by': self.change_by}

    def to_engine(self, time_format=None):
        """
        Return all fields as a dict
        """
        if not time_format:
            mtime = self.mtime.isoformat(sep=' ') if self.mtime else None
            ctime = self.ctime.isoformat(sep=' ') if self.ctime else None
            ptime = self.ptime.isoformat(sep=' ') if self.ptime else None
        else:
            mtime = self.mtime.strftime(time_format) if self.mtime else None
            ctime = self.ctime.strftime(time_format) if self.ctime else None
            ptime = self.ptime.strftime(time_format) if self.ptime else None

        return {'zi_id': self.id_, 'zone_id': self.zone_id, 
                'ctime': ctime, 'mtime': mtime, 'ptime': ptime,
                'change_by': self.change_by,
                'soa_serial': self.soa_serial,
                'soa_mname': self.soa_mname,
                'soa_rname': self.soa_rname,
                'soa_refresh': self.soa_refresh,
                'soa_retry': self.soa_retry,
                'soa_expire': self.soa_expire,
                'soa_minimum': self.soa_minimum,
                'soa_ttl': self.soa_ttl,
                'zone_ttl': self.zone_ttl}

    def to_data(self, time_format=None, use_apex_ns=True, all_rrs=False):
        """
        A full zi output with RRs grouped by comment
        """
        # Get given zi as a dict
        result = self.to_engine(time_format=time_format)
        # Get all resource records and group by RR_Group.
        rrs = [rr.to_engine() for rr in self.rrs]
        # Get all the comments, and store them in dicts by id for reference
        rr_group_comments = {}
        for c in self.rr_group_comments:
            # Don't emit comment IDs into JSON
            rr_group_comments[c.id_] = {'comment': c.comment, 'tag': c.tag}
        rr_comments = {}
        for c in self.rr_comments:
            # Don't emit comment IDs into JSON
            rr_comments[c.id_] = {'comment': c.comment, 'tag': c.tag}

        # Header records
        if not all_rrs:
            # Clean out stuff we will not be sending.
            # SOA RR
            rrs = [r for r in rrs if r['type'] != RRTYPE_SOA]
            # apex_ns
            if use_apex_ns:
                rrs = [r for r in rrs
                            if not(r['label'] == '@'
                                and r['type'] == RRTYPE_NS)]

        # RR level commments
        for rr in rrs:
            if rr['comment_rr_id']:
                comment_id = rr['comment_rr_id']
                comment_dict = rr_comments.get(comment_id, None)
                if comment_dict:
                    rr.update(comment_dict)
            del rr['comment_rr_id']

        # Group records by comment_group_id
        rr_groups = {}
        for rr in rrs:
            comment_id = rr['comment_group_id']
            if not comment_id in rr_groups:
                comment_dict = rr_group_comments.get(comment_id, None)
                rr_group = {}
                if comment_dict:
                    rr_group.update(comment_dict)
                rr_group['rrs'] = [rr]
                rr_groups[comment_id] = rr_group
            else:
                rr_groups[comment_id]['rrs'].append(rr)
            # Strip rr comment_group_id
            del rr['comment_group_id']

        result['rr_groups'] = list(rr_groups.values())
        return result


def get_default_zi_data(db_session, sg_name=None):
    """
    Return default zi data from zone_cfg table

    This is called from wsgi code or zone_tool
    """
    zi_data = {}
    soa_fields = ['soa_mname', 'soa_rname', 'soa_refresh', 
            'soa_retry', 'soa_expire', 'soa_minimum']
    for field in soa_fields:
        zi_data[field] = zone_cfg.get_row_exc(db_session, field, 
                sg_name=sg_name)
    zi_data['zone_ttl'] = zone_cfg.get_row_exc(db_session, 'zone_ttl', 
                    sg_name=sg_name)
    zi_data['soa_ttl'] = None
    zi_data['soa_serial'] = new_zone_soa_serial(db_session)
    return zi_data
     

def new_zone_zi(db_session, zone_sm, change_by):
    zi = ZoneInstance(change_by=change_by, 
            **get_default_zi_data(db_session, zone_sm.sg.name))
    db_session.add(zi)
    zi.zone = zone_sm
    zone_sm.all_zis.append(zi)
    db_session.flush()
    # Update SOA and apex NS records
    # Add some NS records to no_use_apex_ns zone so that zone gets
    # into named.
    zi.update_apex(db_session, force_apex_ns=True)
    db_session.flush()
    return zi




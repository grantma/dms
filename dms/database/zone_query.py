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
DMS DB Zone Query Support
"""


from sqlalchemy.orm.exc import NoResultFound 

from magcode.core.database import *


def rr_query_db_raw(db_session, label, name=None, type_=None, zi_id=None,
        rdata=None, include_disabled=False, sectag=None):
    """
    Function to query Zone DB, and return records
    """
    # We get types from sql_types to avoid import nesting problems
    ZoneSM = sql_types['ZoneSM']
    ResourceRecord = sql_types['ResourceRecord']
    query_kwargs = {'label': label, 'name': name, 'type': type_, 'rdata': rdata,
            'zi_id': zi_id, 'include_disabled': include_disabled}
    domain = name
    zone_sm = None
    # Adjust domain and label if needed
    if not domain:
        # Walk up label from root '.' to obtain most specific Zone in DB
        # Stip dot to label if it already does not have one
        if  not label.endswith('.'):
            label = label + '.'
        label = label.lower()
        node_labels = label.split('.')
        node_labels.reverse()
        node_labels = node_labels[1:]
        test_domain = ''
        for l in node_labels:
            # Find most specific domain in DB by accumlating the node labels
            test_domain = l + '.' + test_domain
            if test_domain == '.':
                # Skip root domain
                continue
            try:
                query = db_session.query(ZoneSM)\
                        .filter(ZoneSM.name == test_domain)
                if not include_disabled:
                    query = ZoneSM.query_is_not_disabled_deleted(query)
                else:
                    query = ZoneSM.query_is_not_deleted(query)
                zone_sm = query.one()
            except NoResultFound:
                continue
            if(sectag and zone_sm and sectag.sectag != settings['admin_sectag'] 
                    and sectag not in zone_sm.sectags):
                continue
            domain = test_domain
       
        if not zone_sm:
            return None
        d_index = label.rfind(domain)
        if d_index == 1:
            raise ValueError("Domain must not start with a '.'")
        elif (d_index > 1):   
            label = label[:(d_index-1)]
        else:
            label = '@'
    else:
        # Check input
        if not domain.endswith('.'):
            domain += '.'
        if domain[0] == '.':
            raise ValueError("Domain must not start with a '.'")
        domain = domain.lower()
        label = label.lower()
        if not label:
            label = '@'
        # Check if domain exists
        try:
            query = db_session.query(ZoneSM)\
                        .filter(ZoneSM.name == domain)
            if not include_disabled:
                query = ZoneSM.query_is_not_disabled_deleted(query)
            else:
                query = ZoneSM.query_is_not_deleted(query)
            zone_sm = query.one()
        except NoResultFound:
            return None
        if(sectag and zone_sm and sectag.sectag != settings['admin_sectag'] 
                and sectag not in zone_sm.sectags):
            return None
    # Now we have a valid domain, time to match the records within it 
    # Replace wildcards in label with SQL wild cards
    label = label.replace('*', '%')
    label = label.replace('?', '_')
    # Perform Query
    if zi_id == None:
        zi_id = zone_sm.zi.id_
    query = db_session.query(ResourceRecord)\
            .filter(ResourceRecord.label.like(label))
    if zi_id:
        if isinstance(zi_id, tuple) or isinstance(zi_id, list):
            query = query.filter(ResourceRecord.zi_id.in_(zi_id))
        else:
            query = query.filter(ResourceRecord.zi_id == zi_id)
    if not include_disabled:
        query = query.filter(ResourceRecord.disable == False)
    if type_:
        if isinstance(type_, tuple) or isinstance(type_, list):
            type_ = [ t.upper() for t in type_ ]
            query = query.filter(ResourceRecord.type_.in_(type_))
        else:
            query = query.filter(ResourceRecord.type_ == type_.upper())
    if rdata:
        query = query.filter(ResourceRecord.rdata == rdata)
    rrs = query.all()
    if not len(rrs):
        return None
    label = label.replace('%', '*')
    label = label.replace('_', '?')
    result = {'query': query_kwargs, 'label': label, 'name': zone_sm.name, 
            'zone_sm': zone_sm, 'zi_id': zi_id, 'rrs': rrs}
    return result



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

import re

import dns
import dns.name
import dns.rdatatype
import dns.rdataclass
import dns.ttl
import dns.rdata
import dns.exception

from sqlalchemy.orm import reconstructor
from sqlalchemy.orm import relationship

from magcode.core.database import *
from dms.dns import *
from dms.exceptions import *
import dms.database.rr_comment


# Dictionary for mapping Record Type to Resource Record Class
rrtype_map = {}

# Lists we use in global sql_data dict
sql_data['rr_subclasses'] = []
sql_data['rr_type_list'] = []


def rr_register(class_):
    """
    Resorce record descedant class decorator function to register class for SQL
    Alchemy mapping in init_rr_class() below, called from
    magcode.core.database.utility.setup_sqlalchemy()
    """
    sql_data['rr_subclasses'].append(class_)
    rrtype_map[class_._rr_type] = class_
    # Also add as an SQL data type
    typeregister(class_)
    return(class_)

@typeregister
class ResourceRecord(object):
    """
    DNS Resource Record type.
    """
   
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_NULL

    @classmethod
    def sa_map_subclass(class_):
        metadata = MetaData()
        sql_data['mappers'][class_] = mapper(class_,
                    inherits=sql_data['mappers'][ResourceRecord], 
                    polymorphic_identity=class_._rr_type)
        sql_data['rr_type_list'].append(class_._rr_type)
    
    @classmethod
    def _mapper_properties(class_):
        rr_table = sql_data['tables'][sql_types['ResourceRecord']]
        rr_comment_table = sql_data['tables'][sql_types['RRComment']]
        ref_type = sql_types['Reference']
        ref_table = sql_data['tables'][ref_type]
        return {'rr_comment': relationship(sql_types['RRComment'],
                                    primaryjoin=(rr_table.c.comment_rr_id 
                                            == rr_comment_table.c.get('id')),
                                        uselist=False,
                                        backref="rr"),
                'group_comment': relationship(sql_types['RRComment'],
                                    primaryjoin=(rr_table.c.comment_group_id 
                                            == rr_comment_table.c.get('id')),
                                        backref="rr_group"),
                'reference': relationship(sql_types['Reference'],
                                        viewonly=True),
                }

    def __init__(self, label=None, ttl=None, zone_ttl=None, rdata=None,
            domain=None, dnspython_rr=None, comment_rr_id=None, 
            comment_group_id=None, lock_ptr=False, disable=False, ref_id=None,
            ug_id=None, update_op=None, track_reverse=False, **kwargs):
        """
        Initialise resource record, and build private
        dnspython rdata tuple for comparison  and parse checking purposes.
        """
        # Swallow type and class arguments, otherwise raise exception
        kwargs = [arg for arg in kwargs if (arg != 'type' and arg != 'class')]
        if kwargs:
            raise TypeError(
                    "__init__() got an unexpected keyword argument '%s'" 
                    % kwargs[0])

        if domain:
            # Check that domain ends in '.'
            if not domain.endswith('.'):
                raise dns.exception.SyntaxError(
                                    "domain '%s' must end with '.'." 
                                    % domain)
            # Relativize label
            label = relativize_domain_name(label, domain)
            # label should not now be an FQDN!
            if label.endswith('.'):
                raise dns.exception.SyntaxError(
                                "FQDN label '%s' is not within domain '%s'."
                                % (label, domain))
            # Make domain dnspython dns.name.Name
            domain = dns.name.from_text(domain)

        # Check that rdata IS supplied
        # This closes hole in error handling - these are the only
        # times when rdata can be blank
        if (not rdata and not dnspython_rr and self._rr_type != RRTYPE_ANY and 
                update_op != RROP_DELETE):
            raise ValueError("rdata must be supplied")

        self.label = label
        self.ttl = ttl
        self.zone_ttl = zone_ttl
        self.rdata = rdata
        self.comment_rr_id = comment_rr_id
        self.comment_group_id = comment_group_id
        self.lock_ptr = lock_ptr
        self.disable = disable
        self.ref_id = ref_id
        self.update_op = update_op
        self.ug_id = ug_id
        self.track_reverse = track_reverse
        self.type_ = self._rr_type
        self.class_ = self._rr_class
        if dnspython_rr:
            # if given dnspython_rr tuple, assume it is already
            # relativized by dnspython (default in zone scanning/parsing)
            self.dnspython_rr = dnspython_rr
            self.label = str(self.dnspython_rr[0])
            self.ttl = str(self.dnspython_rr[1])
            self.rdata = str(self.dnspython_rr[2])
        else:
            self._dnspython_from_rdata(domain)
            # relativize rdata according to domain via dnspython
            if self.dnspython_rr[2]:
                self.rdata = str(self.dnspython_rr[2])
    
    def _get_dnspython_ttl(self):
        if (self.ttl is not None):
            ttl = dns.ttl.from_text(self.ttl)
        elif (self.zone_ttl is not None):
            ttl = dns.ttl.from_text(self.zone_ttl)
        else:
            if self.id_:
                raise ZoneTTLNotSetError(self.id_)
            else:
                raise ValueError("RR zone_ttl can not be None")
        return ttl

    def _dnspython_from_rdata(self, domain=None):
        """
        Use the dnspython from_text() methods and its tokenizer to initialise
        dnspython rdata.
        """
        if (domain):
            origin = domain
        else:
            origin = dns.name.empty
        label = dns.name.from_text(self.label, origin)
        label = label.choose_relativity(origin)
        rdtype = dns.rdatatype.from_text(self.type_)
        rdclass = dns.rdataclass.from_text(self.class_)
        ttl = self._get_dnspython_ttl()
        # Bob Halley dnspython author recommended the following as it is an
        # API call rather than a dig into the guts of dnspython.
        if self.rdata:
            rdata = dns.rdata.from_text(rdclass, rdtype, self.rdata, origin)
        else:
            rdata = None
        self.dnspython_rr = [label, ttl, rdata]

    @reconstructor
    def rr_reconstructor(self):
        """
        Reconstruct dnspython rdata and rdata_dict from rdata,
        when loading from SQLAlchemy
        """
        # Close hole in error handling - these are the only
        # times when rdata can be blank
        if (not self.rdata and self.type_ != RRTYPE_ANY and 
                self.update_op != RROP_DELETE):
            raise ValueError("RR(%s) - rdata must not be blank" % self.id_)
        # Complete initialisation from sqlalchemy
        self._dnspython_from_rdata()

    def __eq__(self, other):
        """
        Compare rdata records for equality
        """
        return self.dnspython_rr == other.dnspython_rr

    def __ne__(self, other):
        """
        Compare rdata records for inequality
        """
        return self.dnspython_rr != other.dnspython_rr

    def __lt__(self, other):
        """
        Compare rdata records for inequality
        """
        return self.dnspython_rr < other.dnspython_rr

    def __le__(self, other):
        """
        Compare rdata records for inequality
        """
        return self.dnspython_rr <= other.dnspython_rr

    def __gt__(self, other):
        """
        Compare rdata records for inequality
        """
        return self.dnspython_rr > other.dnspython_rr

    def __ge__(self, other):
        """
        Compare rdata records for inequality
        """
        return self.dnspython_rr >= other.dnspython_rr

    def _rr_str(self):
        """
        Common code between __repr__ and __str__
        """
        if self.dnspython_rr[2]:
            rdata = self.dnspython_rr[2].__str__()
        elif self.rdata:
            rdata = self.rdata
        else:
            rdata = None
        stuff = [self.label, self.class_, self.type_]
        if rdata:
            stuff.append(rdata)
        string =  ' '.join(stuff)
        return string

    def __str__(self):
        """
        String representation of rdata
        """
        return self._rr_str()

    def __repr__(self):
        """
        Mnemonic representation of rdata
        """
        string = self._rr_str()
        return '<'+ self.__class__.__name__ + " '" + string + "'>"

    def to_engine_brief(self, time_format=None):
        """
        Output for zone engine.
        """
        reference = self.reference.reference \
                if hasattr(self, 'reference') and self.reference else None
        return{'rr_id': self.id_, 'zi_id': self.zi_id,
                'label': self.label,
                'ttl': self.ttl,
                'class': self.class_, 'type': self.type_, 'rdata': self.rdata,
                'comment_group_id': self.comment_group_id, 
                'comment_rr_id': self.comment_rr_id,
                'lock_ptr': self.lock_ptr,
                'disable': self.disable,
                'track_reverse': self.track_reverse,
                'reference': reference}

    to_engine = to_engine_brief

    def _update_dnspython_ttl(self):
            if self.ttl:
                self.dnspython_rr[1] = dns.ttl.from_text(self.ttl)
            else:
                self.dnspython_rr[1] = dns.ttl.from_text(self.zone_ttl)

    def update_zone_ttl(self, zone_ttl, reset_rr_ttl=False):
        """
        Update default ttl, and if ttl = self.ttl
        set in to None
        """ 
        if type(zone_ttl) == str:
            z_ttl = dns.ttl.from_text(zone_ttl)
        else:
            z_ttl = zone_ttl
        if (reset_rr_ttl and self.ttl):
            rr_ttl = dns.ttl.from_text(self.ttl) 
            if (rr_ttl == z_ttl):
                self.ttl = None
        self.zone_ttl = str(zone_ttl)
        self._update_dnspython_ttl()

    def update_ttl(self, ttl):
        """
        Update ttl, converting from integer if required
        """
        self.ttl = str(ttl)
        self._update_dnspython_ttl

    def get_effective_ttl(self):
        """
        returns effective ttl as a string
        """
        if self.ttl:
            return self.ttl
        else:
            return self.zone_ttl

# RR_SOA is most complex RR class to to need to manipulate rdata,
# ONLY RR this is done for - makes SQLAlchemy database persistance easier.
@rr_register
class RR_SOA(ResourceRecord):
    """
    SOA record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_SOA

    def update_serial(self, serial):
        self.dnspython_rr[2].serial = serial
        self.rdata = str(self.dnspython_rr[2])

    def get_serial(self):
        serial = self.dnspython_rr[2].serial
        return serial

@rr_register
class RR_CNAME(ResourceRecord):
    """
    CNAME record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_CNAME

@rr_register
class RR_NS(ResourceRecord):
    """
    NS record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_NS

@rr_register
class RR_A(ResourceRecord):
    """
    A record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_A

@rr_register
class RR_AAAA(ResourceRecord):
    """
    A record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_AAAA

@rr_register
class RR_PTR(ResourceRecord):
    """
    NS record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_PTR

@rr_register
class RR_TXT(ResourceRecord):
    """
    TXT record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_TXT

@rr_register
class RR_MX(ResourceRecord):
    """
    MX record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_MX

@rr_register
class RR_SPF(ResourceRecord):
    """
    SPF record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_SPF

@rr_register
class RR_RP(ResourceRecord):
    """
    RP record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_RP

@rr_register
class RR_SSHFP(ResourceRecord):
    """
    SSHFP record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_SSHFP

@rr_register
class RR_SRV(ResourceRecord):
    """
    SRV record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_SRV

@rr_register
class RR_NSAP(ResourceRecord):
    """
    SRV record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_NSAP

@rr_register
class RR_NAPTR(ResourceRecord):
    """
    SRV record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_NAPTR

@rr_register
class RR_LOC(ResourceRecord):
    """
    LOC record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_LOC

@rr_register
class RR_KX(ResourceRecord):
    """
    KX record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_KX

@rr_register
class RR_IPSECKEY(ResourceRecord):
    """
    IPSECKEY record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_IPSECKEY

@rr_register
class RR_HINFO(ResourceRecord):
    """
    HINFO record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_HINFO

@rr_register
class RR_CERT(ResourceRecord):
    """
    CERT record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_CERT

@rr_register
class RR_DS(ResourceRecord):
    """
    DS record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_DS

@rr_register
class RR_ANY(ResourceRecord):
    """
    NULL record type for use in 
    RR_DELETE operations
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_ANY
    
@rr_register
class RR_TLSA(ResourceRecord):
    """
    TLSA DANE record type
    """
    _rr_class = RRCLASS_IN
    _rr_type = RRTYPE_TLSA

# Factory functions
def dnspython_to_rr(dnspython_rr):
    """
    Factory Function to set up an RR from dnspython data
    """
    type_ = dns.rdatatype.to_text(dnspython_rr[2].rdtype)
    class_ = rrtype_map[type_]
    return class_(dnspython_rr=dnspython_rr)


def _lower_case_names(domain, rr_data):
    """
    lower case labels, and hostnames in PTR, NS, SOA, MX and SRV records
    to prevent DNSSEC duplicates.
    """
    # Lower case label
    rr_data['label'] = rr_data['label'].lower()
    # Deal with SOA NS MX and PTR records lower casing a digit gives the digit!
    if rr_data['type'] in (RRTYPE_MX, RRTYPE_NS, RRTYPE_SOA, RRTYPE_SRV):
        rr_data['rdata'] = rr_data['rdata'].lower()

def _check_name(domain, rr, rr_data):
    """
    Check host names in RRs that bind checks to conform hostname specifications

    Onwer labels on A, AAAA, and MX records
    Domain names in RDATA of SOA, NS, MX, SRV, and PTR records in IN-ADDR.ARPA,
    IP6.ARPA, or IP6.INT (Bind Option check-names)
    """
    if rr.type_ in (RRTYPE_MX, RRTYPE_A, RRTYPE_AAAA):
        if not is_inet_hostname(rr.label):
            raise BadNameOwnerError(domain, rr_data)
    if rr.type_ == RRTYPE_NS:
        if not is_inet_hostname(rr.rdata):
            raise BadNameRdataError(domain, rr_data, rr.rdata)
    if (rr.type_ == RRTYPE_PTR
                and (domain.upper().endswith('IN-ADDR.ARPA.')
                        or domain.upper().endswith('IP6.ARPA.')
                            or domain.upper().endswith('IP6.INT.'))):
        if not is_inet_hostname(rr.rdata, wildcard=False):
            raise BadNameRdataError(domain, rr_data, rr.rdata)
    if (rr.type_ == RRTYPE_MX):
        rdata = rr.rdata.split()
        if len(rdata) != 2:
            raise RdataParseError(domain, rr_data, 'MX record has 2 fields')
        if not  is_inet_hostname(rdata[1]):
            raise BadNameRdataError(domain, rr_data, rdata[1])
    if (rr.type_ == RRTYPE_SRV):
        rdata = rr.rdata.split()
        if len(rdata) != 4:
            raise RdataParseError(domain, rr_data, 'SRV record has 4 fields')
        if not  is_inet_hostname(rdata[3]):
            raise BadNameRdataError(domain, rr_data, rdata[3])
    if (rr.type_ == RRTYPE_SOA):
        rdata = rr.rdata.split()
        if len(rdata) != 7:
            raise RdataParseError(domain, rr_data, 'SOA record has 7 fields')
        if not  is_inet_hostname(rdata[0]):
            raise BadNameRdataError(domain, rr_data, rdata[0])
        if not  is_inet_hostname(rdata[1]):
            raise BadNameRdataError(domain, rr_data, rdata[1])

def data_to_rr(domain, rr_data):
    """
    Factory Function that returns resource record based on
    incoming data

    This is big because of the need for trapping errors in dnspython, 
    and producing useful error feedback
    """
    class_ = rr_data.get('class')
    if class_:
        class_ = rr_data['class'] = rr_data['class'].upper()
        if (class_ != RRCLASS_IN):
            raise UnhandledClassError(domain, rr_data)
    type_ = rr_data.get('type')
    if not type_:
        raise RRNoTypeGiven(domain, rr_data)
    type_ = rr_data['type'] = rr_data['type'].upper()
    if type_ not in rrtype_map.keys():
        raise UnhandledTypeError(domain, rr_data)

    # ANY type only allowed with RROP_DELETE
    if rr_data.get('update_op') != RROP_DELETE and type_ == RRTYPE_ANY:
        raise UnhandledTypeError(domain, rr_data)

    # update_op must be a valid value
    update_op = rr_data.get('update_op')
    if update_op not in rr_op_values:
        raise InvalidUpdateOperation(domain, rr_data)

    class_ = rrtype_map[type_]

    # Check that label is going to be useful!
    # Relativize label
    _lower_case_names(domain, rr_data)
    label = relativize_domain_name(rr_data['label'], domain)
    # label should not now be an FQDN!
    if label.endswith('.'):
        raise LabelNotInDomain(domain, rr_data)

    # Process recieved data
    try:
        kwargs = rr_data.copy()
        kwargs.pop('rdata_pyparsing', None)
        kwargs.pop('rr_groups_index', None)
        kwargs.pop('rrs_index', None)
        kwargs.pop('force_reverse', None)
        kwargs.pop('reference', None)
        rr = class_(domain=domain, **kwargs)
    except Exception as exc:
        err_string = str(exc)
        raise RdataParseError(domain, rr_data, msg=err_string)

    # Do the Bind9 bad names check
    _check_name(domain, rr, rr_data)
    return  rr

def relativize_domain_name(domain_name, zone_name):
    """
    Relativizes domain name wrt to a zone name
    """
    if domain_name.endswith(zone_name):
        d_index = domain_name.rfind(zone_name)
        if d_index == 0:
            domain_name = '@'
        elif d_index:
            domain_name = domain_name[:d_index-1]
    return domain_name

# SQL Alchemy hooks
def init_rr_table():
    table = Table('resource_records', sql_data['metadata'],
                        autoload=True, 
                        autoload_with=sql_data['db_engine'])
    sql_data['tables'][ResourceRecord] = table

def init_rr_mappers():
    table = sql_data['tables'][ResourceRecord]
    sql_data['mappers'][ResourceRecord] = mapper(ResourceRecord, table,
            polymorphic_on=table.c.get('type'), 
            polymorphic_identity=ResourceRecord._rr_type,
            properties=mapper_properties(table, ResourceRecord))
    sql_data['rr_type_list'].append(ResourceRecord._rr_type)
    # Map all the event subclasses
    for class_ in sql_data['rr_subclasses']:
        class_.sa_map_subclass()

sql_data['init_list'].append({'table': init_rr_table, 'mapper': init_rr_mappers})


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
Module that contins various DNS constant definitions
"""


from datetime import datetime
import re
from socket import socket
from socket import AF_INET
from socket import AF_INET6
from socket import error as socket_error
from socket import inet_pton
from socket import inet_ntop

import dns.name
import dns.ttl

from magcode.core.database import db_time
from dms.exceptions import HostnameZiParseError as _HostnameZiParseError
from dms.exceptions import TtlZiParseError as _TtlZiParseError
from dms.exceptions import SOASerialArithmeticError \
                                    as _SOASerialArithmeticError
from dms.exceptions import SOASerialPublishedError \
                                    as _SOASerialPublishedError
from dms.exceptions import SOASerialOcclusionError \
                                    as _SOASerialOcclusionError


# Resource Record Classes
RRCLASS_IN = 'IN'
RRCLASS_HS = 'HS'
RRCLASS_CH = 'CH'

# Resource Record types
RRTYPE_NULL = 'NULL'
RRTYPE_A = 'A'
RRTYPE_AAAA = 'AAAA'
RRTYPE_CERT = 'CERT'
RRTYPE_CNAME = 'CNAME'
RRTYPE_DNAME = 'DNAME'
RRTYPE_DNSKEY = 'DNSKEY'
RRTYPE_DS = 'DS'
RRTYPE_HINFO = 'HINFO'
RRTYPE_IPSECKEY = 'IPSECKEY'
RRTYPE_KEY = 'KEY'
RRTYPE_KX = 'KX'
RRTYPE_LOC = 'LOC'
RRTYPE_MX = 'MX'
RRTYPE_NAPTR = 'NAPTR'
RRTYPE_NSAP = 'NSAP'
RRTYPE_NSEC = 'NSEC'
RRTYPE_NSEC3 = 'NSEC3'
RRTYPE_NSEC3PARAM = 'NSEC3PARAM'
RRTYPE_NS = 'NS'
RRTYPE_NXT = 'NXT'
RRTYPE_PTR = 'PTR'
RRTYPE_RP = 'RP'
RRTYPE_RRSIG = 'RRSIG'
RRTYPE_SIG = 'SIG'
RRTYPE_SOA = 'SOA'
RRTYPE_SPF = 'SPF'
RRTYPE_SRV = 'SRV'
RRTYPE_SSHFP = 'SSHFP'
RRTYPE_TXT = 'TXT'
RRTYPE_ANY = 'ANY'
RRTYPE_TLSA = 'TLSA'

# Various RDATA representations
RDATA_GENERIC_NULL = '\# 0'

# Update operations
RROP_ADD = 'ADD'
RROP_UPDATE_RRTYPE = 'UPDATE_RRTYPE'
RROP_DELETE = 'DELETE'
RROP_PTR_UPDATE = 'PTR_UPDATE'
RROP_PTR_UPDATE_FORCE = 'PTR_UPDATE_FORCE'
# This does not include the PTR_UPDATE update operations for security reasons
# They can be tested anyhow by using A and AAAA records in a forward zone
rr_op_values = (None, RROP_ADD, RROP_UPDATE_RRTYPE, RROP_DELETE)

# Domain name element constants
DOMN_MAXLEN = 255
DOMN_LBLLEN = 63
DOMN_CHRREGEXP = r'^[-.a-zA-Z0-9]*$'
DOMN_LBLREGEXP = r'^$|^[a-zA-Z0-9][-a-zA-Z0-9]*$'
DOMN_IPV6_REGEXP = r'^[a-fA-F0-9:]+$'
DOMN_IPV4_REGEXP = r'^[0-9.]+$'
DOMN_LBLSEP = '.'

label_re = re.compile(DOMN_LBLREGEXP)
ipv6_re = re.compile(DOMN_IPV6_REGEXP)
ipv4_re = re.compile(DOMN_IPV4_REGEXP)

def is_inet_domain(text):
    if len(text) > DOMN_MAXLEN:
        return False
    labels = text.split(DOMN_LBLSEP)
    if labels[-1] != '':
        #Must be root domain
        return False
    for lbl in labels[:-1]:
        if not lbl:
            # label must be at least one character long
            return False
        if len(lbl) > DOMN_LBLLEN:
            return False
        if not label_re.search(lbl):
            return False
        if lbl[0] == '-' or lbl[-1] == '-':
            return False
    return True

def is_inet_hostname(text, absolute=False, wildcard=True):
    # Deal with special case '@'
    if text == '@':
        return True
    if len(text) > DOMN_MAXLEN:
        return False
    labels = text.split(DOMN_LBLSEP)
    if absolute and labels[-1] != '':
        # root domain must be appended
        return False
    lbl_list = labels[:-1] if labels[-1] == '' else labels
    for lbl in lbl_list:
        if not lbl:
            # label must be at least one character long
            return False
        # Wild card domain
        if (wildcard and lbl == '*'):
            continue
        if len(lbl) > DOMN_LBLLEN:
            return False
        if not label_re.search(lbl):
            return False
        if lbl[0] == '-' or lbl[-1] == '-':
            return False
    return True

def validate_zi_hostname(name, zi_field, text):
    """
    Validate that a hostname is 100%
    """
    try:
        thing = dns.name.from_text(text)
    except Exception as exc:
        raise _HostnameZiParseError(name, zi_field, text, str(exc))
    if not is_inet_hostname(text):
        raise _HostnameZiParseError(name, zi_field, text, None)

def validate_zi_ttl(name, zi_field, text):
    """
    Validate a ttl value
    """
    if len(text) > 20:
        raise _TtlZiParseError(name, zi_field, text, "longer than 20 chars.")
    try:
        thing = dns.ttl.from_text(text)
    except Exception as exc:
        raise _TtlZiParseError(name, zi_field, text, str(exc))

def new_zone_soa_serial(db_session):
    """
    Generate a new SOA serial number based on date, for initialising zones
    """
    date = db_time(db_session).timetuple()
    soa_serial = (00 + 100 * date.tm_mday + 10000 * date.tm_mon
                        + 1000000 * date.tm_year)
    return soa_serial

def is_network_address(address):
    """
    Vaildate a network address
    """
    # Check routines also over in dms.zone_tool if this needs to be
    # changed
    try:
        inet_pton(AF_INET6, address)
        return True
    except socket_error:
        pass
    try:
        inet_pton(AF_INET, address)
        return True
    except socket_error:
        pass
    return False

def split_cidr_network_tuple(cidr_network, filter_mask_size=True):
    """
    Split a CIDR network/mask to a values suitable for a DNS reverse zone
    """
    # Check routines also over in dms.zone_tool if this needs to be
    # changed
    try:
        network, mask = cidr_network.split('/')
        mask = int(mask)
    except ValueError:
        return ()
    if network.find(':') >= 0 and network.find('.') < 0:
        try:
            i_net = int.from_bytes(inet_pton(AF_INET6, network), 
                                byteorder='big',
                                signed=False)
            if filter_mask_size and mask not in range(4, 65, 4):
                return ()
            i_mask = ~(2**(128-mask)-1)
            i_net = i_net & i_mask
            network = inet_ntop(AF_INET6, 
                        i_net.to_bytes(16, byteorder='big', signed=False))
            return (network, mask)
        except socket_error:
            pass
    elif network.isdigit() or network.find('.') >= 0 and network.find(':') < 0:
        try:
            network = network[:-1] if network.endswith('.') else network
            num_bytes = len(network.split('.'))
            if num_bytes < 4:
                network += (4 - num_bytes) * '.0'
            if filter_mask_size and mask not in range(8, 25, 8):
                return ()
            i_net = int.from_bytes(inet_pton(AF_INET, network),
                                byteorder='big',
                                signed=False)
            i_mask = ~(2**(32-mask)-1)
            i_net = i_net & i_mask
            network = inet_ntop(AF_INET,
                        i_net.to_bytes(4, byteorder='big', signed=False))
            return (network, mask)
        except socket_error:
            pass
    return ()

def wellformed_cidr_network(cidr_network, filter_mask_size=True):
    """
    Produced a well-formed network/mask pair
    """
    result = split_cidr_network_tuple(cidr_network, filter_mask_size)
    return '%s/%s' % result if result else ''

def zone_name_from_network(cidr_network):
    """
    Convert a CIDR network address to a reverse zone name

    Partly inspired by dnspython dns.reverse.from_address()
    """
    # Check routines also over in dms.zone_tool if this needs to be
    # changed
    result = split_cidr_network_tuple(cidr_network)
    if not result:
        return ()
    network, mask = result
    try:
        segments = []
        for byte in inet_pton(AF_INET6, network):
            segments += [ '%x' % (byte >> 4), '%x' % (byte & 0x0f) ]
        base_domain = 'ip6.arpa.'
        mask_divisor = 4
    except socket_error:
        segments = [ '%d' % byte for byte in inet_pton(AF_INET, network)]
        base_domain = 'in-addr.arpa.'
        mask_divisor = 8
    segments.reverse()
    n = mask // mask_divisor
    return ('.'.join(segments[-n:]).lower() + '.' + base_domain, 
                '%s/%s' % (network, mask))

def network_from_zone_name(name):
    """
    Form a network from a zone name.

    TODO: Finish and test this.  IPv6 mask code not complete!
    Partly inspired by dnspython dns.reverse.from_address()
    """
    if name.endswith('.in-addr.arpa.'):
        rev_str = name[:name.rfind('.in-addr.arpa.')]
        addr_list = rev_str.split('.')
        addr_list.reverse()
        mask = len(addr_list) * 8
        if mask not in (0, 8, 16, 24, 32):
            return None
        if len(addr_list):
            addr_str = '.'.join(addr_list)
            # Check address and make pretty
            try:
                 addr_str = inet_ntop(AF_INET, inet_pton(AF_INET, addr_str))
            except socket_error:
                return None
        else:
            addr_str = '0'
        return "%s/%s" % (addr_str, mask)
    elif name.endswith('.ip6.arpa.'):
        rev_str = name[:name.rfind('.ip6.arpa.')]
        addr_list = rev_str.split('.')
        addr_list.reverse()
        mask = len(addr_list) * 4
        if mask not in range(0, 65, 4):
            return None
        # Start here
        l = len(addr_list)
        bytes_2 = []
        i = 0 
        while i < l:
            bytes_2.append(''.join([x for x in addr_list[i:i+4]]))
            i += 4
        addr_str = ':'.join(bytes_2)
        # Check address and make pretty
        try:
            addr_str = inet_ntop(AF_INET6, inet_pton(AF_INET6, addr_str))
        except socket_error:
            return None
        return addr_str

    
    # Nothing can be done here!
    return None

def label_from_address(address):
    """
    Convert a network address to a reverse FQDN zone label

    Partly inspired by dnspython dns.reverse.from_address()
    """
    # Check routines also over in dms.zone_tool if this needs to be
    # changed
    try:
        segments = []
        for byte in inet_pton(AF_INET6, address):
            segments += [ '%x' % (byte >> 4), '%x' % (byte & 0x0f) ]
        base_domain = 'ip6.arpa.'
    except socket_error:
        segments = [ '%d' % byte for byte in inet_pton(AF_INET, address)]
        base_domain = 'in-addr.arpa.'
    segments.reverse()
    return '.'.join(segments).lower() + '.' + base_domain 

def address_from_label(rev_fqdn_label):
    """
    Convert an FQDN reverse label into a network address
    
    Partly inspired by dnspython dns.reverse.from_address()
    """
    if rev_fqdn_label.endswith('.in-addr.arpa.'):
        rev_str = rev_fqdn_label[:rev_fqdn_label.rfind('.in-addr.arpa.')]
        addr_list = rev_str.split('.')
        addr_list.reverse()
        addr_str = '.'.join(addr_list)
        # Check address and make pretty
        try:
             addr_str = inet_ntop(AF_INET, inet_pton(AF_INET, addr_str))
        except socket_error:
            return None
        return addr_str
    elif rev_fqdn_label.endswith('.ip6.arpa.'):
        rev_str = rev_fqdn_label[:rev_fqdn_label.rfind('.ip6.arpa.')]
        addr_list = rev_str.split('.')
        addr_list.reverse()
        l = len(addr_list)
        bytes_2 = []
        i = 0 
        while i < l:
            bytes_2.append(''.join([x for x in addr_list[i:i+4]]))
            i += 4
        addr_str = ':'.join(bytes_2)
        # Check address and make pretty
        try:
            addr_str = inet_ntop(AF_INET6, inet_pton(AF_INET6, addr_str))
        except socket_error:
            return None
        return addr_str

    # Nothing can be done here!
    return None

def new_soa_serial_no(current, name, db_soa_serial=None, candidate=None, 
        wrap_serial_next_time=False, date_stamp=None):
    """
    Calculate a new SOA serial number given the current one.
    
    This function shoul always provide a new serial that will
    enable moving back to the date based serial possible next update.
    New Serial must also be greater than current serial to ensure that
    any changes to SOA values are propagated.

    Setting warap_serial_next_time, and then doing another update will
    bring the SOA serial number back to YYYYMMDDnn conventional operations
    format.

    RFC 2316 Sec 3.4.2.2 says that SOA will not be updated at all unless
    new serial number is a positive increment on the current, as defined
    by modulo 2^32 arithmetic in RFC 1982 Section 3.
    """
    # As per RFC 1034 and 1035, SOA serial number is unsigned int32
    # [0 .. (2**32 -1)], hence modulo 32 arithmetic for SOA serial numbers
    # in RFC 1982.
    SERIAL_BITS = 32
    if date_stamp:
        date = date_stamp.timetuple()
    else:
        date = datetime.now().timetuple()
    new_date_serial = (00 + 100 * date.tm_mday + 10000 * date.tm_mon
                    + 1000000 * date.tm_year)

    # Maximum increment and addition formulae from RFC1982 Sec 3.1
    max_increment  = 2**(SERIAL_BITS -1) - 1
    max_update = (current + max_increment) % (2**SERIAL_BITS)

    if (wrap_serial_next_time):
        candidate = max_update
    elif (not candidate):
        candidate = new_date_serial
        # Something interesting, but you need to check that time between 
        # updates > refresh while doing this....  Could be troublesome.
        # check out chosen default candidate
        #if (candidate <= max_increment 
        #    and (current - candidate) 
        #        >= settings['soa_serial_wrap_threshold']):
        #    # Deal to any 'out of convention' serial numbers that sneak
        #    # in.  
        #    # FIXME: This will work until the 36th day of the 48th month
        #    # of the year 2147 or serial no 2147483647 ie max_increment...
        #    candidate = max_update

    # Two number line cases here, 1) max_update > current, and the wrap
    # case 2) max_update < current. Wrap occurs at (2^32 - 1).
    if (max_update > current):
        if (db_soa_serial and db_soa_serial > current 
                    and db_soa_serial < max_update):
            base = db_soa_serial
        elif (db_soa_serial and db_soa_serial == max_update):
            raise _SOASerialOcclusionError(name)
        else:
            base = current

        if (candidate > base and candidate <= max_update):
            update = candidate
        else:
            update = (base + 1) % (2**SERIAL_BITS)
    elif(max_update < current):
        if (db_soa_serial and (db_soa_serial < max_update 
                                or db_soa_serial > current)):
            base = db_soa_serial
        elif (db_soa_serial and db_soa_serial == max_update):
            raise _SOASerialOcclusionError(name)
        else:
            base = current

        if (candidate <= max_update or candidate > base):
            update = candidate
        else:
            update = (base + 1) % (2**SERIAL_BITS)
    else:
        # This is mathematically impossible for SERIAL_BITS = 32 
        # If it happens, this program has shifted to an alternate
        # reality of memory corruption
        raise _SOASerialArithmeticError(name)
    
    # SOA serial number can never be zero - RFC 2136 Sec 4.2
    if (update == 0):
        # If 0 is value of max_update, want to decrement so 
        # that update happens
        if (max_update == 0):
            update = (update - 1) % (2**SERIAL_BITS)
        else:
            update = (update + 1) % (2**SERIAL_BITS)

    if db_soa_serial and db_soa_serial == update:
        raise _SOASerialPublishedError(name)

    return update



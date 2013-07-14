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
Base Update Engine class.  Contains common code.
"""

import socket
from datetime import datetime

import dns.query
import dns.resolver
import dns.zone
import dns.exception
import dns.rdatatype
import dns.name
import dns.message
import dns.rdataclass
import dns.flags

from dms.exceptions import SOASerialArithmeticError
from dms.exceptions import NoSuchZoneOnServerError
from magcode.core.globals_ import settings
from magcode.core.database import RCODE_FATAL
from magcode.core.database import RCODE_RESET
from magcode.core.database import RCODE_OK
from magcode.core.database import RCODE_ERROR
from dms.dns import RRTYPE_SOA
from dms.dns import RRTYPE_NSEC3PARAM
from dms.dns import RRTYPE_DNSKEY
# initialise settings keys
import dms.globals_


class UpdateEngine(object):
    """
    Parent Generic Update Engine class

    Contains common code etc.
    """
    def __init__(self, server, port=None):
        """
        Initialise settings for conversation.
        """
        # Make sure we can connect to server port TCP 53
        # NOTE: can be IPv4 or V6 - depends on resolv.conf option inet6 setting
        dest_port = settings['dns_port']
        if (port):            
            dest_port = port
        (family, type_, proto, canonname, sockaddr) \
            = socket.getaddrinfo(server, dest_port, proto=socket.SOL_TCP)[0]
        sock = socket.socket(family=family, type=type_, proto=proto)
        sock.connect(sockaddr)
        sock.close()
        # If we get here without raising an exception, we can talk to the 
        # server (mostly)
        self.server_name = server
        self.port_name = dest_port
        self.server = sockaddr[0]
        self.port = sockaddr[1]

    def read_zone(self, zone_name, filter_dnssec=True):
        """
        Use dnspython to read in a Zone from the DNS server
        
        Returns a Zone Instance based on the read in data.
        NOTE: This is not from the DB!
        """
        xfr_generator = dns.query.xfr(self.server, zone_name, port=self.port)
        try:
            zone = dns.zone.from_xfr(xfr_generator)
        except dns.exception.FormError as exc:
            zone = None
        finally:
            del xfr_generator
        # Unlink exception chaining
        if (not zone):
            raise NoSuchZoneOnServerError(zone_name, self.server_name, 
                                            self.port)

        # Filter out dnssec if requested.
        dnssec_types = settings['dnssec_filter'].split()
        dnssec_rdtypes = [dns.rdatatype.from_text(x) for x in dnssec_types]
        nsec3param_rdtype = dns.rdatatype.from_text(RRTYPE_NSEC3PARAM)
        dnskey_rdtype = dns.rdatatype.from_text(RRTYPE_DNSKEY)
        # Need to find items to delete before deleting them, or
        # else zone data structure is corrupted.
        rr_delete_list = []
        dnskey_flag = False
        nsec3param_flag = False
        for rdata in zone.iterate_rdatas():
            if not dnskey_flag:
                dnskey_flag = (rdata[2].rdtype == dnskey_rdtype)
            if not nsec3param_flag:
                nsec3param_flag = (rdata[2].rdtype == nsec3param_rdtype)
            if rdata[2].rdtype in dnssec_rdtypes:
                rr_delete_list.append((rdata[0], rdata[2].rdtype, 
                        rdata[2].covers(),))
        # Finally delete all unwanted records
        if filter_dnssec:
            for (name, rdtype, covers) in rr_delete_list:
                zone.delete_rdataset(name, rdtype, covers)
        # Finally, an unclutered zone without DNSSEC
        return (zone, dnskey_flag, nsec3param_flag)

    def read_soa(self, zone_name):
        """
        Use dnspython to read the SOA record of a Zone from the DNS server.

        Returns the SOA serial number etc.  This is intended as a test
        function to see if the master server has configured a zone.
        """
        zone = dns.name.from_text(zone_name)
        rdtype = dns.rdatatype.from_text(RRTYPE_SOA)
        rdclass = dns.rdataclass.IN
        query = dns.message.make_query(zone, rdtype, rdclass)
        exc = None
        try:
            # Use TCP as dnspython can't track multi-threaded udp query/results
            answer = dns.query.tcp(query, self.server, port=self.port,
                    timeout=float(settings['dns_query_timeout']))
        except dns.exception.Timeout:
            msg =  ("Zone '%s', - timeout waiting for response, retrying"
                    % zone_name)
            return (RCODE_ERROR, msg, None)
        except (dns.query.UnexpectedSource, dns.query.BadResponse,
                dns.query.FormError) as exc:
            # For UDP, FormError and BadResponse here are retrys as they
            # mostly could be transitory
            msg = ("Zone '%s', - reply from unexpected source, retrying"
                    % zone_name)
            return (RCODE_ERROR, msg, None)
        # Here to show what should be done if any of above errors prove
        # to be more than a retry...
        #except (dns.query.BadResponse,
        #        dns.exception.FormError) as exc:
        #    msg = ("Zone '%s', - server %s not operating correctly." 
        #                % (zone_name, server.server_name))
        #    return (RCODE_FATAL, msg, None)
        except socket.error as exc:
            if errno in (errno.EACCESS, errno.EPERM, errno.ECONNREFUSED, 
                    errno.ENETUNREACHABLE, errno.ETIMEDOUT):
                msg = ("Zone '%s' - can't reach server %s:%s yet - %s"
                        % (zone_name, self.server, self.port, exc.strerror))
                return (RCODE_ERROR, msg, None)
            msg = ("Zone '%s' - server %s:%s, fatal error %s."
                   % (zone_name, self.server, self.port, exc.strerror))
            return (RCODE_FATAL, msg, None)
        finally:
            # Clean up memory
            del query
        try:
            if (answer.flags & dns.flags.AA != dns.flags.AA):
                msg = "Zone '%s' not yet operational on server." % zone_name
                return (RCODE_RESET, msg, None)
            if (len(answer.answer) != 1):
                msg = "Zone '%s' not yet operational on server." % zone_name
                return (RCODE_RESET, msg, None)
            if not len(answer.answer[0].items):
                msg = "Zone '%s' not yet operational on server." % zone_name
                return (RCODE_RESET, msg, None)
            if answer.answer[0].items[0].rdtype != rdtype:
                msg = "Zone '%s' not yet operational on server." % zone_name
                return (RCODE_RESET, msg, None)
            
            # We succeeded in getting an SOA and serial number
            msg = "Zone '%s' operational on server." % zone_name 
            return (RCODE_OK, msg, answer.answer[0].items[0].serial)
        finally:
            # clean up memory
            del answer

    def get_serial_no(self, zone):
        """
        Obtain the serial number from the SOA of a zone
        """
        rdataset = zone.find_rdataset(zone.origin, 
                                        dns.rdatatype.from_text(RRTYPE_SOA))
        return rdataset.items[0].serial
       
    def update_zone(self, zone_name, zi, db_soa_serial=None, 
            candidate_soa_serial=None,
            force_soa_serial_update=False, wrap_serial_next_time=False,
            date_stamp=None, nsec3_seed=False, clear_dnskey=False,
            clear_nsec3=False):
        """
        Stub method for updating a zone.

        returns tuple of RCODE_, message, serial number
        """
        message = 'Stub update_zone()'
        return (RCODE_FATAL, message, None, None)

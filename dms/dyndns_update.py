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
Module to handle talking Dynamic DNS update to bind master server.
"""


import sys
import os
import errno
import re
import socket
import shlex
import random
from subprocess import Popen
from subprocess import PIPE
from subprocess import CalledProcessError
from os.path import isfile

import dns.query
import dns.zone
import dns.tsigkeyring
import dns.update
import dns.rcode

from magcode.core.globals_ import *
from dms.dns import *
from magcode.core.database import RCODE_OK
from magcode.core.database import RCODE_ERROR
from magcode.core.database import RCODE_RESET
from magcode.core.database import RCODE_FATAL
from magcode.core.database import RCODE_NOCHANGE
from dms.globals_ import *
from dms.parser import get_keys
from dms.update_engine import UpdateEngine
from dms.exceptions import DynDNSCantReadKeyError
from dms.exceptions import DynDNSCantReadKeyError
from dms.exceptions import NoSuchZoneOnServerError
from dms.exceptions import SOASerialError


# For settings initialisation see dms.globals_

class DynDNSUpdate(UpdateEngine):
    """
    Implements the operations needed to update bind via Dyanmic DNS
    """
    def __init__(self, server, key_file, key_name, port=None):
        """
        Initialise settings for conversation.
        """
        # Stop obvious problems
        # Make sure key_file is accessible
        if not isfile(key_file):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), key_file)
        test_open = open(key_file)
        test_open.close()
        self.key_file = key_file
        tsig_keys = get_keys(key_file)
        if (not tsig_keys
            and not key_name in list(tsig_keys.keys())):
            raise DynDNSCantReadKeyError(key_file, key_name)
        self.key_name = key_name
        self.tsig_key = tsig_keys[self.key_name]
        self.key_file = key_file

        # Check we can get to DNS server (AXFR part of base UpdateEngine)
        super().__init__(server, port)

        #Transform settings for DYNDNS RCODES to something we can understand
        self.success_rcodes = [dns.rcode.from_text(x) 
                for x in settings['dyndns_success_rcodes'].strip().split()]
        self.retry_rcodes = [dns.rcode.from_text(x) 
                for x in settings['dyndns_retry_rcodes'].strip().split()]
        self.reset_rcodes = [dns.rcode.from_text(x) 
                for x in settings['dyndns_reset_rcodes'].strip().split()]
        self.fatal_rcodes = [dns.rcode.from_text(x) 
                for x in settings['dyndns_fatal_rcodes'].strip().split()]
        return

    def update_zone(self, zone_name, zi, db_soa_serial=None, 
            candidate_soa_serial=None,
            force_soa_serial_update=False, wrap_serial_next_time=False,
            date_stamp=None, nsec3_seed=False, clear_dnskey=False,
            clear_nsec3=False):
        """
        Use dnspython to update a Zone in the DNS server

        Use wrap_serial_next_time to 'fix' SOA serial numbers grossly not 
        in the operations format YYYYMMDDnn. date is a datetime object in 
        localtime.
        """
        # Read in via AXFR zone for comparison purposes
        try:
            zone, dnskey_flag, nsec3param_flag = self.read_zone(zone_name)
            update_info = {'dnskey_flag': dnskey_flag, 
                            'nsec3param_flag': nsec3param_flag}
        except NoSuchZoneOnServerError as exc:
            msg = str(exc)
            #return (RCODE_FATAL, msg, None, None)
            # Send RESET as server not configured yet.
            return (RCODE_RESET, msg, None, None)

        except (dns.query.UnexpectedSource, dns.query.BadResponse) as exc:
            msg = ("Zone '%s', - server %s not operating correctly." 
                        % (zone_name, server.server_name))
            return (RCODE_FATAL, msg, None, None)
        
        except (IOError, OSError) as exc:
            if exc.errno in (errno.EACCES, errno.EPERM, errno.ECONNREFUSED, 
                    errno.ENETUNREACH, errno.ETIMEDOUT):
                msg = ("Zone '%s' - server %s:%s not available - %s"
                        % (zone_name, self.server, self.port, exc.strerror))
                return (RCODE_ERROR, msg, None, None)
            msg = ("Zone '%s' - server %s:%s, fatal error %s."
                   % (zone_name, self.server, self.port, exc.strerror))
            return (RCODE_FATAL, msg, None, None)


        # Get current SOA record for zone to include as prerequiste in update
        # Makes update transaction idempotent
        current_soa_rr = zone.find_rdataset(zone.origin, RRTYPE_SOA).items[0]
        
        update_soa_serial_flag = False
        curr_serial_no = self.get_serial_no(zone)
        # In case of a DR failover, our DB can have a more recent serial number
        # than in name server
        try:
            new_serial_no = new_soa_serial_no(curr_serial_no, zone_name, 
                    db_soa_serial=db_soa_serial,
                    candidate=candidate_soa_serial,
                    wrap_serial_next_time=wrap_serial_next_time,
                    date_stamp=date_stamp)
        except SOASerialError as exc:
            msg = str(exc)
            if (not sys.stdin.isatty()):
                log_critical(msg)
            return (RCODE_FATAL, msg, None, None)
        if wrap_serial_next_time or force_soa_serial_update:
            # Apply serial number to SOA record.
            zi.update_soa_serial(new_serial_no)
        else:
            # An increment should only be performed after difference
            update_soa_serial_flag = True

        # Compare server_zone with zi.rrs
        # Find additions and deletions
        del_rrs = [rr for rr in zone.iterate_rdatas()
                    if rr not in zi.iterate_dnspython_rrs()]
        add_rrs = [rr for rr in zi.iterate_dnspython_rrs()
                    if rr not in zone.iterate_rdatas()]
        # Check if DNSSEC settings need to be changed 
        do_clear_nsec3 = clear_nsec3 and nsec3param_flag
        do_clear_dnskey = clear_dnskey and dnskey_flag
        do_nsec3_seed = nsec3_seed and not nsec3param_flag

        if (not del_rrs and not add_rrs and not do_clear_nsec3 
                and not do_clear_dnskey and not do_nsec3_seed):
            msg = ("Domain '%s' not updated as no change detected" 
                        % (zone_name))
            return (RCODE_NOCHANGE, msg, curr_serial_no, update_info)
      
        # Incremental update of SOA serial number
        soa_rdtype = dns.rdatatype.from_text(RRTYPE_SOA)
        if update_soa_serial_flag:
            # Apply serial number to SOA record.
            zi.update_soa_serial(new_serial_no)
            # recalculate add_rrs - got to be done or else updates will be
            # missed
            add_rrs = [rr for rr in zi.iterate_dnspython_rrs()
                        if rr not in zone.iterate_rdatas()]
       
        # Groom updates for DynDNS update perculiarities

        # SOA can never be deleted RFC 2136 Section 3.4.2.3 and 3.4.2.4
        # so skip this.
        del_rrs = [rr for rr in del_rrs 
                if (rr[2].rdtype != soa_rdtype)]

        # Can never delete the last NS on the root of a zone,
        # so pre add all '@' NS records (RFC 2136 Sec
        # 3.4.2.4)
        tl_label = dns.name.from_text('@', origin=dns.name.empty)
        ns_rdtype = dns.rdatatype.from_text(RRTYPE_NS)
        pre_add_rrs = [rr for rr in add_rrs 
                        if (rr[0] == tl_label and rr[2].rdtype == ns_rdtype)]
        tl_ns_rdata = [rr[2] for rr in pre_add_rrs]
        add_rrs = [rr for rr in add_rrs if rr not in pre_add_rrs]
        # Remove '@' NS delete from del_rrs if record in pre_add_rrs 
        # ie, we are just doing a TTL update!
        del_rrs = [rr for rr in del_rrs 
                    if (not(rr[0] == tl_label and rr[2] in tl_ns_rdata))]

        # CNAMEs can only be added to vacant nodes, or totally replace 
        # RRSET on a node RFC 2136 Section 3.4.2.2
        # Choose to enforce this at zi API level.

        # DNSSEC processing - prepare NSEC3PARM rdata 
        if do_nsec3_seed:
            rn = random.getrandbits(int(settings['nsec3_salt_bit_length']))
            hash_alg = settings['nsec3_hash_algorithm']
            flags = settings['nsec3_flags']
            iterations = settings['nsec3_iterations']
            nsec3param_rdata = ("%s %s %s %016x" 
                                % (hash_alg, flags, iterations, rn))
            # Test rn as random can produce garbage sometimes...
            rdata_list = nsec3param_rdata.split()
            try:
                # This is the piece of code where dnspython blows up...
                stuff = bytes.fromhex(rdata_list[-1])
            except Exception:
                msg = ("Failed to seed NSEC3 salt - SM reset required")
                return (RCODE_RESET, msg, None, update_info)

        # Prepare dnspython tsigkeyring
        keyring = dns.tsigkeyring.from_text({
            self.key_name : self.tsig_key['secret'] })
        if (self.tsig_key['algorithm'] == 'hmac-md5'):
            key_algorithm = dns.tsig.HMAC_MD5
        else:
            key_algorithm = dns.name.from_text(self.tsig_key['algorithm'])
        
        # Create update 
        # We have to use absolute FQDNs on LHS  and RHS to make sure updates
        # to NS etc happen
        # While doing this also handle wee things for DNSSEC processing
        origin = dns.name.from_text(zone_name)
        update = dns.update.Update(origin, keyring=keyring,
                    keyname = self.key_name, keyalgorithm=key_algorithm)
        update.present(origin, current_soa_rr)
        for rr in pre_add_rrs:
            update.add(rr[0], rr[1], rr[2])
        for rr in del_rrs:
            update.delete(rr[0], rr[2])
        # Add DNSSEC clearance stuff to end of delete section of update
        if do_clear_nsec3:
            update.delete(origin, RRTYPE_NSEC3PARAM)
        if do_clear_dnskey:
            update.delete(origin, RRTYPE_DNSKEY)
        for rr in add_rrs:
            update.add(rr[0], rr[1], rr[2])
        # NSEC3PARAM seeding
        if do_nsec3_seed:
            update.add(origin, '0', RRTYPE_NSEC3PARAM, nsec3param_rdata)

        # Do dee TING!
        response = dns.query.tcp(update, self.server, port=self.port)

        # Process reply
        rcode = response.rcode()
        rcode_text = dns.rcode.to_text(response.rcode())
        success_rcodes = (dns.rcode.NOERROR)
        if (rcode in self.success_rcodes):
            msg = ("Update '%s' to domain '%s' succeeded" 
                            % (new_serial_no, zone_name))
            return (RCODE_OK, msg, new_serial_no, update_info)
        elif (rcode in self.retry_rcodes):
            msg = ("Update '%s' to domain '%s' failed: %s - will retry"
                        % (new_serial_no, zone_name, rcode_text))
            return (RCODE_ERROR, msg, None, update_info)
        elif (rcode in self.reset_rcodes):
            msg = ("Update '%s' to domain '%s' failed: %s - SM reset required"
                        % (new_serial_no, zone_name, rcode_text))
            return (RCODE_RESET, msg, None, update_info)
        elif (rcode in self.fatal_rcodes):
            msg = ("Update '%s' to domain '%s' permanently failed: %s"
                        % (new_serial_no, zone_name, rcode_text))
            return (RCODE_FATAL, msg, None, update_info)
        else:
            msg = ("Update '%s' to domain '%s' permanently failed: '%s'"
                    " - unknown response"
                        % (new_serial_no, zone_name, response.rcode()))
            return (RCODE_FATAL, msg, None, update_info)



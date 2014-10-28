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
Exceptions module for the DMS
"""


import pyparsing

from magcode.core.wsgi.jsonrpc_server import JSONRPC_INTERNAL_ERROR
from magcode.core.wsgi.jsonrpc_server import BaseJsonRpcError

class DMSError(BaseJsonRpcError):
    """
    Base DMS Error Exception

    * JSONRPC Error: JSONRPC_INTERNAL_ERROR
    """

class ZoneTTLNotSetError(DMSError):
    """
    The zone ttl needs to be set in the RR database row
    
    * JSONRPC Error: -1
    * JSONRPC data keys:
        * 'rr_id'  - Resource Record ID
    """
    def __init__(self, rr_id):
        message = "RR (%s) does not have its zone_ttl set" % rr_id
        DMSError.__init__(self, message)
        self.data['rr_id'] = rr_id
        self.jsonrpc_error = -1

class UpdateError(DMSError):
    """
    Error during update of zone
    
    * JSONRPC Error: -2
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain, *args):
        message = "Error updating domain '%s'." % domain
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -2

class SOASerialError(DMSError):
    """
    Ancestor for all SOA Serial arithmetic errors
    """

class SOASerialArithmeticError(SOASerialError):
    """
    SOA Serial Arithmetic Error.  Possibly due to memory corruption

    * JSONRPC Error: -3
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain):
        message = ("Zone '%s' - Error calculating SOA serial number - something impossible happened." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -3

class DynDNSUpdateError(UpdateError):
    """
    Error during update of zone
    
    * JSONRPC Error: -4
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain, *args):
        message = "Error updating domain '%s'." % domain
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -4
        
class DynDNSCantReadKeyError(DynDNSUpdateError):
    """
    Can't read in configured TSIG for Dynamic DNS update

    * JSONRPC Error: -5
    * JSONRPC data keys:
        * 'name'  - None
    """
    def __init__(self, file_, key_name):
        message = ("Error updating domain - can't read key '%s' from file '%s'"
            % (file_, key_name))
        DMSError.__init__(self, message)
        self.data['file'] = file_
        self.data['key_name'] = key_name
        # put this here to help avoid throwing exceptions in error processing
        # code.
        self.data['name'] = None
        self.jsonrpc_error = -5

class NoSuchZoneOnServerError(UpdateError):
    """
    No zone found in DNS server
    
    * JSONRPC Error: -6
    * JSONRPC data keys:
        * 'name'      - zone name
        * 'server'    - server hostname/address
        * 'port'      - server port

    This exception only occurs internally in dmsdmd, and dyndns_tool. It is
    not returned at all over HTTP JSON RPC.
    """
    def __init__(self, domain, server, port):
        message = ("Server %s:%s, no such zone '%s' on server."
                % (server, port, domain))
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.data['server'] = server
        self.data['port'] = port
        self.jsonrpc_error = -6

# Resource Record Parsing Errors
class NoPreviousLabelParseError(DMSError):
    """
    No Previous Label seen. - This should not be reached in code

    * JSONRPC Error:     -7
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain):
        message = "There is no previous RR seen with a valid label"
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -7

class ZoneParseError(DMSError):
    """
    Parent class for zi RR errors

    * JSONRPC Error:      JSONRPC_INTERNAL_ERROR
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, 
            msg=None, use_pyparsing=True, rewind_loc=False, 
            beginning_loc=False):
        
        # Only initialise data if it has not been set up already....
        if not hasattr(self, 'data'):
            self.data = {}
        
        self.data['name'] = domain
        self.data['rr_data'] = rr_data
        self.data['rr_groups_index'] = rr_data.get('rr_groups_index', 0)
        self.data['rrs_index'] = rr_data.get('rrs_index', 0)
        self.rdata_pyparsing = rr_data.get('rdata_pyparsing')
        if not use_pyparsing:
            self.rdata_pyparsing = None
        
        if not msg:
            msg = 'generic error'
        if self.rdata_pyparsing:
            s = self.rdata_pyparsing['s']
            loc = self.rdata_pyparsing['loc']
            if beginning_loc:
                # Put cursor at top if zone is inconsistent
                loc = 0
            elif rewind_loc:
                # Rewind loc if this is a full RR  or ZI consistency error
                while (loc > 0 and s[loc-1] != '\n'):
                    loc -= 1
            else:
            # Advance loc so that it is not whitespace....
                while (s[loc] == ' ' or s[loc] == '\t'):
                    loc += 1
            self.pp_exc = pyparsing.ParseBaseException(s, loc, msg)
            message = str(self.pp_exc)
            lineno = self.pp_exc.lineno
            col = self.pp_exc.lineno
        else:
            class_ = rr_data.get('class', 'IN')
            label = rr_data.get('label', 'NULL')
            type_ = rr_data.get('type', 'NULL')
            rdata = rr_data.get('rdata', 'NULL')
            message = ("Domain '%s' ([%s, %s]),"
                        " '%s %s %s %s' - %s"
                            % (domain, self.data['rr_groups_index'],
                                self.data['rrs_index'],
                                label, class_,
                                type_, rdata,
                                msg))
            DMSError.__init__(self, message)
            lineno = 1
            col = 1

        self.message = message
        self.lineno = lineno
        self.col = col

    def __str__(self):
        if hasattr(self, 'rdata_pyparsing') and self.rdata_pyparsing:
            return self.pp_exc.__str__()
        else:
            return super().__str__()
    
    def __repr__(self):
        if hasattr(self, 'rdata_pyparsing') and self.rdata_pyparsing:
            return self.pp_exc.__repr__()
        else:
            return super().__repr__()

    def markInputline(self):
        if hasattr(self, 'rdata_pyparsing') and self.rdata_pyparsing:
            return self.pp_exc.markInputline()
        else:
            return None

class UnhandledClassError(ZoneParseError):
    """
    Unhandled class for record - we only ever do IN
    
    * JSONRPC Error:      -8
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "class '%s' is not 'IN'." % rr_data['class']
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -8

class UnhandledTypeError(ZoneParseError):
    """
    RR type is one we don't handle.
    
    * JSONRPC Error:      -9
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "type '%s' is not supported." % rr_data['type']
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -9

class Not7ValuesSOAParseError(ZoneParseError):
    """
    7 fields were not supplied as required by RFC 1035
    
    * JSONRPC Error:      -10
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'num_soa_rdata_values' - number of SOA fields given
    """
    def __init__(self, domain, rr_data):
        num_soa_rdata_values = len(rr_data['rdata'].split())
        msg = ("SOA must have 7 rdata values - %s supplied."
                % num_soa_rdata_values)
        super().__init__(domain, rr_data, msg=msg)
        self.data['num_soa_rdata_values'] = num_soa_rdata_values
        self.jsonrpc_error = -10

class SOASerialMustBeInteger(ZoneParseError):
    """
    SOA serial number must be an integer value.
    
    * JSONRPC Error:      -11
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'soa_serial_thing'  - thing given as SOA serial no.
    """
    def __init__(self, domain, rr_data):
        soa_serial_thing = rr_data['rdata'].split()[2]
        msg = ("SOA serial must be an integer, not '%s'."
                    % soa_serial_thing)
        super().__init__(domain, rr_data, msg=msg)
        self.data['soa_serial_thing'] = soa_serial_thing
        self.jsonrpc_error = -11

class LabelNotInDomain(ZoneParseError):
    """
    FQDN Label outside of domain
    
    * JSONRPC Error:      -12
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'label_thing'       - thing given as RR label
    """
    def __init__(self, domain, rr_data):
        label_thing = rr_data['label']
        msg = ("FQDN label '%s' is not within domain." % label_thing)
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.data['label_thing'] = label_thing
        self.jsonrpc_error = -12

class BadNameOwnerError(ZoneParseError):
    """
    Owner name of an A AAAA or MX record is not a valid hostname
    
    * JSONRPC Error:      -13
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'label_thing'       - thing given as RR label
    """
    def __init__(self, domain, rr_data):
        label_thing = rr_data['label']
        msg = ("label '%s' for an %s RR is a bad name>" 
                % (label_thing, rr_data['type']))
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.data['label_thing'] = label_thing
        self.jsonrpc_error = -13

class BadNameRdataError(ZoneParseError):
    """
    Name in the rdata of a record is not a valid hostname
    
    * JSONRPC Error:      -14
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'rdata_thing'   - bad RDATA of RR
        * 'bad_name'      - bad hostname in RDATA
    """
    def __init__(self, domain, rr_data, bad_name):
        rdata_thing = rr_data['rdata']
        bad_name = bad_name
        msg = ("Bad name '%s' in rdata for %s RR." % 
            (bad_name, rr_data['type']))
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.data['rdata_thing'] = rdata_thing
        self.data['bad_name'] = bad_name
        self.jsonrpc_error = -14

class ZoneError(ZoneParseError):
    """
    Zone related resource record error.
    
    * JSONRPC Error:      JSONRPC_INTERNAL_ERROR
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    pass

class ZoneAlreadyHasSOARecord(ZoneError):
    """
    Zone already has an SOA record.

    * JSONRPC Error:      -15
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "An SOA record already exists for this domain"
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -15

class ZoneSOARecordNotAtApex(ZoneError):
    """
    Zone already has an SOA record.

    * JSONRPC Error:      -16
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        self.label_thing = rr_data['label']
        msg = "Incorrect SOA RR label '%s' - should be '@'." % self.label_thing
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -16

class DuplicateRecordInZone(ZoneError):
    """
    Zone already has a record for this.

    * JSONRPC Error:      -17
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "Record already exists - duplicate."
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -17

class ZoneCNAMEExists(ZoneError):
    """
    Zone already has a CNAME using this label.

    * JSONRPC Error:      -18
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = ("CNAME exists using this label '%s' - can't create RR."
                % rr_data['label'])
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -18

class ZoneCNAMELabelExists(ZoneError):
    """
    Zone already has a CNAME using this label.

    * JSONRPC Error:      -19
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = ("Label '%s' already exists - can't create CNAME RR." 
                % rr_data['label'])
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -19

class DuplicateRecordInZone(ZoneError):
    """
    Zone already has a record for this.

    * JSONRPC Error:      -20
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "Record already exists - duplicate."
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -20

class ZoneCheckIntegrityNoGlue(ZoneError):
    """
    Record in zone does not have valid in zone glue

    * JSONRPC Error:      -21
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, glue_name):
        msg = "In Zone glue '%s' does not exist." % glue_name
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -21
    

class ZoneHasNoSOARecord(DMSError):
    """
    Zone has No SOA record.

    * JSONRPC Error:      -22
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, domain):
        message = "Zone '%s' has no SOA record - please fix." % domain
        super().__init__(message)
        self.data['name'] = domain
        self.jsonrpc_error = -22

class ZoneHasNoNSRecord(ZoneError):
    """
    Zone has No NS records.

    * JSONRPC Error:      -23
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "Zone has no apex NS record."
        super().__init__(domain, rr_data, msg=msg, rewind_loc=True)
        self.jsonrpc_error = -23

class RdataParseError(ZoneParseError):
    """
    Somewhere in the rdata processing (probably within dnspython)
    sense could not be made of the data

    * JSONRPC Error:      -24
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
        * 'rdata_thing'       - given invalid RDATA
    """
    def __init__(self, domain, rr_data, msg=None):
        rdata_thing = rr_data['rdata']
        if not msg:
            msg = ("RDATA invalid: '%s'."
                        % rdata_thing)
        super().__init__(domain, rr_data, msg=msg)
        self.data['rdata_thing'] = rdata_thing
        self.jsonrpc_error = -24

class PrivilegeNeeded(ZoneParseError):
    """
    Privilege is needed to set this RR field

    * JSONRPC Error:      JSONRPC_INTERNAL_ERROR
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """

class AdminPrivilegeNeeded(PrivilegeNeeded):
    """
    Administrative privilege is needed to set this RR field

    * JSONRPC Error:      -26
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, field_name, msg=None):
        msg = ("Administrator privilege required for '%s'." % field_name)
        super().__init__(domain, rr_data, msg=msg, 
                use_pyparsing=False)
        self.data['field_name'] = field_name
        self.jsonrpc_error = -26

class HelpdeskPrivilegeNeeded(PrivilegeNeeded):
    """
    Help desk privilege is needed to set this RR field

    * JSONRPC Error:      -27
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, field_name, msg=None):
        msg = ("Help desk privilege required for '%s'." % field_name)
        super().__init__(domain, rr_data, msg=msg, use_pyparsing=False)
        self.data['field_name'] = field_name
        self.jsonrpc_error = -27

class ZoneNotFound(DMSError):
    """
    For a DMI, can't find the requested zone.
    
    * JSONRPC Error:      -28
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' not found." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -28

class ZoneNotFoundByZoneId(ZoneNotFound):
    """
    For a DMI, can't find the requested zone.
    
    * JSONRPC Error:      -29
    * JSONRPC data keys:
        * 'zone_id'      - Zone ID
    """
    def __init__(self, zone_id):
        message = "Zone ID '%s' not found." % zone_id
        DMSError.__init__(self, message)
        self.data['zone_id'] = zone_id
        self.jsonrpc_error = -29

class ZiNotFound(ZoneNotFound):
    """
    For a DMI, can't find the requested zi.
    
    * JSONRPC Error:      -30
    * JSONRPC data keys:
        * 'name'  - domain name
    * JSONRPC data keys:
        * 'zi_id' - Zone Instance ID (can be None/Null)
    """
    def __init__(self, name, zi_id):
        message = "Zi for '%s', zone '%s' not found." % (zi_id, name)
        DMSError.__init__(self, message)
        self.data['name'] = name
        self.data['zi_id'] = zi_id
        self.jsonrpc_error = -30

class ZoneExists(DMSError):
    """
    For a DMI, can't create the requested zone as it already exists.
    
    * JSONRPC Error:      -31
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, domain):
        message = "Zone '%s' already exists, can't create it." % domain
        super().__init__(message)
        self.data['name'] = domain
        self.jsonrpc_error = -31

class NoZonesFound(DMSError):
    """
    For a DMI, can't find the requested zones.
    
    * JSONRPC Error:      -32
    * JSONRPC data keys:
        * 'name_pattern'  - wildcard name pattern
    """
    def __init__(self, name_pattern):
        if name_pattern:
            message = "No zones matching '%s' found." % name_pattern
        else:
            message = "No zones found."
            name_pattern = '*'
        super().__init__(message)
        self.data['name_pattern'] = name_pattern
        self.jsonrpc_error = -32

class ZoneSmFailure(DMSError):
    """
    Zone SM Failure - synchronous execution of the Zone SM
    was not successful.

    * JSONRPC Error: -80
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, name, event_message, event_results):
        if event_message:
            message = event_message
        else:
            message = ("Edit lock for '%s' can't be canceled." 
                        % name)
        super().__init__(message)
        self.data['name'] = name
        self.data['event_message'] = event_message
        self.data['event_results'] = event_results
        self.jsonrpc_error = -80

class CancelEditLockFailure(ZoneSmFailure):
    """
    For a DMI, can't clear edit_lock for zone.
    
    * JSONRPC Error:      -33
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Cancel Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -33

class EditLockFailure(ZoneSmFailure):
    """
    For a DMI, can't obtain an edit_lock for zone.
    
    * JSONRPC Error:      -34
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Lock Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -34

class TickleEditLockFailure(ZoneSmFailure):
    """
    Can't tickle the edit lock timeout event due to an incorrect
    edit_lock_token

    * JSONRPC Error:      -35
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Timeout Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -35

class UpdateZoneFailure(ZoneSmFailure):
    """
    Can't update zone as it is locked.

    * JSONRPC Error:      -35
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Timeout Event Message
        * 'event_results' - Event results object
        * 'zi_id' -         ID of saved ZI
    """
    def __init__(self, name, event_message, event_results, zi_id=None):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -35
        self.data['zi_id'] = zi_id

class ZoneExists(DMSError):
    """
    Trying to create a zone that already exists

    * JSONRPC Error:      -36
    * JSONRPC data keys:
        * 'name'        - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' already exists." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -36

class ZoneNotDeleted(DMSError):
    """
    Trying to destroy a zone that is active

    * JSONRPC Error:      -37
    * JSONRPC data keys:
        * 'name'        - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' is not DELETED" % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -37

class ZiInUse(DMSError):
    """
    Trying to delete a zi that is currently published.

    * JSONRPC Error:      -38
    * JSONRPC data keys:
        * 'name'        - domain name
    """
    def __init__(self, name, zi_id):
        message = "Zone '%s', zi '%s' is in use." % (name, zi_id)
        super().__init__(message)
        self.data['name'] = name
        self.data['zi_id'] = zi_id
        self.jsonrpc_error = -38

class BinaryFileError(DMSError):
    """
    Trying to load a binary file.

    * JSONRPC Error:      -39
    * JSONRPC data keys:
        * 'file_name'   - file name
    """
    def __init__(self, file_name):
        message = "%s: appears to be a binary file." % (file_name)
        super().__init__(message)
        self.data['file_name'] = file_name
        self.jsonrpc_error = -38

class ZoneSecTagExists(DMSError):
    """
    Trying to create a security tag that already exists.

    * JSONRPC Error:      -40
    * JSONRPC data keys:
        * 'sectag_label'   - security tag label
    """
    def __init__(self, sectag_label):
        message = "Zone security tag '%s' already exists." % (sectag_label)
        super().__init__(message)
        self.data['sectag_label'] = sectag_label
        self.jsonrpc_error = -40

class ZoneSecTagDoesNotExist(DMSError):
    """
    Zone security tag does not exist. 

    * JSONRPC Error:      -41
    * JSONRPC data keys:
        * 'sectag_label'   - security tag label
    """
    def __init__(self, sectag_label):
        message = "Zone security tag '%s' does not exist." % (sectag_label)
        super().__init__(message)
        self.data['sectag_label'] = sectag_label
        self.jsonrpc_error = -41

class ZoneSecTagConfigError(ZoneSecTagDoesNotExist):
    """
    Zone security tag for DMS server does not exist. 

    * JSONRPC Error:      -42
    * JSONRPC data keys:
        * 'sectag_label'   - security tag label
    """
    def __init__(self, sectag_label):
        message = ("Zone security tag '%s' misconfigured - does not exist." 
                   % sectag_label)
        super(DMSError, self).__init__(message)
        self.data['sectag_label'] = sectag_label
        self.jsonrpc_error = -42

class ZoneSecTagStillUsed(DMSError):
    """
    Zone security tag is still in use 

    * JSONRPC Error:      -43
    * JSONRPC data keys:
        * 'sectag_label'   - security tag label
    """
    def __init__(self, sectag_label):
        message = ("Zone security tag '%s' is still in use." 
                   % sectag_label)
        super().__init__(message)
        self.data['sectag_label'] = sectag_label
        self.jsonrpc_error = -43

class NoZoneSecTagsFound(DMSError):
    """
    No zone security tags found for this domain. 

    * JSONRPC Error:      -44
    * JSONRPC data keys:
        * 'name'   - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - no security tags found." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -44

class NoSecTagsExist(DMSError):
    """
    No zone security tags found for this domain. 

    * JSONRPC Error:      -45
    """
    def __init__(self):
        message = "No security tags exist. This is REALLY BAD."
        super().__init__(message)
        self.jsonrpc_error = -45

class SecTagPermissionDenied(DMSError):
    """
    Operations on security tags can only be done with Admin privilege

    * JSONRPC Error:      -46
    * JSONRPC data keys:
        * 'sectag_label'   - security tag label
    """
    def __init__(self, sectag_label):
        message = "Security tag '%s' - Permission denied." % sectag_label
        super().__init__(message)
        self.data['sectag_label'] = sectag_label
        self.jsonrpc_error = -46

class ZoneNameUndefined(DMSError):
    """
    Name of the Zone can not be determined.

    * JSONRPC Error:      -47
    * JSONRPC data keys:
        * 'file_name'   - file name being loaded.
    """
    def __init__(self, file_name):
        message = "%s: - zone name cannot be determined." % file_name
        super().__init__(message)
        self.data['file_name'] = file_name
        self.jsonrpc_error = -47

class ZiParseError(DMSError):
    """
    Zi related SOA/TTL data error.
    
    * JSONRPC Error:      JSONRPC_INTERNAL_ERROR
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'zi_field'  - ZI field where error found
        * 'value'     - value in error
    """
    def __init__(self, name, zi_field, value, exc_msg=None):
        # Some name messing for setting default values from zone_tool
        name_str = "Zone '%s'" % name if name else "Config key"
        if not name:
            name = name_str
        if not exc_msg:
            msg = "%s - '%s' has invalid value."
            message = msg % (name_str, zi_field)
        else:
            msg = "%s - '%s': %s"
            message = msg % (name_str, zi_field, exc_msg)
        super().__init__(message)
        self.data['name'] = name
        self.data['zi_field'] = zi_field
        self.data['value'] = value
        self.jsonrpc_error = JSONRPC_INTERNAL_ERROR

class HostnameZiParseError(ZiParseError):
    """
    Zi related SOA mname or rname value error.
    
    * JSONRPC Error:      -48
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'zi_field'  - ZI field where error found
        * 'value'     - value in error
    """
    def __init__(self, name, zi_field, value, exc_msg=None):
        super().__init__(name, zi_field, value, exc_msg)
        self.jsonrpc_error = -48


class TtlZiParseError(ZiParseError):
    """
    Zi related ttl value error.
    
    * JSONRPC Error:      -49
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'zi_field'  - ZI field where error found
        * 'value'     - value in error
    """
    def __init__(self, name, zi_field, value, exc_msg=None):
        super().__init__(name, zi_field, value, exc_msg)
        self.jsonrpc_error = -49

class IncludeNotSupported(ZoneParseError):
    """
    Our zone parser does not support the $INCLUDE statement
    
    * JSONRPC Error:      -50
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "$INCLUDE is not supported by the Net24 DMS zone file parser."
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -50


class DirectiveParseError(ZoneParseError):
    pass

class HostnameParseError(DirectiveParseError):
    """
    Hostname parse error while parsing zone file.
    
    * JSONRPC Error:      -51
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, value, info=None):
        directive = rr_data['directive']
        if info:
            msg = ("Bad name '%s' in %s directive - %s" 
                    % (value, directive, info))
        else:
            msg = "Bad name '%s' in '%s' directive." % (value, directive)
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -51

class TtlParseError(DirectiveParseError):
    """
    Hostname parse error while parsing zone file.
    
    * JSONRPC Error:      -52
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, value, info=None):
        directive = rr_data['directive']
        if info:
            msg = ("Bad TTL '%s' in %s directive - %s" 
                        % (value, directive, info))
        else:
            msg = "Bad TTL '%s' in %s directive." % (value, directive)
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -52

class TtlInWrongPlace(DirectiveParseError):
    """
    $TTL not at top of zone file.
    
    * JSONRPC Error:      -53
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data, file_name=None):
        msg = "$TTL can only be at the top of a zone."
        if file_name:
            msg = "%s: %s" % (file_name, msg)
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -53

class GenerateNotSupported(ZoneParseError):
    """
    Our zone parser does not support the $GENERATE statement
    
    * JSONRPC Error:      -54
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "$GENERATE is not supported by the Net24 DMS zone file parser."
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -54


class BadInitialZoneName(DMSError):
    """
    Name of the Zone can not be determined.

    * JSONRPC Error:      -55
    * JSONRPC data keys:
        * 'file_name'   - file name being loaded.
    """
    def __init__(self, file_name, value, exc_msg=None):
        if not exc_msg:
            message = "%s: zone name '%s' is invalid." % (file_name, value)
        else:
            message = ("%s: zone name '%s' - %s" 
                        % (file_name, value, str(exc_msg))) 
        super().__init__(message)
        self.data['file_name'] = file_name
        self.data['value'] = value
        self.jsonrpc_error = -55

class ConfigBatchHoldFailed(DMSError):
    """
    Configuration SM Failed to enter CONFIG_HOLD for batch zone creation

    * JSONRPC Error:      -56
    """
    def __init__(self):
        message = "MasterSM failed to enter CONFIG_HOLD for batch zone creation"
        super().__init__(message)
        self.jsonrpc_error = -56

class ZoneMultipleResults(DMSError):
    """
    For a DMI, search for one requested zone found multiple entities
    
    * JSONRPC Error:      -57
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' multiple results found." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -57

class SgMultipleResults(DMSError):
    """
    For a DMI, search for one requested SG found multiple entities
    
    * JSONRPC Error:      -58
    * JSONRPC data keys:
        * 'sg_name'      - SG name
    """
    def __init__(self, sg_name):
        message = "SG '%s' - multiple results found." % sg_name
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.jsonrpc_error = -58

class NoSgFound(DMSError):
    """
    For a DMI, requested SG not found
    
    * JSONRPC Error:      -59
    * JSONRPC data keys:
        * 'sg_name'      - SG name
    """
    def __init__(self, sg_name):
        message = "SG '%s' - not found." % sg_name
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.jsonrpc_error = -59

class ZoneNotDnssecEnabled(DMSError):
    """
    Zone is not DNSSEC enabled.
    
    * JSONRPC Error:      -60
    * JSONRPC data keys:
        * 'name'          - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - not DNSSEC enabled." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -60

class ZoneCfgItem(DMSError):
    pass

class ZoneCfgItemNotFound(ZoneCfgItem):
    """
    An item with the given key name can not be found in the zone_cfg table

    * JSONRPC Error:      -61
    * JSONRPC data keys:
        * 'key'      - item key name
    """
    def __init__(self, key):
        message = "ZoneCfg Item '%s' - not found." % key
        super().__init__(message)
        self.data['key'] = key
        self.jsonrpc_error = -61

class ZoneBeingCreated(DMSError):
    """
    A zone in the creation process can not be deleted or undeleted

    * JSONRPC Error:      -62
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - event message
        * 'event_results' - event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -62

class SgNameRequired(DMSError):
    """
    SG Name is required for this configuration parameter
    
    * JSONRPC Error:      -63
    * JSONRPC data keys:
        * 'config_key'      - config parameter key
    """
    def __init__(self, config_key):
        message = "Config_key '%s' - requires sg_name" % config_key
        super().__init__(message)
        self.data['config_key'] = config_key
        self.jsonrpc_error = -63

class ReferenceExists(DMSError):
    """
    Trying to create a reference that already exists.

    * JSONRPC Error:      -64
    * JSONRPC data keys:
        * 'reference'   - reference code
    """
    def __init__(self, reference):
        message = "Reference '%s' already exists." % (reference)
        super().__init__(message)
        self.data['reference'] = reference
        self.jsonrpc_error = -64

class ReferenceDoesNotExist(DMSError):
    """
    Reference does not exist. 

    * JSONRPC Error:      -65
    * JSONRPC data keys:
        * 'reference'   - reference code
    """
    def __init__(self, reference):
        message = "Reference '%s' does not exist." % (reference)
        super().__init__(message)
        self.data['reference'] = reference
        self.jsonrpc_error = -65

class ReferenceStillUsed(DMSError):
    """
    Reference is still in use 

    * JSONRPC Error:      -66
    * JSONRPC data keys:
        * 'reference'   - reference code
    """
    def __init__(self, reference):
        message = ("Reference '%s' is still in use." 
                   % reference)
        super().__init__(message)
        self.data['reference'] = reference
        self.jsonrpc_error = -66

class NoReferenceFound(DMSError):
    """
    No Reference found.

    * JSONRPC Error:      -67
    * JSONRPC data keys:
        * 'reference'   - reference code
    """
    def __init__(self, reference):
        message = "Reference '%s' - not found." % reference
        super().__init__(message)
        self.data['reference'] = reference
        self.jsonrpc_error = -67

class MultipleReferencesFound(DMSError):
    """
    Multiple references were found 

    * JSONRPC Error:      -68
    * JSONRPC data keys:
        * 'reference'   - reference code
    """
    def __init__(self, reference):
        message = "Reference '%s' - multiple references found!" % reference
        super().__init__(message)
        self.data['name'] = reference
        self.jsonrpc_error = -68

class ActiveZoneExists(ZoneSmFailure):
    """
    Another zone instance is active - this one cannot be activated.

    * JSONRPC Error:      -69
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - event message
        * 'event_results' - event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -69

class ZoneFilesStillExist(ZoneSmFailure):
    """
    Can't destroy/nuke a zone as its zone files still exist

    * JSONRPC Error:      -70
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'event_message' - Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, name, event_message, event_results):
        super().__init__(name, event_message, event_results)
        self.jsonrpc_error = -70

class ZoneCfgItemValueError(ZoneCfgItem):
    """
    An item with the given key name can not be interpolated from its string

    This can happen for string -> boolean conversions

    * JSONRPC Error:      -71
    * JSONRPC data keys:
        * 'key'      - item key name
        * 'value'    - item value
    """
    def __init__(self, key, value):
        message = ("ZoneCfg Item '%s' - value '%s' cannot be interpolated"
                % (key, value))
        super().__init__(message)
        self.data['key'] = key
        self.data['value'] = value
        self.jsonrpc_error = -71

class SgExists(DMSError):
    """
    For a DMI, SG already exists
    
    * JSONRPC Error:      -72
    * JSONRPC data keys:
        * 'sg_name'      - SG name
    """
    def __init__(self, sg_name):
        message = "SG '%s' - already exists" % sg_name
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.jsonrpc_error = -72

class SgStillUsed(DMSError):
    """
    Container class for SG Deleteion errors
    """
    pass

class SgStillHasZones(SgStillUsed):
    """
    For a DMI, attempted deletion, SG still has zones
    
    * JSONRPC Error:      -73
    * JSONRPC data keys:
        * 'sg_name'      - SG name
    """
    def __init__(self, sg_name):
        message = "SG '%s' - is still in use, has zones" % sg_name
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.jsonrpc_error = -73

class ServerError(DMSError):
    """
    Ancestor class for server functions, saves code.
    """

class ServerExists(ServerError):
    """
    Server already exists
    
    * JSONRPC Error:      -74
    * JSONRPC data keys:
        * 'server_name'      - server name
    """
    def __init__(self, server_name):
        message = "Server '%s' - already exists" % server_name
        super().__init__(message)
        self.data['server_name'] = server_name
        self.jsonrpc_error = -74

class NoServerFound(ServerError):
    """
    Server does not exist
    
    * JSONRPC Error:      -75
    * JSONRPC data keys:
        * 'server_name'      - server name
    """
    def __init__(self, server_name):
        message = "Server '%s' - does not exist" % server_name
        super().__init__(message)
        self.data['server_name'] = server_name
        self.jsonrpc_error = -75

class NoServerFoundByAddress(ServerError):
    """
    Server does not exist
    
    * JSONRPC Error:      -76
    * JSONRPC data keys:
        * 'address'      - server address
    """
    def __init__(self, address):
        message = "Server '%s' - not found" % address
        super().__init__(message)
        self.data['address'] = address
        self.jsonrpc_error = -76

class ServerAddressExists(ServerError):
    """
    Server with the given address exists
    
    * JSONRPC Error:      -77
    * JSONRPC data keys:
        * 'address'      - server address
    """
    def __init__(self, address):
        message = ("Server '%s' - with this address already exists"
                    % address)
        super().__init__(message)
        self.data['address'] = address
        self.jsonrpc_error = -77

class ServerNotDisabled(ServerError):
    """
    Server must be disabled for operation to proeceed.
    
    * JSONRPC Error:      -78
    * JSONRPC data keys:
        * 'server_name'      - server name
    """
    def __init__(self, server_name):
        message = ("Server '%s' - server must be disabled for operation"
                    % server_name)
        super().__init__(message)
        self.data['server_name'] = server_name
        self.jsonrpc_error = -78

class ServerSmFailure(DMSError):
    """
    Server SM Failure - synchronous execution of the Server SM
    was not successful.

    * JSONRPC Error: -79
    * JSONRPC data keys:
        * 'server_name'    - server name
        * 'event_message' - Event Message
        * 'event_results' - Event results object
    """
    def __init__(self, server_name, event_message, event_results):
        if event_message:
            message = event_message
        else:
            message = ("Server SM '%s' failed." 
                        % server_name)
        super().__init__(message)
        self.data['server_name'] = server_name
        self.data['event_message'] = event_message
        self.data['event_results'] = event_results
        self.jsonrpc_error = -79

class RrQueryDomainError(DMSError):
    """
    For query an RR, domain cannot start with '.'
    
    * JSONRPC Error:      -81
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Domain '%s' - name cannot start with '.'" % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -81

class ReferenceFormatError(DMSError):
    """
    A reference can only consist of the characters '-_a-zA-Z0-9.@', 
    and must start with a letter or numeral.  It also must be less than
    1024 characters long.

    * JSONRPC Error:      -82
    * JSONRPC data keys:
        * 'reference' - reference name
        * 'error'     - error message
    """
    def __init__(self, reference, error):
        message = "Reference '%s' - format error - %s" % (reference, error)
        super().__init__(message)
        self.data['reference'] = reference
        self.data['error'] = error
        self.jsonrpc_error = -82

class InvalidUpdateOperation(ZoneParseError):
    """
    RR type is one we don't handle.
    
    * JSONRPC Error:      -83
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "invalid update operation '%s'." % rr_data['update_op']
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -83

class IncrementalUpdateNotInTrialRun(DMSError):
    """
    Error in Incremental Update mechanism.  Update mechanism not in
    Trial Run Mode.
    
    * JSONRPC Error:      JSON_RPC_INTERNAL_ERROR
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - ZiUpdate should be in trial mode." % name
        super().__init__(message)
        self.data['name'] = name

class UpdateTypeNotSupported(ZoneParseError):
    """
    Our zone parser does not support the $UPDATE_TYPE statement in edit mode
    
    * JSONRPC Error:      -84
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "$UPDATE_TYPE is not supported edit mode."
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -84

class RropNotSupported(ZoneParseError):
    """
    Our zone parser does not support the RROP: RR flag in edit mode
    
    * JSONRPC Error:      -85
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "RROP: RR flag is not supported edit mode."
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -85

class UpdateTypeAlreadyQueued(DMSError):
    """
    An update of the given type is already queued for the zone

    * JSONRPC Error:      -86
    * JSONRPC data keys:
        * 'name'          - domain name
        * 'update_type'   - update type
    """
    def __init__(self, name, update_type):
        message = ("Zone '%s' - Update type of '%s' already queued" 
                            % (name, update_type))
        super().__init__(message)
        self.data['name'] = name
        self.data['update_type'] = update_type
        self.jsonrpc_error = -86

class UpdateTypeRequired(DMSError):
    """
    An update_type is required parameter for an incremental update.

    * JSONRPC Error:      -87
    * JSONRPC data keys:
        * 'name'          - domain name

    """
    def __init__(self, name):
        message = ("Zone '%s' - update_type is arequired parameter" 
                            % (name))
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -87

class ZoneDisabled(DMSError):
    """
    Zone disabled. Can't do operation.
    
    * JSONRPC Error:      -88
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' disabled." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -88

class InvalidDomainName(DMSError):
    """
    Domain name is invalid.
    
    * JSONRPC Error:      -89
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Invalid domain name '%s'" % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -89


class IncrementalUpdatesDisabled(DMSError):
    """
    Incremental Updates are disabled for this zone.
    
    * JSONRPC Error:      -90
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - incremental updates are disabled" % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -90

class ReverseNamesNotAccepted(InvalidDomainName):
    """
    Reverse domain names are generated from CIDR network names.
    
    * JSONRPC Error:      -91
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = ("Zone '%s' - reverse names not accepted, please use "
                    "CIDR network name instead."
                    % name)
        super(DMSError, self).__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -91

class ZoneHasNoZi(DMSError):
    """
    For a Zone, no ZI has no candidate or published ZI
    
    * JSONRPC Error: - 92
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - has no candidate or published ZI." % name
        DMSError.__init__(self, message)
        self.data['name'] = name
        self.jsonrpc_error = -92
        
class ZoneNotDisabled(DMSError):
    """
    Zone disabled. Can't do operation.
    
    * JSONRPC Error:      -94
    * JSONRPC data keys:
        * 'name'      - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' not disabled." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -94

class SgStillHasServers(SgStillUsed):
    """
    For a DMI, attempted deletion, SG still has servers
    
    * JSONRPC Error:      -95
    * JSONRPC data keys:
        * 'sg_name'      - SG name
    """
    def __init__(self, sg_name):
        message = "SG '%s' - is still in use, has servers" % sg_name
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.jsonrpc_error = -95

class InvalidHmacType(DMSError):
    """
    Invalid Hmac type given

    * JSONRPC Error:      -96
    * JSONRPC data keys:
        * 'hmac_type'      - Given hmac type
    """
    def __init__(self, hmac_type):
        message = "HMAC '%s' - is invalid" % hmac_type
        super().__init__(message)
        self.data['hmac_type'] = hmac_type
        self.jsonrpc_error = -96

class RRNoTypeGiven(ZoneParseError):
    """
    RR has no type given.
    
    * JSONRPC Error:      -97
    * JSONRPC data keys:
        * 'name'      - domain name
        * 'rr_data'   - RR data from zi, Not RDATA!
        * 'rr_groups_index'   - index into rr_groups array.
        * 'rrs_index'         - index of RR in rrs of rr_groups
    """
    def __init__(self, domain, rr_data):
        msg = "RR has no type given - invalid."
        super().__init__(domain, rr_data, msg=msg)
        self.jsonrpc_error = -97

class ZoneSearchPatternError(DMSError):
    """
    Given zone search pattern is invalid
    """

class OnlyOneLoneWildcardValid(ZoneSearchPatternError):
    """
    Only one lone '*' or '%' for zone search pattern is valid

    * JSONRPC Error:      -98
    * JSONRPC data keys:
        * 'search_pattern'    - Zone search pattern
    """
    def __init__(self, search_pattern):
        msg = "Only one lone '*' or '%' for zone search pattern is valid"
        super().__init__(msg)
        self.data['search_pattern'] = search_pattern
        self.jsonrpc_error = -98

class ReferenceMustBeGiven(ZoneSearchPatternError):
    """
    When giving a zone search pattern, a reference must be given

    * JSONRPC Error:      -99
    * JSONRPC data keys:
        * 'search_pattern'    - Zone search pattern
    """
    def __init__(self, search_pattern):
        msg = "When giving a zone search pattern, a reference must be given"
        super().__init__(msg)
        self.data['search_pattern'] = search_pattern
        self.jsonrpc_error = -99


_zi_id_human_str = 'nnn or nnn+++|nnn---|nnn-m|nnn+m or |^+++|^---|^+m|^-m or m[.n]{s|m|h|d|w} or HH:MM or DD/MM or DD/MM/YYYY or DD/MM/YYYY,HH:MM or YYYY-MM-DD,HH:MM'
class ZiIdSyntaxError(DMSError):
    """
    ZI id given has invalid syntax.

    * JSONRPC Error:      -100
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id, exc_msg=None):
        if exc_msg:
            msg = "ZI id '%s' - " % zi_id + exc_msg
        else:
            msg = "ZI id lookup string '%s' has invalid syntax." % zi_id
            msg += " Try " + _zi_id_human_str
        super().__init__(msg)
        self.data['zi_id'] = zi_id
        self.jsonrpc_error = -100

class ZiIdAdjStringSyntaxError(ZiIdSyntaxError):
    """
    ZI id adjustment sub string has invalid syntax.

    * JSONRPC Error:      -101
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid syntax, use ---/+++/-n/+n as adjustment"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -101

class ZiIdTimeUnitSyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has an invalid time unit specifier.

    * JSONRPC Error:      -102
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid time specifier, use s,m,h,d,w,M, or Y"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -102

class ZiIdTimeAmountSyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has invalid time amount.

    * JSONRPC Error:      -103
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid time amount, numbers must be integer or decimal and within expected bounds"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -103

class ZiIdHhMmSyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has an invalid HH:MM time.

    * JSONRPC Error:      -104
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid HH:MM time string"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -104

class ZiIdDdSlashMmSyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has an invalid DD/MM date.

    * JSONRPC Error:      -105
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid DD/MM date string"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -105

class ZiIdDdMmYyyySyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has an invalid DD/MM/YYYY date.

    * JSONRPC Error:      -106
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid DD/MM/YYYY date string"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -106

class ZiIdIsoDateSyntaxError(ZiIdSyntaxError):
    """
    ZI id sub string has an invalid YYYY-MM-DD date.

    * JSONRPC Error:      -107
    * JSONRPC data keys:
        * 'zi_id'     - given zi_id string
    """
    def __init__(self, zi_id):
        msg = "invalid YYYY-MM-DD date string"
        super().__init__(zi_id, msg)
        self.jsonrpc_error = -107

class RestoreNamedDbError(DMSError):
    """
    Subclass for Errors relating to restore_named_db DR functionality
    """

class NamedStillRunning(RestoreNamedDbError):
    """
    Named is still running

    * JSONRPC Error:       -108
    * JSONRPC data keys:
        * 'rndc_status_exit_code' - exit code from 'rndc status'
    """
    def __init__(self, rndc_status_exit_code):
        msg = ("named is still running - rndc status exit code %s" 
                    % rndc_status_exit_code)
        super().__init__(msg)
        self.data['rndc_status_exit_code'] = rndc_status_exit_code
        self.jsonrpc_error = -108

class DmsdmdStillRunning(RestoreNamedDbError):
    """
    Dmsdmd is still running
    
    * JSONRPC Error:       -109
    * JSONRPC data keys:
        * dmsdmd_pid - dmsdmd PID
    """
    def __init__(self, dmsdmd_pid):
        msg = ("dmsdmd is still running - PID %s" 
                    % dmsdmd_pid)
        super().__init__(msg)
        self.data['dmsdmd_pid'] = dmsdmd_pid
        self.jsonrpc_error = -109

class PidFileValueError(RestoreNamedDbError):
    """
    PID file format error
    
    * JSONRPC Error:       -110
    * JSONRPC data keys:
        * 'pid_file' - PID file name
        * 'exception' - Value Error Exception
    """
    def __init__(self, pid_file, exception):
        msg = ("PID file %s - format error - %s" 
                % pid_file, str(exception))
        super().__init__(msg)
        self.data['pid_file'] = pid_file
        self.data['exception'] = str(exception)
        self.jsonrpc_error = -110

class PidFileAccessError(RestoreNamedDbError):
    """
    PID file format error
    
    * JSONRPC Error:       -111
    * JSONRPC data keys:
        * 'pid_file' - PID file name
        * 'exception' - Value Error Exception
    """
    def __init__(self, pid_file, os_error):
        msg = ("PID file %s - %s" 
                % (pid_file, os_error))
        super().__init__(msg)
        self.data['pid_file'] = pid_file
        self.data['os_error'] = os_error
        self.jsonrpc_error = -111

class ZoneFileWriteError(RestoreNamedDbError):
    """
    Can't write zone file

    * JSONRPC Error:       -112
    * JSONRPC data keys:
        * 'name'  - domain name
        * 'internal_error' - error that occured
    """
    def __init__(self, name, internal_error):
        msg = ("Zone '%s' internal write error - %s" 
                % (name, internal_error))
        super().__init__(msg)
        self.data['name'] = name
        self.data['internal_error'] = internal_error
        self.jsonrpc_error = -112

class NamedConfWriteError(RestoreNamedDbError):
    """
    Can't write named.conf sections

    * JSONRPC Error:       -113
    * JSONRPC data keys:
        * 'name'  - domain name
        * 'internal_error' - error that occured
    """
    def __init__(self, internal_error):
        msg = ("Named.conf includes internal write error - %s" 
                % (internal_error))
        super().__init__(msg)
        self.data['internal_error'] = internal_error
        self.jsonrpc_error = -113

class ReplicaSgExists(DMSError):
    """
    A master SG already exists
    
    * JSONRPC Error:      -114
    * JSONRPC data keys:
        * 'sg_name'          - SG name
        * 'replica_sg_name'   - master SG name
    """
    def __init__(self, sg_name, replica_sg_name):
        message = ("SG '%s' - master SG '%s' already exists" 
                    % (sg_name, replica_sg_name))
        super().__init__(message)
        self.data['sg_name'] = sg_name
        self.data['replica_sg_name'] = replica_sg_name
        self.jsonrpc_error = -114

class SOASerialOcclusionError(SOASerialError):
    """
    SOA Serial Occlusion Error.  SOA serial as recorded in database is
    maximum of current SOA serial value in master DNS server.

    * JSONRPC Error: -115
    """
    def __init__(self, domain):
        message = ("Zone '%s' - SOA Serial Occlusion Error - SOA serial as recorded in database is maximum of current SOA serial value in master DNS server." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -115

class SOASerialPublishedError(SOASerialError):
    """
    SOA Serial Published Error.  SOA serial number update is the same as
    published value in database.

    * JSONRPC Error: -116
    """
    def __init__(self, domain):
        message = ("Zone '%s' - SOA Serial Published Error - SOA serial number update is the same as published value in database." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -116

class ZoneNotPublished(DMSError):
    """
    Zone Not Published.  Can't poke DNS server.

    * JSONRPC Error: -117
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain):
        message = ("Zone '%s' - Not Published - can't poke DNS server." 
                            % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -117

class SOASerialCandidateIgnored(SOASerialError):
    """
    Proposed SOA Serial Candidate ignored.

    * JSONRPC Error: -118
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain):
        message = ("Zone '%s' - Proposed candidate SOA serial number ignored." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -118

class SOASerialRangeError(SOASerialError):
    """
    SOA Serial Number is out of range must be > 0 and <= 2**32 -1.

    * JSONRPC Error: -120
    * JSONRPC data keys:
        * 'name'  - domain name
    """
    def __init__(self, domain):
        message = ("Zone '%s' - SOA serial number is out of range, must be > 0, and <= 2**32 -1." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -120

class SOASerialTypeError(SOASerialError):
    """
    SOA Serial Number must be an integer.

    * JSONRPC Error: -121
    * JSONRPC data keys: 'name'  - domain name
    """
    def __init__(self, domain):
        message = ("Zone '%s' - SOA serial must be an integer." % domain)
        DMSError.__init__(self, message)
        self.data['name'] = domain
        self.jsonrpc_error = -121

class DBReadOnlyError(DMSError):
    """
    Database is in Read Only mode.

    * JSONRPC Error: - 122
    * JSONRPC data keys:
        * 'exc_msg'  - original exception message
    """
    def __init__(self, exc_msg):
        message = ("DB in Read Only mode - %s" % exc_msg[:100])
        DMSError.__init__(self, message)
        self.jsonrpc_error = -122
        self.data['exc_msg'] = exc_msg[:100]

class ZoneNoAltSgForSwap(DMSError):
    """
    Zone idoes not have an alternate SG for swapping
    
    * JSONRPC Error:      -123
    * JSONRPC data keys:
        * 'name'          - domain name
    """
    def __init__(self, name):
        message = "Zone '%s' - has no alt_sg to swap to." % name
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -123

class LoginIdError(DMSError):
    """
    DMS Error class to cover login_id exceptions
    """

class LoginIdFormatError(LoginIdError):
    """
    A login_id can only consist of the characters '-_a-zA-Z0-9.@', 
    and must start with a letter or numeral.  It also must be less than
    512 characters long.

    * JSONRPC Error:      -124
    * JSONRPC data keys:
        * 'login_id'  - login_id
        * 'error'     - error message
    """
    def __init__(self, login_id, error):
        message = "login_id '%s' - format error - %s" % (login_id, error)
        super().__init__(message)
        self.data['login_id'] = login_id
        self.data['error'] = error
        self.jsonrpc_error = -124

class LoginIdInvalidError(LoginIdError):
    """
    A login_id must be given, and be less than 512 characters long.

    * JSONRPC Error:      -125
    * JSONRPC data keys:
        * 'error'     - error message

    """
    def __init__(self, error):
        message = "login_id invalid - %s" % (error)
        super().__init__(message)
        self.data['error'] = error
        self.jsonrpc_error = -125

class ZiTextParseError(DMSError):
    """
    Parse Error.  The zone file text input as zi_text
    must be of a valid format

    * JSONRPC Error:      -126
    * JSONRPC data keys:
        * 'parse_error'        - error message
        * 'name'               - domain name
        * 'lineno'             - line number
        * 'col'                - column
        * 'marked_iinput_line' - input line with marked error

    """
    def __init__(self, domain, pp_exc):
        message = "Zone '%s' - parse error - %s" % (domain, str(pp_exc))
        super().__init__(message)
        self.data['parse_error'] = str(pp_exc)
        self.data['name'] = domain
        if hasattr(pp_exc, 'lineno'):
            self.data['lineno'] = pp_exc.lineno
        else:
            self.data['lineno'] = None
        if hasattr(pp_exc, 'col'):
            self.data['col'] = pp_exc.col
        else:
            self.data['col'] = None
        if hasattr(pp_exc, 'markInputline'):
            self.data['marked_input_line'] = pp_exc.markInputline()
        else:
            self.data['marked_input_line'] = None
        self.jsonrpc_error = -126


class ZoneAdminPrivilegeNeeded(DMSError):
    """
    DMI has not been assigned the privilege required to edit this zone.
    
    * JSONRPC Error:      -127
    * JSONRPC data keys:
        * 'name'          - domain name
    """
    def __init__(self, name):
        message = ("Zone '%s' - DMI does not have privilege to edit this zone"
                        % name)
        super().__init__(message)
        self.data['name'] = name
        self.jsonrpc_error = -127


class NoReplicaSgFound(DMSError):
    """
    For a DMI, Master SG not found
    
    * JSONRPC Error:      -128
    """
    def __init__(self):
        message = "No Master SG found."
        super().__init__(message)
        self.jsonrpc_error = -128

class EventNotFoundById(DMSError):
    """
    For an event_id, an event is not found
    
    * JSONRPC Error:      -129
    * JSONRPC data keys:
        * 'event_id'      - event_id being searched for
    """
    def __init__(self, event_id):
        message = "Event ID '%s': - no event of this ID exists" % event_id
        super().__init__(message)
        self.jsonrpc_error = -129
        self.data['event_id'] = event_id

class CantFailEventById(DMSError):
    """
    For an event_id, can't fail the event because it is processed or already
    failed.
    
    * JSONRPC Error:      -130
    * JSONRPC data keys:
        * 'event_id'      - event_id being failed
    """
    def __init__(self, event_id):
        message = "Event ID '%s': - this event can't be failed." % event_id
        super().__init__(message)
        self.jsonrpc_error = -130
        self.data['event_id'] = event_id

# Next JSONRPC Error -131


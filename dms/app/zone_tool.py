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
"""Zone Tool command line zone management program

Program implemented by subclassing net.24.core.process.Process, and 
replacing the main() method.
"""


import os
import sys
import io
import tempfile
import stat
import socket
import cmd
import re
import errno
import signal
import time
import shlex
import grp
import pwd
import syslog
from getopt import gnu_getopt
from getopt import GetoptError
from textwrap import TextWrapper
from subprocess import check_call
from subprocess import check_output
from subprocess import Popen
from subprocess import PIPE
from subprocess import STDOUT
from subprocess import CalledProcessError
from os.path import basename

from pyparsing import ParseBaseException
from pyparsing import ParseException
from pyparsing import ParseFatalException
from pyparsing import ParseSyntaxException
from pyparsing import RecursiveGrammarException
import dns.ttl
import sqlalchemy.exc

from magcode.core.process import Process
from magcode.core.process import BooleanCmdLineArg
from magcode.core.process import BaseCmdLineArg
from magcode.core.process import SignalBusiness
from magcode.core.process import SignalHandler
from magcode.core.globals_ import *
from magcode.core.database import *
from magcode.core.database.event import ESTATE_NEW
from magcode.core.database.event import ESTATE_RETRY
from dms.globals_ import *
from magcode.core.system_editor_pager import SystemEditorPager
from dms.cmdline_engine import CmdLineEngine
from dms.cmdline_engine import config_keys
from dms.cmdline_engine import server_types
from dms.cmdline_engine import tsig_key_algorithms
from dms.zone_text_util import data_to_bind
from dms.zone_text_util import bind_to_data
from dms.database import zone_cfg
from dms.database.server_sm import SSTATE_OK
from dms.database.server_sm import SSTATE_CONFIG
from dms.database.server_sm import SSTATE_DISABLED
from dms.exceptions import *
from dms.dns import label_re
from dms.dns import DOMN_LBLSEP
from dms.dns import DOMN_LBLREGEXP
from dms.dns import DOMN_CHRREGEXP
from dms.dns import DOMN_LBLLEN
from dms.dns import DOMN_MAXLEN

USAGE_MESSAGE = "Usage: %s [-dfhv] [-c config_file] <command> <domain-name>"
COMMAND_DESCRIPTION = "Edit a domain in the DMS"

# Internal globals to program
engine = None
db_session = None
switch_dict = {}

# Command line processing functions
class DoHelp(Exception):
    """
    Argument processing exception - no match
    """

class DoNothing(Exception):
    """
    Argument check error, go back to command line
    """

# Argument parsing functions used in ZoneToolCmd class below
# Global module namspace as it makes code below a lot tidier
ERROR_PREFIX = '***   '
ERROR_INDENT = '      '
OUTPUT_INDENT = '        '
_stdout = None
error_msg_wrapper = TextWrapper(initial_indent = ERROR_PREFIX, 
                                subsequent_indent = ERROR_INDENT)
result_msg_wrapper = TextWrapper(initial_indent = ERROR_INDENT, 
                                subsequent_indent = ERROR_INDENT)
output_msg_wrapper = TextWrapper(initial_indent = OUTPUT_INDENT + '  ', 
                                subsequent_indent = OUTPUT_INDENT + '  ')

def ln2strs(arg):
    """
    Splits arg into arguments, and returns tuple of args
    """
    return tuple(map(str, shlex.split(arg)))

def arg_domain_name_text(domain_name, **kwargs):
    """
    Process a <domain-name>
    """
    # Check routines also over in dms.dns if this needs to be changed
    if not re.match(DOMN_CHRREGEXP, domain_name):
        print(error_msg_wrapper.fill("<domain-name> can in some cases be a valid IP address or networ/mask, or if a domain contain the characters '-a-zA-Z0-9.'"), file=_stdout)
        return None
    if not domain_name.endswith(DOMN_LBLSEP):
        domain_name += DOMN_LBLSEP
    if len(domain_name) > DOMN_MAXLEN:
        print(ERROR_PREFIX + "<domain-name> is %s long, must be <= %s." 
                % (len(domain_name), DOMN_MAXLEN), file=_stdout)
        return None
    labels = domain_name.split(DOMN_LBLSEP)
    if labels[-1] != '':
        print(error_msg_wrapper.fill("'%s' is no the root domain." 
                    % labels[-1]), file=_stdout)
        return None
    for lbl in labels[:-1]:
        # Skip 'root' zone
        if not lbl:
            print(error_msg_wrapper.fill(
                "<domain-name> '%s' cannot have empty labels." 
                % domain_name.lower()), file=_stdout)
            return None
        if len(lbl) > DOMN_LBLLEN:
            print(error_msg_wrapper.fill(
                '<domain-name> - label longer than %s characters'
                    % DOMN_LBLLEN),
                file=_stdout)
            return None
        if not label_re.search(lbl):
            print(error_msg_wrapper.fill(
                "<domain-name> - invalid label '%s'" % lbl), file=_stdout)
            return None    
        if lbl[0] == '-' or lbl[-1] == '-':
            print(error_msg_wrapper.fill(
                "<domain-name> - invalid label '%s'" % lbl), file=_stdout)
            return None    
    return {'name': domain_name.lower()}

def arg_domain_name_net(domain_name, **kwargs):
    """
    Process a <domain-name> Handles Ip addresses, nets, and text
    """
    # Check routines also over in dms.dns if this needs to be changed
    # See if it has a netmask
    if domain_name.find('/') < 0:
        return arg_domain_name_text(domain_name, **kwargs)
    # Split to mask and network
    try:
        (network, mask) = domain_name.split('/')
    except ValueError:
        print(error_msg_wrapper.fill(
            "For a network, only one '/' can be given"), file=_stdout)
        return None
    try:
        mask = int(mask)
    except ValueError:
        print(error_msg_wrapper.fill(
            "network mask must be a valid decimal number."), file=_stdout)
        return None
    # Determine network family
    if network.find(':') >= 0 and network.find('.') < 0:
        try:
            socket.inet_pton(socket.AF_INET6, network)
            if mask not in range(4, 65, 4):
                print(error_msg_wrapper.fill(
                    "IPv6 network mask must be a multiple of 4 between 4 and 64"),
                    file=_stdout)
                return None
            return {'name': domain_name.lower()}
        except socket.error:
            pass
    elif network.isdigit() or network.find('.') >= 0 and network.find(':') < 0:
        try:
            network = network[:-1] if network.endswith('.') else network
            num_bytes = len(network.split('.'))
            if num_bytes < 4:
                network += (4 - num_bytes) * '.0'
            socket.inet_pton(socket.AF_INET, network)
            if mask not in (8, 16, 24):
                print(error_msg_wrapper.fill(
                    "IPv4 network mask must be 8, 16, or 24"), file=_stdout)
                return None
            return {'name': domain_name.lower()}
        except socket.error:
            pass
    print(error_msg_wrapper.fill("network/mask - invalid network '%s' given."
            % domain_name),
            file=_stdout)
    return None

    

def arg_domain_name(domain_name, **kwargs):
    """
    Process a <domain-name> Handles IP addresses, nets, and text
    """
    # Check routines also over in dms.dns if this needs to be changed
    # Check for network addresses
    try:
        socket.inet_pton(socket.AF_INET, domain_name)
        return {'name': domain_name.lower()}
    except socket.error:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, domain_name)
        return {'name': domain_name.lower()}
    except socket.error:
        pass
    return arg_domain_name_net(domain_name, **kwargs)

def arg_domain1_name(domain1_name, **kwargs):
    """
    Process a <domain1-name> Handles IP addresses, nets and text
    """
    result = arg_domain_name(domain1_name, **kwargs)
    if not result:
        return None
    return {'domain1_name': result['name']}

def arg_domain2_name(domain2_name, **kwargs):
    """
    Process a <domain2-name> Handles IP addresses, nets and text
    """
    result = arg_domain_name(domain2_name, **kwargs)
    if not result:
        return None
    return {'domain2_name': result['name']}

def arg_src_domain_name(src_domain_name, **kwargs):
    """
    Process a <src-domain-name> Handles IP addresses, nets and text
    """
    result = arg_domain_name(src_domain_name, **kwargs)
    if not result:
        return None
    return {'src_name': result['name']}

def arg_key_name(key_name, **kwargs):
    """
    Process a TSIG key name
    """
    result = arg_domain_name_text(key_name, **kwargs)
    if result:
        return {'key_name': result['name']}
    return None

def arg_label(label, **kwargs):
    """
    Process a <label>
    """
    if not re.match(r'^[\-_a-zA-Z0-9\.\?\*@]+$', label):
        print(ERROR_PREFIX + "<label> can only contain characters '-_a-zA-Z0-9.?*@'", file=_stdout)
        return None
    if len(label) > 255:
        print(ERROR_PREFIX + "<label> is %s long, must be <= 255." 
                % len(label), file=_stdout)
        return None
    return {'label': label.lower()}

def arg_rr_type(type_, **kwargs):
    """
    Process an rr_type argument
    """
    types = type_.split()
    out = []
    for t in types:
        if not re.match(r'^[_a-zA-Z0-9]+$', t):
            print(ERROR_PREFIX + "<rr_type> can only contain characters '_a-zA-Z0-9'", file=_stdout)
            return None
        if len(t) > 20:
            print(ERROR_PREFIX + "<rr_type> '%s' is %s long, must be <= 20." 
                    % (t, len(t)), file=_stdout)
            return None
        out.append(t.lower())
    return {'type': out}

def arg_rdata(rdata, **kwargs):
    """
    Process an rdata argument
    """
    if not re.match(r'^[\-\._a-zA-Z0-9 \t]+$', rdata):
        print(ERROR_PREFIX + "<rdata> can only contain characters '-._a-zA-Z0-9' \t", file=_stdout)
        return None
    return {'rdata': rdata}

def arg_sectag_label(sectag_label, **kwargs):
    """
    Process a <sectag-label>
    """
    if not re.match(r'^[\-_a-zA-Z0-9\.]+$', sectag_label):
        print(ERROR_PREFIX + "<sectag-label> can only contain characters '-_a-zA-Z0-9.'", file=_stdout)
        return None
    if not re.match(r'^[0-9a-zA-Z][\-_a-zA-Z0-9\.]*$', sectag_label):
        print(ERROR_PREFIX + "<sectag-label> must start with 'a-zA-Z0-9'", file=_stdout)
        return None
    if len(sectag_label) > 60:
        print(ERROR_PREFIX + "<sectag-label> is %s long, must be <= 60." 
                % len(sectag_label), file=_stdout)
        return None
    return {'sectag_label': sectag_label}

def _arg_zi_id(zi_id, arg_type, arg_str, **kwargs):
    """
    Process a <zi-id>
    """
    if zi_id == '*':
        zi_id = '0'
    # zi_id checks done futher in in ZoneEngine._resolv_zi_id
    return {arg_type: zi_id}

def arg_zi_id(zi_id, **kwargs):
    """
    Process a <zi-id>
    """
    return _arg_zi_id(zi_id, 'zi_id', 'zi-id', **kwargs)

def arg_zi1_id(zi1_id, **kwargs):
    """
    Process a <zi1-id>
    """
    return _arg_zi_id(zi1_id, 'zi1_id', 'zi1-id', **kwargs)

def arg_zi2_id(zi2_id, **kwargs):
    """
    Process a <zi2-id>
    """
    return _arg_zi_id(zi2_id, 'zi2_id', 'zi2-id', **kwargs)

def arg_zone_id(zone_id, **kwargs):
    """
    Process a <zone-id>
    """
    try:
        zone_id = int(zone_id)
    except ValueError:
        print(ERROR_PREFIX + "<zone-id> can only contain digits.",
                file=_stdout)
        return None
    return {'zone_id': zone_id}

def arg_last_limit(last_limit, **kwargs):
    """
    Process a <last-limit>
    """
    try:
        last_limit = int(last_limit)
    except ValueError:
        print(ERROR_PREFIX + "<last-limit> can only contain digits.",
                file=_stdout)
        return None
    return {'last_limit': last_limit}

def arg_event_id(event_id, **kwargs):
    """
    Process a <event-id>
    """
    try:
        event_id = int(event_id)
    except ValueError:
        print(ERROR_PREFIX + "<event-id> can only contain digits.",
                file=_stdout)
        return None
    return {'event_id': event_id}

def arg_edit_lock_token(edit_lock_token, **kwargs):
    """
    Process an <edit-lock-token>
    """
    try:
        edit_lock_token = int(edit_lock_token)
    except ValueError:
        print(ERROR_PREFIX + "<edit-lock-token> can only contain digits.",
                file=_stdout)
        return None
    return {'edit_lock_token': edit_lock_token}

def arg_force(force, **kwargs):
    """
    Process a 'force' argument
    """
    if force.lower() != 'force':
        print(ERROR_PREFIX + "'force' is the only option here.",
                file=_stdout)
        return None
    return {'force': True}

def arg_zone_attribute(attribute, **kwargs):
    """
    process zone flag
    """
    attributes = ('use_apex_ns', 'edit_lock', 'auto_dnssec', 'nsec3', 
                    'inc_updates')
    if (attribute.lower() not in attributes): 
        print (ERROR_PREFIX + "Can only take one of: %s." 
                    % str(attributes), file=_stdout)
        return None
    return {'attribute': attribute}

def arg_zone_option(zone_option, **kwargs):
    """
    process a zone option
    """
    zone_options = ('use_apex_ns', 'edit_lock', 'auto_dnssec', 'nsec3',
                    'inc_updates',
                    'no_use_apex_ns', 'no_edit_lock', 'no_auto_dnssec',
                        'no_nsec3', 'no_inc_updates',
                    'def_use_apex_ns', 'def_edit_lock', 'def_auto_dnssec',
                        'def_nsec3', 'def_inc_updates')
    if (zone_option.lower() not in zone_options): 
        print (error_msg_wrapper.fill("Can only take one of: %s." 
                    % str(zone_options)), file=_stdout)
        return None
    if zone_option.startswith('no_'):
        return {zone_option[3:]: False}
    elif zone_option.startswith('def_'):
        key = zone_option[4:]
        default = engine.get_config_default(key)
        return {key: default}
    else:
        return {zone_option: True}

def arg_boolean(value, **kwargs):
    """
    Deal with on/off/true/false/0/1
    """
    table = {'on': True, 'off': False, 'true': True, 'false': False, '1': True,
            '0': False, 'yes': True, 'no': False}
    try:
        return {'value': table[value.lower()]}
    except KeyError:
        print (error_msg_wrapper.fill("<boolean> can only be one of: on, off, true, false, 1, 0, yes, no."), 
                file=_stdout)
        return None

def arg_config_dir(config_dir, **kwargs):
    """
    Deal with a directory name
    """
    if config_dir.lower()  in ('none', 'default'):
        return {'config_dir': None}
    if not config_dir.startswith('/'):
        print (error_msg_wrapper.fill("<config_dir> '%s' must start with '/'." 
                    % config_dir),
                file=_stdout)
        return None
    if len(config_dir) > 1024:
        print (error_msg_wrapper.fill(
            "<config_dir> must less than 1025 characters long."), file=_stdout)
        return None
    return {'config_dir': config_dir}

def arg_file_name(file_name, **kwargs):
    """
    Deal with a file name
    """
    return {'file_name': file_name}

def arg_zone_ttl(zone_ttl, **kwargs):
    """
    Handle a zone_ttl argument
    """
    if len(zone_ttl) > 20:
        print(ERROR_PREFIX + "<zone-ttl> is %s long, must be <= 20." 
                % len(zone_ttl), file=_stdout)
        return None
    if not re.match('^[0-9wdhms]+$', zone_ttl):
        print(ERROR_PREFIX 
                + "<zone-ttl> can only contain characters '0-9wdhms'",
            file=_stdout)
        return None
    try:
        dns.ttl.from_text(zone_ttl)
    except dns.ttl.BadTTL as exc:
        print(error_msg_wrapper.fill("<zone-ttl> - %s" % str(exc)),
                file=_stdout) 
        return None
    return {'zone_ttl': zone_ttl}

def arg_config_key(key, **kwargs):
    """
    Deal with set_config keys
    """
    global config_keys
    if key not in config_keys:
        cfg_list = ', '.join(config_keys)
        print (error_msg_wrapper.fill("Key '%s' must be one of %s'." 
                    % (key, cfg_list)),
                file=_stdout)
        return None
    return {'config_key': key}

def arg_config_value(value, **kwargs):
    """
    Check out a value
    """
    global _config_keys
    args = kwargs['args']
    index = kwargs['index']
    # Check previous argument
    if args[index-1] not in config_keys:
        raise Exception("Something really is wrong here!")
    prev_arg = args[index-1].lower()
    if prev_arg in ('use_apex_ns', 'edit_lock', 'auto_dnssec', 'nsec3', 
                    'inc_updates'):
        result = arg_boolean(value)
        if not result:
            return None
        return result
    if prev_arg in ('default_sg',):
        result = arg_sg_name(value)
        if not result:
            return None
        return {'value': result['sg_name']}
    if prev_arg in ('default_ref',):
        result = arg_reference(value)
        if not result:
            return None
        return {'value': result['reference']}
    if prev_arg in ('default_stype',):
        result = arg_server_type(value)
        if not result:
            return None
        return {'value': result['server_type']}
    if prev_arg in ('soa_mname', 'soa_rname'):
        result = arg_domain_name_text(value)
        if not result:
            return None
        return {'value': result['name']}
    if prev_arg in ('zi_max_age', 'zone_del_age', 'zone_del_pare_age',
                    'event_max_age', 'syslog_max_age'):
        result = arg_age_days(value)
        if not result:
            return None
        return {'value': result['age_days']}
    if prev_arg in ('zi_max_num',):
        result = arg_zi_max_num(value)
        if not result:
            return None
        return {'value': result['zi_max_num']}
    if len(value) > 20:
        print(ERROR_PREFIX + "<ttl-value> is %s long, must be <= 20." 
                % len(value), file=_stdout)
        return None
    if not re.match('^[0-9wdhms]+$', value):
        print(ERROR_PREFIX 
                + "<ttl-value> can only contain characters '0-9wdhms'",
            file=_stdout)
        return None
    return {'value': value}

def arg_server_type(server_type, **kwargs):
    """
    Process <server-type> argument
    """
    global server_types
    if server_type not in server_types:
        cfg_list = ', '.join(server_types)
        print (error_msg_wrapper.fill("<server-type> '%s' must be one of %s'." 
                    % (server_type, cfg_list)),
                file=_stdout)
        return None
    return {'server_type': server_type}

def arg_address(address, **kwargs):
    """
    Process an <address> argument
    """
    address = address.strip()
    address_type = None
    try:
        address.index(':')
        address_type = socket.AF_INET6
    except ValueError:
        pass
    try:
        address.index('.')
        address_type = socket.AF_INET
    except ValueError:
        pass
    if not address_type:
        print(ERROR_PREFIX 
                + "<address> can only be a valid IPv4 or IPv6 address.",
                file=_stdout)
        return None
    try:
        socket.inet_pton(address_type, address)
    except socket.error:
        print(ERROR_PREFIX 
                + "<address> can only be a valid IPv4 or IPv6 address.",
                file=_stdout)
        return None
    return {'address': address}

def arg_address_none(address, **kwargs):
    """
    Process an addess argument that can also take the 'none' or 'default' 
    keywords, and return None
    """
    if (address.lower() == 'none'
            or address.lower() == 'def'
            or address.lower() == 'default'):
        return {'address': None}
    return arg_address(address, **kwargs)

def arg_alt_address_none(alt_address, **kwargs):
    """
    Process an alt-addess argument that can also take the 'none' or 
    'default' keywords, are return None
    """
    result = arg_address_none(alt_address, **kwargs)
    if not result:
        return None
    return {'alt_address': result['address']}

def arg_ssh_address_none(ssh_address, **kwargs):
    """
    Process an ssh_address argument that can also take the 'none' 
    keyword, and return None
    """
    if (ssh_address.lower() == 'none'):
        return {'ssh_address': None}
    result = arg_address(ssh_address, **kwargs)
    if not result:
        return None
    return {'ssh_address': result['address']}


def arg_server_name(server_name, **kwargs):
    """
    Process a <server-name>
    """
    if not re.match(r'^[\-\._a-zA-Z0-9]+$', server_name):
        print(ERROR_PREFIX + "<server-name> can only contain characters '.-_a-zA-Z0-9'", file=_stdout)
        return None
    if not re.match(r'^[0-9A-Za-z][\-\._a-zA-Z0-9]*$', server_name):
        print(ERROR_PREFIX + "<server-name> must start with 'a-zA-Z0-9'", file=_stdout)
        return None
    if len(server_name) > 255:
        print(ERROR_PREFIX + "<server-name> is %s long, must be <= 255." 
                % len(server_name), file=_stdout)
        return None
    return {'server_name': server_name}

def arg_new_server_name(new_server_name, **kwargs):
    """
    Process a <new-server-name>
    """
    if not re.match(r'^[\-\._a-zA-Z0-9]+$', new_server_name):
        print(ERROR_PREFIX + "<new-server-name> can only contain characters '.-_a-zA-Z0-9'", file=_stdout)
        return None
    if not re.match(r'^[0-9A-Za-z][\-\._a-zA-Z0-9]*$', new_server_name):
        print(ERROR_PREFIX + "<new-server-name> must start with 'a-zA-Z0-9'", file=_stdout)
        return None
    if len(new_server_name) > 255:
        print(ERROR_PREFIX + "<new-server-name> is %s long, must be <= 255." 
                % len(new_server_name), file=_stdout)
        return None
    return {'new_server_name': new_server_name}

def arg_sg_name(sg_name, **kwargs):
    """
    Process an <sg-name>
    """
    if not re.match(r'^[\-_a-zA-Z0-9]+$', sg_name):
        print(ERROR_PREFIX + "<sg-name> can only contain characters '-_a-zA-Z0-9'", file=_stdout)
        return None
    if not re.match(r'^[0-9a-zA-Z][\-_a-zA-Z0-9]*$', sg_name):
        print(ERROR_PREFIX + "<sg-name> must start with 'a-zA-Z0-9'", file=_stdout)
        return None
    if len(sg_name) > 32:
        print(ERROR_PREFIX + "<sg-name> is %s long, must be <= 32." 
                % len(sg_name), file=_stdout)
        return None
    return {'sg_name': sg_name}

def arg_sg_name_none(sg_name, **kwargs):
    """
    Process an sg_name argument that can also take the 'none', 'no
    keywords, and return None
    """
    if (sg_name.lower() in ('none', 'no', 'off', 'false')):
        return {'sg_name': None}
    return arg_sg_name(sg_name, **kwargs)

def arg_new_sg_name(new_sg_name, **kwargs):
    """
    Process a new_sg_name argument
    """
    result =  arg_sg_name(new_sg_name, **kwargs)
    if not result:
        return None
    return {'new_sg_name': result['sg_name']}

def arg_reference(reference, **kwargs):
    """
    Process a <reference>
    """
    if not re.match(r'^[\-_a-zA-Z0-9.@]+$', reference):
        print(ERROR_PREFIX + "<reference> can only contain characters '-_a-zA-Z0-9.@'", file=_stdout)
        return None
    if not re.match(r'^[0-9a-zA-Z][\-_a-zA-Z0-9.@]*$', reference):
        print(ERROR_PREFIX + "<reference> must start with 'a-zA-Z0-9'",
                file=_stdout)
        return None
    if len(reference) > 1024:
        print(ERROR_PREFIX + "<reference> is %s long, must be <= 1024." 
                % len(reference), file=_stdout)
        return None
    return {'reference': reference}

def arg_dst_reference(dst_reference, **kwargs):
    """
    Process a dst_reference
    """
    result = arg_reference(dst_reference, **kwargs)
    if not result:
        return None
    return {'dst_reference': result['reference']}

def arg_age_days(age_days, **kwargs):
    """
    Process a <age-days>
    """
    try:
        age_days = float(age_days)
    except ValueError:
        print(ERROR_PREFIX + "<age-days> can only be a float.", 
                file=_stdout)
        return None
    if age_days < 0:
        print(ERROR_PREFIX + "<age-days> cannot be less than 0.", file=_stdout)
        return None
    return {'age_days': age_days}

def arg_soa_serial(soa_serial, **kwargs):
    """
    Process a <soa-serial>.

    Range checking done further in.
    """
    try:
        soa_serial = int(soa_serial)
    except ValueError:
        print(ERROR_PREFIX + "<soa_serial> can only be an integer.", 
                file=_stdout)
        return None
    return {'soa_serial': soa_serial}

def arg_zi_max_num(zi_max_num, **kwargs):
    """
    Process a <zi-max-num>
    """
    try:
        zi_max_num = int(zi_max_num)
    except ValueError:
        print(ERROR_PREFIX + "<zi-max-num> can only contain digits.",
                file=_stdout)
        return None
    if zi_max_num < 1:
        print(ERROR_PREFIX + "<zi-max-num> cannot be less than 1.", 
                file=_stdout)
        return None
    return {'zi_max_num': zi_max_num}

def arg_hmac_type(hmac_type, **kwargs):
    """
    Process an HMAC name
    """
    if hmac_type not in tsig_key_algorithms:
        hmac_list = ', '.join(tsig_key_algorithms)
        print (error_msg_wrapper.fill("HMAC '%s' must be one of %s'." 
                    % (hmac_type, hmac_list)),
                file=_stdout)
        return None
    return {'hmac_type': hmac_type}

def arg_no_rndc(no_rndc, **kwargs):
    """
    Process a no_rndc argument
    """
    result = True
    if no_rndc.lower() != 'no_rndc':
        result = False
    return {'no_rndc': result}

# Arguments processed by cmdline handler 
# set these up same as commandline args below which set settings keys 
short_args = "aofg:ijn:pr:tuvz:"
long_args = ["force", "use-origin-as-name", "server-group=", "sg=", 
        "reference=", "ref=", "verbose", "show-all", "show-active", "zone=",
        "domain=", "zi=", "replica-sg", "inc-updates", "oping-servers",
        'soa-serial-update']

def parse_getopt(args):
    """
    Parse command line arguments and remove from list.
    """
    global switch_dict
    try:
        opts, args_left = gnu_getopt(args, short_args, long_args)
    except GetoptError:
        raise DoHelp()
   
    switch_dict = {}
    # Process options
    for o, a in opts:
        if o in ('-f', '--force'):
            switch_dict['force_cmd'] = True
        elif o in ('-a', '--show-all'):
            switch_dict['show_all'] = True 
        elif o in ('-t', '--show-active'):
            switch_dict['show_active'] = True 
        elif o in ('-g', '--server-group', '--sg'):
            result = arg_sg_name(a)
            if not result:
                raise DoNothing()
            switch_dict.update(result)
        elif o in ('-p', '--replica-sg'):
            switch_dict['replica_sg_flag'] = True 
        elif o in ('-i', '--inc-updates'):
            switch_dict['inc_updates_flag'] = True 
        elif o in ('-j', '--oping-servers'):
            switch_dict['oping_servers_flag'] = True 
        elif o in ('-o', '--use-origin-as-name'):
            switch_dict['use_origin_as_name'] = True
        elif o in ('-v', '--verbose'):
            switch_dict['verbose'] = True
        elif o in ('-u', '--soa-serial-update'):
            switch_dict['force_soa_serial_update'] = True
        elif o in ('-r', '--reference', '--ref'):
            result = arg_reference(a)
            if not result:
                raise DoNothing()
            switch_dict.update(result)
        elif o in ('-n', '--zone', '--domain'):
            result = arg_domain_name(a)
            if not result:
                raise DoNothing()
            switch_dict.update(result)
        elif o in ('-z', '--zi'):
            result = arg_zi_id(a)
            if not result:
                raise DoNothing()
            switch_dict.update(result)
        else:
            raise DoHelp()
    return args_left

def parse_line(syntax_list, line):
    """
    Parse the line, and return a tuple/dict of results, or None
    """
    args = ln2strs(line)
    # Parse command line arguments here
    args = parse_getopt(args)
    # Exit it called from do_ls
    if not syntax_list:
        return args
    # Do line length syntax match
    syntax_match = [x for x in syntax_list if len(x) == len(args)]
    if not syntax_match:
        raise DoHelp()
    syntax = syntax_match[0]
    arg_dict = {}
    for i in range(len(args)):
        arg = syntax[i](args[i], index=i, args=args)
        if (not arg):
            raise DoNothing()
        arg_dict.update(arg)
    return arg_dict

class ZoneToolCmd(cmd.Cmd, SystemEditorPager):
    """
    Command processor environment for zone_tool
    """
    intro = ("\nWelcome to the Domain Name Administration Service.\n\n"  
            "Type help or ? to list commands.\n")
    prompt = '%s > ' % settings['process_name']
    indent = OUTPUT_INDENT
    error_prefix = ERROR_PREFIX

    def __init__(self, *args, **kwargs):
        global _stdout
        super().__init__(*args, **kwargs)
        self.exit_code = os.EX_OK
        _stdout = self.stdout 
        self._get_login_id()
        self._init_cmds_not_to_syslog_list()
        self._open_syslog()
        # Initialise self.admin_mode
        self._init_restricted_commands_list()
        self.check_if_admin()
        # Initialise self.wsgi_test_mode
        self._init_wsgi_test_commands_list()
        self.wsgi_api_test_mode = False
        # Set editor if in restricted shell mode.  Bit messy doing via
        # process_name, but it works
        if not self.admin_mode and settings['editor_flag']:
            settings['editor'] = settings['editor_' + settings['editor_flag']]

    def _get_login_id(self):
        """
        Get the login_id string
        """
        try:
            username = pwd.getpwuid(os.getuid()).pw_name
            hostname = socket.getfqdn()
            self.login_id = username + '@' + hostname
        except (OSError, IOError) as exc:
            self.exit_code = os.EX_OSERROR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            sys.exit(self.exit_code)
            
    def _open_syslog(self):
        """
        Open syslog for successful command logging

        This is used for logging successful zone_tool command execution for
        auditing.  Did not use magcode.core.logging as it would spray a lot
        of extra log messages that are not needed in an interactive session.
        """
        log_facility = settings['zone_tool_log_facility'].upper()
        if log_facility not in ('AUTH', 'AUTHPRIV', 'CRON', 'DAEMON', 'FTP',
                'KERN', 'LOCAL0', 'LOCAL1', 'LOCAL2', 'LOCAL3', 'LOCAL4', 
                'LOCAL5', 'LOCAL6', 'LOCAL7', 'LPR', 'MAIL', 'NEWS', 'SYSLOG',
                'USER', 'UUCP'):
            msg = "Incorrect zone_tool_log_facility '%s'" % log_facility
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            sys.exit(os.EX_CONFIG)
        log_facility = eval('syslog.LOG_' + log_facility)
        log_priority = settings['zone_tool_log_level'].upper()
        if log_priority not in ('EMERG', 'ALERT', 'CRIT', 'ERR', 'WARNING', 
                'NOTICE', 'INFO', 'DEBUG'):
            msg = "Incorrect zone_tool_log_level '%s'" % log_priority
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            sys.exit(os.EX_CONFIG)
        self._log_priority = eval('syslog.LOG_' + log_priority)
        syslog.openlog(ident=settings['process_name'], facility=log_facility)

    def _init_cmds_not_to_syslog_list(self):
        """
        Load commands list from settings
        """
        self._cmds_not_to_syslog = [ c.lower() 
                    for c in settings['commands_not_to_syslog'].split()]

    # Trap DB running in hot standby mode
    def onecmd(self, line):
        """
        Calls Cmd.onecmd(self, line)

        Method traps PostgresQL running in replication mode
        """
        # Double nested EXC so that standard exception processing
        # happens for PostgresQL in Read Only hot-standby.  This is lowest
        # common point where this can be trapped properly, code is here
        # for similarity to WSGI code in dms/dms_engine.py
        try:
            try:
                result = super().onecmd(line)
            except sqlalchemy.exc.InternalError as exc:
                raise DBReadOnlyError(str(exc))
        except DBReadOnlyError as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return None
        # Log that a command was executed
        cmd = line.strip().split()
        if not cmd:
            return result
        cmd_verb = cmd[0].lower()
        action_verb = cmd_verb.split('_')[0]
        if action_verb.startswith('ls'):
            action_verb = 'ls'
        # Don't log information commands
        if (action_verb in self._cmds_not_to_syslog):
            return result
        # Only log real commands
        if not hasattr(self, 'do_' + cmd_verb):
            return result
        if self.exit_code == os.EX_OK:
            login_id = self.login_id
            msg = "%s executed command '%s'" % (login_id, line)
            syslog.syslog(self._log_priority, msg)
        return result

    # Do restricted mode
    def get_names(self):
        if self.wsgi_api_test_mode:
            return dir(self.__class__)
        if hasattr(self, '_new_dir'):
            return self._new_dir
        if self.admin_mode:
            self._new_dir = [attr for attr in dir(self.__class__) 
                                if attr not in self._wsgi_test_cmds]
        else:
            self._new_dir = [attr for attr in self.__dict__ 
                            if not attr.startswith('do_')]
            self._new_dir += self._restricted_cmds
        return self._new_dir

    def __getattribute__(self, attr):
        if not attr.startswith('do_'):
            # get on with it ASAP
            return object.__getattribute__(self, attr)
        if self.wsgi_api_test_mode:
            # get on with it ASAP
            return object.__getattribute__(self, attr)
        if self.admin_mode:
            if attr in object.__getattribute__(self, '_wsgi_test_cmds'):
                raise AttributeError("'%s' object has no attribute '%s'"
                        % (object.__getattribute__(self, '__class__').__name__,
                                    attr))
            return object.__getattribute__(self, attr)
        if attr not in object.__getattribute__(self, '_restricted_cmds'):
            raise AttributeError("'%s' object has no attribute '%s'"
                        % (object.__getattribute__(self, '__class__').__name__,
                                    attr))
        return object.__getattribute__(self, attr)


    def _init_restricted_commands_list(self):
        """
        Load restricted commands list from settings
        """
        self._restricted_cmds = [ 'do_' + c 
                    for c in settings['restricted_mode_commands'].split()]

    def _init_wsgi_test_commands_list(self):
        """
        Load WSGI Test commands list from settings
        """
        self._wsgi_test_cmds = [ 'do_' + c 
                    for c in settings['wsgi_test_commands'].split()]

    def init_wsgi_apt_test_mode(self):
        """
        Turn this mode on if requested at command line, and if
        in admin_mode
        """
        if self.admin_mode:
            self.wsgi_api_test_mode = settings['wsgi_api_test_flag']

    def check_or_force(self):
        if not switch_dict.get('force_cmd') and not settings['force_cmd']:
            print(self.error_prefix + "Do really you wish to do this?",
                    file=self.stdout)
            answer = ''
            while not answer:
                answer = input('\t--y/[N]> ')
                if answer in ('n', 'N', ''):
                    return False
                elif answer in ('y', 'Y'):
                    return True
                answer = ''
                continue
        return True

    def check_if_root(self):
        """
        Check that we are running as root, if not exit with message.
        """

        # check that we are root for file writing permissions stuff
        if (os.geteuid() != 0 ):
            self.exit_code = os.EX_NOPERM
            msg = "Only root can execute this command"
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return False
        return True 

    def fillin_sg_name(self, arg_dict, fillin_required=True):
        """
        Fill in sg parameter when needed.
        """
        global switch_dict
        if switch_dict.get('sg_name'):
            arg_dict['sg_name'] = switch_dict.get('sg_name')
            return
        # If it is already given via command line, return
        if arg_dict.get('sg_name'):
            return
        if settings['default_sg']:
            arg_dict['sg_name'] = settings['default_sg']
            return
        if fillin_required:
            arg_dict['sg_name'] = zone_cfg.get_row_exc(db_session,
                                                    'default_sg')

    def get_use_origin_as_name(self):
        """
        Determine use_origin_as_name 
        """
        global switch_dict
        if switch_dict.get('use_origin_as_name'):
            return switch_dict['use_origin_as_name']
        if settings.get('use_origin_as_name'):
            return settings['use_origin_as_name']
        return False

    def get_replica_sg(self):
        """
        Determine replica_sg 
        """
        global switch_dict
        if switch_dict.get('replica_sg_flag'):
            return switch_dict['replica_sg_flag']
        if settings.get('replica_sg_flag'):
            return settings['replica_sg_flag']
        return False

    def get_inc_updates(self):
        """
        Determine inc_updates flag 
        """
        global switch_dict
        if switch_dict.get('inc_updates_flag'):
            return switch_dict['inc_updates_flag']
        if settings.get('inc_updates_flag'):
            return settings['inc_updates_flag']
        return False

    def get_verbose(self):
        """
        Determine verbose output or not
        """
        global switch_dict
        if switch_dict.get('verbose'):
            return switch_dict['verbose']
        if settings.get('verbose'):
            return settings['verbose']
        return False

    def get_oping_servers(self):
        """
        Determine whether to do oping servers or not
        """
        global switch_dict
        if switch_dict.get('oping_servers_flag'):
            return switch_dict['oping_servers_flag']
        if settings.get('oping_servers_flag'):
            return settings['oping_servers_flag']
        return False

    def fillin_reference(self, arg_dict, fillin_required=False):
        """
        Fill in reference parameter when needed
        """
        global switch_dict
        if switch_dict.get('reference'):
            arg_dict['reference'] = switch_dict.get('reference')
            return
        # If it is already given via command line, return
        if arg_dict.get('reference'):
            return
        if settings['reference']:
            arg_dict['reference'] = settings['reference']
            return

    def fillin_domain_name(self, arg_dict, fillin_required=False):
        """
        Fill in name parameter when needed
        """
        global switch_dict
        if switch_dict.get('name'):
            arg_dict['name'] = switch_dict.get('name')
            return
        # If it is already given via command line, return
        if arg_dict.get('name'):
            return
        if settings['zone_name']:
            arg_dict['name'] = settings['zone_name']
            return

    def fillin_show_all(self, arg_dict, fillin_required=False):
        """
        Fill in show_all parameter when needed
        """
        global switch_dict
        if switch_dict.get('show_all'):
            arg_dict['show_all'] = switch_dict.get('show_all')
            return
        # If it is already given via command line, return
        if arg_dict.get('show_all'):
            return
        if settings['show_all']:
            arg_dict['show_all'] = settings['show_all']
            return

    def fillin_show_active(self, arg_dict, fillin_required=False):
        """
        Fill in show_active parameter when needed
        """
        global switch_dict
        if switch_dict.get('show_active'):
            arg_dict['show_active'] = switch_dict.get('show_active')
            return
        # If it is already given via command line, return
        if arg_dict.get('show_active'):
            return
        if settings['show_active']:
            arg_dict['show_active'] = settings['show_active']
            return

    def fillin_force_soa_serial_update(self, arg_dict, fillin_required=False):
        """
        Fill in force_soa_serial_update parameter when needed
        """
        global switch_dict
        if switch_dict.get('force_soa_serial_update'):
            arg_dict['force_soa_serial_update'] = switch_dict.get(
                                                    'force_soa_serial_update')
            return
        # If it is already given via command line, return
        if arg_dict.get('force_soa_serial_update'):
            return
        if settings['force_soa_serial_update']:
            arg_dict['force_soa_serial_update'] \
                                        = settings['force_soa_serial_update']
            return

    def fillin_replica_sg(self, arg_dict, fillin_required=False):
        """
        Fill in replica_sg parameter when needed
        """
        global switch_dict
        if switch_dict.get('replica_sg_flag'):
            arg_dict['replica_sg'] = switch_dict.get('replica_sg_flag')
            return
        # If it is already given via command line, return
        if 'replica_sg' in arg_dict:
            return
        if settings['replica_sg_flag']:
            arg_dict['replica_sg'] = settings['replica_sg_flag']
            return

    def fillin_inc_updates(self, arg_dict, fillin_required=False):
        """
        Fill in inc_updates parameter when needed
        """
        global switch_dict
        if switch_dict.get('inc_updates_flag'):
            arg_dict['inc_updates'] = switch_dict.get('inc_updates_flag')
            return
        # If it is already given via command line, return
        if 'inc_updates' in arg_dict:
            return
        if settings['inc_updates_flag']:
            arg_dict['inc_updates'] = settings['inc_updates_flag']
            return

    def fillin_oping_servers(self, arg_dict, fillin_required=False):
        """
        Fill in oping_servers parameter when needed
        """
        global switch_dict
        if switch_dict.get('oping_servers_flag'):
            arg_dict['oping_servers'] = switch_dict.get('oping_servers_flag')
            return
        # If it is already given via command line, return
        if 'oping_servers' in arg_dict:
            return
        if settings['oping_servers_flag']:
            arg_dict['oping_servers'] = settings['oping_servers_flag']
            return

    def fillin_zi_id(self, arg_dict, fillin_required=False):
        """
        Fill in zi_id parameter when needed
        """
        global switch_dict
        if switch_dict.get('zi_id') is not None:
            arg_dict['zi_id'] = switch_dict.get('zi_id')
            return
        # If it is already given via command line, return
        if arg_dict.get('zi_id'):
            return
        if settings['zi_id']:
            arg_dict['zi_id'] = settings['zi_id']
            return

    def do_exit(self, line):
        "Exit program."
        return True

    do_quit = do_exit
    do_EOF = do_exit
    do_eof = do_exit

    def emptyline(self):
        """
        Override this to prevent repeat execution of last command if enter on
        blank line!
        """
        pass

    def do_help(self, arg, no_pager=False):
        """
        Wrap do_help so that it works properly with pager
        """
        if no_pager:
            super().do_help(arg)
            return
        out_buffer = io.StringIO()
        old_stdout = self.stdout
        self.stdout = out_buffer
        super().do_help(arg)
        self.stdout = old_stdout
        out = out_buffer.getvalue()
        out_buffer.close()
        self.exit_code = self.pager(out)



#    def precmd(self, line):
#        """
#        Turn '-' into '_' on first command verb
#        """
#        split_line = line.split()
#        split_line[0] = split_line[0].replace('-', '_')
#        line = ' '.join(split_line)
#        return line
#
#    def completenames(self, text, *ignored):
#        dotext = 'do_'+text
#        names = [a[3:] for a in self.get_names() if a.startswith(dotext)]
#        print (names)
#        #names2 = [a.replace('-','_') for a in names if a.find('_') > 0]
#        #names = names.extend(names2)
#        return names


    def do_ls(self, line):
        """
        List zones/domains (+ wildcards):
        
        ls [-tv] [-r reference] [-g sg_name] [domain-name] [domain-name] ...

        where:  domain-name     domain name with * or ? wildcards as needed
                reference       reference
                sg_name         server group name
                -t              show active
                -v              verbose output
        """
        try:
            names = parse_line(None, line)
        except DoHelp:
            self.do_help('ls')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        error_on_nothing = True if len(names) else False
        try:
            arg_dict = {}
            self.fillin_reference(arg_dict)
            self.fillin_sg_name(arg_dict, fillin_required=False)
            self.fillin_show_active(arg_dict, fillin_required=False)
            if arg_dict.get('show_active'):
                # Warble the show_active argument
                arg_dict['include_disabled'] = not arg_dict['show_active']
                arg_dict.pop('show_active', None)
            zones = engine.list_zone_admin(names=names, **arg_dict)
        except ZoneSearchPatternError as exc:
            self.exit_code = os.EX_USAGE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except (NoReferenceFound, NoSgFound) as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoZonesFound as exc:
            zones = []
            if (error_on_nothing):
                self.exit_code = os.EX_NOHOST
                msg = "Zones: %s - not present." % exc.data['name_pattern']
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                return
        if self.get_verbose():
            zones = ["%-32s %-12s %-14s%s" % (z['name'], z['soa_serial'], 
                        z['state'],
                        ' ' + z.get('reference') if z.get('reference') else '')
                        for z in zones]
        else:
            zones = [z['name'] for z in zones]
        if zones:
            zones = '\n'.join(zones)
            self.exit_code = self.pager(zones, file=self.stdout)

    do_list_zone = do_ls

    def do_ls_deleted(self, line):
        """
        List deleted zones/domains (+ wildcards):
        
        ls_deleted [-v] [-r reference] [-g sg_name] [domain-name]
                        [domain-name] ...

        where:  domain-name     domain name with * or ? wildcards as needed
                reference       reference
                sg_name         server group name
                -v              verbose output
        """
        try:
            names = parse_line(None, line)
        except DoHelp:
            self.do_help('ls_deleted')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        error_on_nothing = True if len(names) else False
        try:
            arg_dict = {'toggle_deleted': True}
            self.fillin_reference(arg_dict)
            self.fillin_sg_name(arg_dict, fillin_required=False)
            zones = engine.list_zone_admin(names=names, **arg_dict)
        except ZoneSearchPatternError as exc:
            self.exit_code = os.EX_USAGE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except (NoReferenceFound, NoSgFound) as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoZonesFound as exc:
            zones = []
            if (error_on_nothing):
                self.exit_code = os.EX_NOHOST
                msg = "Zones: %s - not present." % exc.data['name_pattern']
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                return
        if self.get_verbose():
            zones = ["%-32s %-12s %-14s%s" 
                    % (z['name'], z['zone_id'], z['deleted_start'],
                        ' ' + z.get('reference') if z.get('reference') else '') 
                    for z in zones]
        else:
            zones = ["%-32s %-12s%s" 
                    % (z['name'], z['zone_id'],
                        ' ' + z.get('reference') if z.get('reference') else '') 
                    for z in zones]
        if zones:
            zones = '\n'.join(zones)
            self.exit_code = self.pager(zones, file=self.stdout)

    do_list_zone_deleted = do_ls_deleted

    def do_ls_zi(self, line):
        """
        List the zone instances for a domain: 
        
        ls_zi [-v] [-z zi_id] <domain-name> [zi-id]

        where:
                -v  show ctime followed by mtime

        Without -v, just ctime is displayed.
        """
        syntax = ((arg_domain_name, arg_zi_id),
                    (arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('ls_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        self.fillin_zi_id(arg_dict)
        try:
            if (arg_dict.get('zi_id')
                    and arg_dict['zi_id'] not in (0, '*', '0')):
                result = engine.list_resolv_zi_id(**arg_dict)
            else:
                arg_dict.pop('zi_id', None)
                result = engine.list_zi(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        zi_s = []
        for zi in reversed(result['all_zis']):
            if self.get_verbose():
                zi_str = '%-19s  %-12s  %s  %s' % (zi['zi_id'], 
                                                zi['soa_serial'], zi['ctime'],
                                                zi['mtime'])
            else:
                zi_str = '%-19s  %-12s  %s' % (zi['zi_id'], zi['soa_serial'], 
                                                zi['ctime'])
            if zi['zi_id'] == result['zi_id']:
                zi_s += ['*' + zi_str]
                continue
            zi_s += [' ' + zi_str]

        zi_s = [self.indent + zi for zi in zi_s]
        if zi_s:
            zi_s = '\n'.join(zi_s)
            self.exit_code = self.pager(zi_s, file=self.stdout)

    do_list_zi = do_ls_zi

    def _show_zonesm(self, zone_sm_dict):
        """
        Given a zone_sm_dict, display it on stdout
        """
        out = []
        out += [ (self.indent + '%-16s' % (str(x) + ':')
                    + ' ' + str(zone_sm_dict[x])) 
                        for x in zone_sm_dict 
                            if (x is not 'zi' and x is not 'all_zis'
                                and x is not 'sectags')]
        name = [ x for x in out if (x.find(' name:') >= 0)][0]
        out.remove(name)
        out.sort()
        out.insert(0, name)
        out = '\n'.join(out)
        return out

    def do_show_zonesm(self, line):
        """
        Show the settings for a zone SM: show_zonesm <domain-name>
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zonesm')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zone(**arg_dict)
        except ZoneNotFound as exc:
            print(self.error_prefix + "Zone '%s' not present." % line,
                    file=self.stdout)
            self.exit_code = os.EX_NOHOST
            return
        if not result:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present." % line,
                    file=self.stdout)
            return
        out = self._show_zonesm(result)
        if result.get('zi'):
            # Only display ZI if it exists
            out += '\n'
            out += '\n'
            out += self._show_zi(result['zi'])
        self.exit_code = self.pager(out, file=self.stdout)

    def do_show_zonesm_byid(self, line):
        """
        Show the settings for a zone SM by id: show_zonesm_byid <zone-id>
        """
        syntax = ((arg_zone_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zonesm_byid')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zone_byid(**arg_dict)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone Instance '%s' not present." % line,
                    file=self.stdout)
            return
        out = self._show_zonesm(result)
        if result.get('zi'):
            out += '\n'
            out += self._show_zi(result['zi'])
        self.exit_code = self.pager(out, file=self.stdout)
    
    def do_show_zone(self, line):
        """
        Show a zone, by default as published: show_zone <domain-name> [zi-id]
        """
        syntax = ((arg_domain_name, arg_zi_id),
                  (arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zone_full(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone/Zone Instance '%s' not present." 
                    % line, file=self.stdout)
            return
        # Stop 'q' in a pager printing exceptions
        try:
            out = data_to_bind(result['zi'], name=result['name'], 
                    reference=result.get('reference'))
        except IOError:
            out = ''
        if out:
            self.exit_code = self.pager(out, file=self.stdout)
        return

    def do_show_zone_byid(self, line):
        """
        Show a zone by zone_id, by default as published: 
            
            show_zone_byid <zone_id> [zi-id]

        """
        syntax = ((arg_zone_id, arg_zi_id),
                  (arg_zone_id,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zone_byid')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zone_byid_full(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        # Stop 'q' in a pager printing exceptions
        try:
            out = data_to_bind(result['zi'], name=result['name'], 
                    reference=result.get('reference'))
        except IOError:
            out = ''
        if out:
            self.exit_code = self.pager(out, file=self.stdout)
        return

    def _show_zi(self, zi_dict):
        """
        Given a zi_dict, display it on stdout
        """
        out = []
        out += [ (self.indent + '%-16s' % (str(x) + ':')
                    + ' ' + str(zi_dict[x])) 
                        for x in zi_dict 
                            if (x is not 'rr_groups'
                                and x is not 'rr_comments')]
        zi_id = [ x for x in out if (x.find('zi_id') >= 0)][0]
        out.remove(zi_id)
        out.sort()
        out.insert(0, zi_id)
        out = '\n'.join(out)
        return out

    def do_show_zi(self, line):
        """
        Show the settings for a ZI: show_zi <domain-name> [zi-id]
        """
        syntax = ((arg_domain_name, arg_zi_id),
                  (arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zi(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        out = self._show_zi(result)
        self.exit_code = self.pager(out, file=self.stdout)
        
    def do_show_zi_byid(self, line):
        """
        Show the settings for a ZI: show_zi <zi-id>
        """
        syntax = ((arg_zi_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zi_byid')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zi_byid(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZiNotFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        out = self._show_zi(result)
        self.exit_code = self.pager(out, file=self.stdout)

    def do_set_config(self, line):
        """
        Set DB Configuration settings: 
        
        set_config [-g sg_name] [sg_name] <key> <value>

        sg_name        sg_name for soa_mname 

        Key can be one of:

        default_sg      Default Server Group
        default_ref     Default reference for created zones

        auto_dnssec     Boolean defaults used during initial zone creation
        edit_lock
        inc_updates
        nsec3
        use_apex_ns

        soa_mname       Used during initial zone creation
        soa_rname
        soa_refresh
        soa_retry
        soa_expire
        soa_minimum
        soa_ttl
        zone_ttl

        event_max_age   Defaults used when vacuuming deleted zones, 
        syslog_max_age  events, syslog messages and old zis.
        zi_max_num
        zi_max_age
        zone_del_age        0 turns off deleted zone aging via vacuum_* 
        zone_del_pare_age   0 turns off zone zi paring to 1 via vacuum_*
        """
        syntax=((arg_sg_name, arg_config_key, arg_config_value),
                (arg_config_key, arg_config_value),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_config')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            if arg_dict.get('config_key') == 'soa_mname':
                # only fill in SG group for soa_mname
                self.fillin_sg_name(arg_dict)
            result = engine.set_config(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except SgNameRequired as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZiParseError as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if result:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + result['message'], file=self.stdout)

    def do_show_config(self, line):
        """
        Display configuration values: show_config
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('show_config')
            return
        result = engine.show_config()
        if not result:
            print(self.error_prefix 
                    + "Error, no configuration returned from DB.",
                    file=self.stdout)

        out = []
        for zone_cfg in result:
            if zone_cfg.get('sg_name'):
                line = (self.indent + '%-18s' % (str(zone_cfg['key']) + ':')
                    + ' ' + str(zone_cfg['value']) + ' (' 
                            + str(zone_cfg['sg_name']) + ')')
            else:
                line = (self.indent + '%-18s' % (str(zone_cfg['key']) + ':')
                    + ' ' + str(zone_cfg['value']))
            out.append(line)
        out.sort()
        out = '\n'.join(out)
        self.exit_code = self.pager(out, file=self.stdout)

    def do_show_apex_ns(self, line):
        """
        Display apex name servers: show_apex_ns [-g sg_name] [sg_name]
        """
        syntax=((arg_sg_name,),
                ())
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_apex_ns')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_sg_name(arg_dict)
            ns_servers = engine.show_apex_ns(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        ns_servers = [self.indent + ns for ns in ns_servers]
        ns_servers = '\n'.join(ns_servers)
        self.exit_code = self.pager(ns_servers, file=self.stdout)

    def do_edit_apex_ns(self, line):
        """
        Edit apex name servers: edit_apex_ns [-g sg_name] [sg_name]
        """
        def clean_up():
            if (tmp_filename):
                os.unlink(tmp_filename)

        syntax=((arg_sg_name,),
                ())
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('edit_apex_ns')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_sg_name(arg_dict)
            ns_servers = engine.show_apex_ns(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneCfgItemNotFound as exc:
            # We need to be able to create entries
            ns_servers= [] 
            pass
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return

        # Write ns_servers to a temporary file
        tmp_filename = ''
        (fd, tmp_filename) = tempfile.mkstemp(prefix=settings['process_name']
                                        + '-', suffix='.apex_ns_servers')
        tmp_file = io.open(fd, mode='wt')
        for ns in ns_servers:
            print(ns, file=tmp_file)
        tmp_file.flush()
        tmp_file.close()
        
        # Edit NS servers list
        old_stat = os.stat(tmp_filename)
        editor = self.get_editor()
        try:
            output = check_call([editor, tmp_filename])
        except CalledProcessError as exc:
            print(self.error_prefix + "Editor exited with '%s'." 
                    % exc.returncode, file=self.stdout)
            self.exit_code = os.EX_SOFTWARE
            return

        # Check that file has definitely been changed.
        new_stat = os.stat(tmp_filename)
        if (old_stat[stat.ST_MTIME] == new_stat[stat.ST_MTIME]
                and old_stat[stat.ST_SIZE] == new_stat[stat.ST_SIZE]
                and old_stat[stat.ST_INO] == new_stat[stat.ST_INO]):
            print(self.error_prefix + "File '%s' unchanged after editing "
                    "- exiting." % tmp_filename, file=self.stdout)
            clean_up()
            self.exit_code = os.EX_OK
            return
 
        # Read in file and set NS servers list
        tmp_file = io.open(tmp_filename, mode='rt')
        ns_servers = tmp_file.readlines()
        tmp_file.close()
        ns_servers = [ ns.strip() for ns in ns_servers ]
        engine.set_apex_ns(ns_servers, sg_name=arg_dict['sg_name'])
        clean_up()
        return

    def do_clear_edit_lock(self, line):
        """
        Clear an edit lock: clear_edit_lock <domain-name> <edit-lock-token>
        """
        syntax = ((arg_domain_name, arg_edit_lock_token),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('clear_edit_lock')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            cancel_results = engine.cancel_edit_zone(**arg_dict)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present."
                    % arg_dict['name'], file=self.stdout)
        except CancelEditLockFailure as exc:
            print(error_msg_wrapper.fill(str(exc)),
                        file=self.stdout)
            self.exit_code = os.EX_UNAVAILABLE
            return
        return

    # For WSGI APT testing
    do_cancel_edit_zone = do_clear_edit_lock

    def do_edit_zone(self, line):
        """
        Edit a zone, by default as published: edit_zone <domain-name> [zi-id]
        """
        def clean_up():
            if (tmp_filename):
                os.unlink(tmp_filename)
            if (orig_filename):
                os.unlink(orig_filename)

        def cancel_edit_zone(name, edit_lock_token):
            # Wrap this thing to contain try carry on as it is used as a
            # clean up routine
            try:
                engine.cancel_edit_zone(name, edit_lock_token)
            except (CancelEditLockFailure, ZoneNotFound):
                return
            return

        def handle_exit_status(status):
            """
            Based on code in subprocess module
            """
            if os.WIFSIGNALED(status):
                return - os.WTERMSIG(status)
            elif os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            else:
                raise RunTimeError("Unknown child exit status!")

        syntax = ((arg_domain_name, arg_zi_id),
                  (arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('edit_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        arg_dict['login_id'] = self.login_id
        try:
            zone_sm_data, edit_lock_token = engine.edit_zone_admin(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print("Zone/Zone Instance '%s' not present." % line, 
                    file=self.stdout)
            return
        except EditLockFailure as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_UNAVAILABLE
            return

        # get domain name for use later on
        name = zone_sm_data['name']
        # Write zone data to a temporary file
        tmp_filename = ''
        orig_filename = ''
        (fd, tmp_filename) = tempfile.mkstemp(prefix=settings['process_name']
                                        + '-', suffix='.zone')
        (orig_fd, orig_filename) = tempfile.mkstemp(
                                    prefix=settings['process_name']
                                        + '-', suffix='.zone.orig')
        tmp_file = io.open(fd, mode='wt')
        orig_file = io.open(orig_fd, mode='wb')
        data_to_bind(zone_sm_data['zi'], name=name, 
                reference=zone_sm_data.get('reference'), file=tmp_file)
        tmp_file.flush()
        tmp_file.close()
        # Write out orig file for diff
        tmp_file = open(tmp_filename, 'rb')
        bstuff = tmp_file.read()
        orig_file.write(bstuff)
        orig_file.flush()
        orig_file.close()

        # Edit Zone 
        parse_flag = False
        old_stat = os.stat(tmp_filename)
        prev_stat = os.stat(tmp_filename)
        cursor_line = None
        cursor_col = None
        msg_wrapper = TextWrapper()
        while not(parse_flag):
            # Edit temp file, have to do our own wait, and every so often
            # see if file changed.
            editor = self.get_editor()
            if cursor_line:
                args = [editor, '+%s' % cursor_line, tmp_filename]
            else:
                args = [editor, tmp_filename]
            sig_stuff = SignalBusiness()
            sig_stuff.register_signal_handler(signal.SIGALRM,
                                    SIGALRMHandler())
            # Set up thirty second itimer to send SIGALRM every 30 seconds
            signal.setitimer(signal.ITIMER_REAL, 30, 30)
            error_str = None
            try:
                process = Popen(args)
            except (IOError,OSError) as exc:
                print (error_msg_wrapper.fill("Running %s failed: %s" 
                        % (exc.filename, exc.strerror)), file=self.stdout)
                self.exit_code = os.EX_SOFTWARE
                return
            status = None
            editlock_timedout = False
            editlock_timedout_msg = None
            while sig_stuff.check_signals():
                try:
                    pid, status = os.waitpid(process.pid, 0)
                except OSError as exc:
                    if exc.errno != errno.EINTR:
                        raise
                if status != None:
                    break
                new_stat = os.stat(tmp_filename)
                if (prev_stat[stat.ST_MTIME] != new_stat[stat.ST_MTIME]
                        or prev_stat[stat.ST_SIZE] != new_stat[stat.ST_SIZE]
                        or prev_stat[stat.ST_INO] != new_stat[stat.ST_INO]):
                    try:
                        engine.tickle_editlock(name, edit_lock_token)
                    except TickleEditLockFailure as exc:
                        editlock_timedout = True
                        editlock_timedout_msg = str(exc)
                        print (self.error_prefix + editlock_timedout_msg,
                            file=self.stdout)
                prev_stat = new_stat
            
            # Disable itimer
            signal.setitimer(signal.ITIMER_REAL, 0)
            sig_stuff.unregister_signal_handler(signal.SIGALRM)
            return_code = handle_exit_status(status)
            if return_code != os.EX_OK:
                print(self.error_prefix + "editor exited with '%s'."
                        % exc.returncode, file=self.stdout)
                if not editlocked_timedout:
                    cancel_edit_zone(name, edit_lock_token)
                self.exit_code = os.EX_SOFTWARE
                return
            if editlock_timedout:
                print (error_msg_wrapper.fill(editlock_timedout_msg),
                        file=self.stdout)
                clean_up()
                self.exit_code = os.EX_TEMPFAIL
                return

            # Check that file has definitely been changed.
            new_stat = os.stat(tmp_filename)
            if (old_stat[stat.ST_MTIME] == new_stat[stat.ST_MTIME]
                    and old_stat[stat.ST_SIZE] == new_stat[stat.ST_SIZE]
                    and old_stat[stat.ST_INO] == new_stat[stat.ST_INO]
                    and not settings['force_cmd']):
                print(self.error_prefix + "File '%s'\n    unchanged after editing - exiting." 
                            % tmp_filename, file=self.stdout)
                cancel_edit_zone(name, edit_lock_token)
                clean_up()
                self.exit_code = os.EX_OK
                return
            
            # Stop, Change, Diff or Accept
            print(self.error_prefix + "Do you wish to Abort, "
                    "Change, Diff, or Update the zone '%s'?" 
                    % name, file=self.stdout)
            answer = ''
            while not answer:
                answer = input('--[U]/a/c/d> ')
                if answer in ('\nUu'):
                    break
                elif answer in ('Aa'):
                    cancel_edit_zone(name, edit_lock_token)
                    clean_up()
                    return
                elif answer in ('Cc'):
                    continue
                elif answer in ('Dd'):
                    # do diff
                    diff_bin = self.get_diff()
                    diff_args = self.get_diff_args()
                    diff_args = [diff_bin] + diff_args.split()
                    diff_args.append(orig_filename)
                    diff_args.append(tmp_filename)
                    tail_bin = self.get_tail()
                    tail_args = self.get_tail_args()
                    tail_argv = [tail_bin] + tail_args.split()
                    # Make sure Less is secure
                    pager_env = os.environ
                    if not self.admin_mode:
                        pager_env.update({'LESSSECURE': '1'})
                    pager_bin = self.get_pager()
                    pager_args = self.get_pager_args()
                    pager_argv = [pager_bin] + pager_args.split()
                    try:
                        p1 = Popen(diff_args, stdout=PIPE)
                        p2 = Popen(tail_argv, stdin=p1.stdout, stdout=PIPE)
                        p3 = Popen(pager_argv, stdin=p2.stdout, env=pager_env)
                        p1.stdout.close() # Allow p1 to receive a SIGPIPE if p2
                                          # exits
                        p2.stdout.close()
                        # Do it
                        output = p3.communicate()
                    except (IOError,OSError) as exc:
                        print (error_msg_wrapper.fill("Running %s failed: %s" 
                                % (exc.filename, exc.strerror)),
                                file=self.stdout)
                        self.exit_code = os.EX_SOFTWARE
                        return
                    # Go back round and query again
                    answer = ''
                    continue
                answer = ''
            else:
                continue

            # Read in zone file and update zone
            try:
                (zi_data, origin_name, update_type, zone_reference) \
                            = bind_to_data(tmp_filename, name)
                result = engine.update_zone_admin(name, zi_data, self.login_id,
                        edit_lock_token)
            except (ParseBaseException, ZoneParseError, ZiParseError,
                    PrivilegeNeeded, ZoneHasNoSOARecord,
                    ZoneSecTagDoesNotExist, SecTagPermissionDenied,
                    SOASerialError) as exc:
                # Must not commit changes to DB when cleaning up!
                engine.rollback()
                if (isinstance(exc, ParseBaseException) 
                    or isinstance(exc, ZoneParseError)):
                    print(exc.markInputline(), file=self.stdout)
                if (isinstance(exc, PrivilegeNeeded)
                    or isinstance(exc, ZoneSecTagDoesNotExist)
                    or isinstance(exc, SecTagPermissionDenied)):
                    msg = "Privilege error - %s" % exc
                elif (isinstance(exc, NoSgFound)
                        or isinstance(exc, ZoneCfgItem)):
                    msg = "Missing DMS config - %s" % exc
                else:
                    msg = "Parse error - %s" % exc
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                print ("Do you want to correct it? ([Y] - continue/n - abort)",
                            file=self.stdout)
                answer = input('--[Y]/n> ')
                if answer in ('\nYy'):
                    if hasattr(exc, 'lineno'):
                        cursor_line = exc.lineno
                        cursor_col = exc.col
                    continue
                else:
                    cancel_edit_zone(name, edit_lock_token)
                    clean_up()
                    self.exit_code = (os.EX_NOPERM 
                                        if isinstance(exc, PrivilegeNeeded)
                                        else os.EX_DATAERR)
                    return
            except LoginIdError as exc:
                print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
                self.exit_code = os.EX_PROTOCOL
                clean_up()
                return
            # Zone SM failures - keep these separate as these are not many
            except UpdateZoneFailure as exc:
                msg = ("Update Error - changes not saved - %s" 
                        % exc)
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_TEMPFAIL
                clean_up()
                return
            except ZoneSmFailure as exc:
                msg = "ZoneSM failure - %s" % exc 
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_PROTOCOL
                clean_up()
                return
            except BinaryFileError as exc:
                msg = str(exc)
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_IOERR
                clean_up()
                return
            else:
                parse_flag = True

        clean_up()
        return

    def do_disable_zone(self, line):
        """
        Disable a zone: disable_zone <domain-name>
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('disable_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.disable_zone(**arg_dict)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present." 
                    % arg_dict['name'], file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_enable_zone(self, line):
        """
        Enable a zone: enable_zone <domain-name>
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('enable_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.enable_zone(**arg_dict)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present." 
                    % arg_dict['name'], file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_create_zone(self, line):
        """
        Create a zone: 
        
        create_zone [-g <sg-name>] [-i] [ -r reference] <domain-name> 
                            [zone-option] ...

        where   -g <sg-name>: specify an SG name other than default_sg
                -i:            set inc_updates flag on the new zone
                -r reference:  set reference
                zone-option:   use_apex_ns|auto_dnssec|edit_lock|nsec3
                                |inc_updates
                                        up to 5 times
        """
        syntax = ((arg_domain_name_net, arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option, arg_zone_option),
                    (arg_domain_name_net, arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option),
                    (arg_domain_name_net, arg_zone_option, arg_zone_option,
                        arg_zone_option),
                    (arg_domain_name_net, arg_zone_option, arg_zone_option),
                    (arg_domain_name_net, arg_zone_option),
                    (arg_domain_name_net,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        self.fillin_sg_name(arg_dict, fillin_required=False)
        self.fillin_reference(arg_dict)
        self.fillin_inc_updates(arg_dict)
        arg_dict['login_id'] = self.login_id
        try:
            create_results = engine.create_zone_admin(**arg_dict)
        except ZoneExists:
            print(self.error_prefix + "Zone '%s' already exists."
                    % arg_dict['name'], file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except (NoSgFound, ZoneCfgItem) as exc:
            msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except InvalidDomainName as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist,
                SecTagPermissionDenied,) as exc:
            engine.rollback()
            msg = "Zone '%s' privilege needed - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        return

    def do_copy_zone(self, line):
        """
        Copy a zone: 
        
        copy_zone [-g <sg-name>] [-i] [ -r reference] [-z zi_id]
                          <src-domain-name> <domain-name> [zone-option] ...

        where   -g <sg-name>: specify an SG name other than default_sg
                -i:            set inc_updates flag on the new zone
                -r reference:  set reference
                -z zi_id:      set zi_id used for copy source
                zone-option:   use_apex_ns|auto_dnssec|edit_lock|nsec3
                                |inc_updates
                                        up to 5 times
        """
        syntax = ((arg_src_domain_name, arg_domain_name_net,
                        arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option, arg_zone_option),
                    (arg_src_domain_name, arg_domain_name_net,
                        arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option),
                    (arg_src_domain_name, arg_domain_name_net, 
                        arg_zone_option, arg_zone_option,
                        arg_zone_option),
                    (arg_src_domain_name, arg_domain_name_net,
                        arg_zone_option, arg_zone_option),
                    (arg_src_domain_name, arg_domain_name_net,
                        arg_zone_option),
                    (arg_src_domain_name, arg_domain_name_net,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('copy_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        self.fillin_sg_name(arg_dict, fillin_required=False)
        self.fillin_reference(arg_dict)
        self.fillin_zi_id(arg_dict)
        self.fillin_inc_updates(arg_dict)
        arg_dict['login_id'] = self.login_id
        try:
            create_results = engine.copy_zone_admin(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except (ZiNotFound, ZoneNotFound) as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except ZoneExists:
            print(self.error_prefix + "Zone '%s' already exists."
                    % arg_dict['name'], file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except (NoSgFound, ZoneCfgItem) as exc:
            msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except InvalidDomainName as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist,
                SecTagPermissionDenied,) as exc:
            engine.rollback()
            msg = "Zone '%s' privilege needed - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        return

    def do_create_zi_zone(self, line):
        """
        Create a zone from a zi: 
        
        create_zi_zone [-g <sg-name>] [-i] [ -r reference]
                          <zi-id> <domain-name>
                          [zone-option] ...

        where   -g <sg-name>: specify an SG name other than default_sg
                -i:            set inc_updates flag on the new zone
                -r reference:  set reference
                zone-option:   use_apex_ns|auto_dnssec|edit_lock|nsec3
                                |inc_updates
                                        up to 5 times
        """
        syntax = ((arg_zi_id, arg_domain_name_net,
                        arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option, arg_zone_option),
                    (arg_zi_id, arg_domain_name_net,
                        arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option),
                    (arg_zi_id, arg_domain_name_net, 
                        arg_zone_option, arg_zone_option,
                        arg_zone_option),
                    (arg_zi_id, arg_domain_name_net,
                        arg_zone_option, arg_zone_option),
                    (arg_zi_id, arg_domain_name_net,
                        arg_zone_option),
                    (arg_zi_id, arg_domain_name_net,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_zi_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        self.fillin_sg_name(arg_dict, fillin_required=False)
        self.fillin_reference(arg_dict)
        self.fillin_inc_updates(arg_dict)
        arg_dict['login_id'] = self.login_id
        try:
            create_results = engine.create_zi_zone_admin(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except (ZiNotFound, ZoneNotFound) as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneExists:
            print(self.error_prefix + "Zone '%s' already exists."
                    % arg_dict['name'], file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except (NoSgFound, ZoneCfgItem) as exc:
            msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except InvalidDomainName as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist,
                SecTagPermissionDenied,) as exc:
            engine.rollback()
            msg = "Zone '%s' privilege needed - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        return

    def do_copy_zi(self, line):
        """
        Copy a zi from a zone to another: 
        
        copy_zi [-z zi_id] <src-domain-name> <domain-name> [zi_id]
        """
        syntax = ((arg_src_domain_name, arg_domain_name, arg_zi_id),
                    (arg_src_domain_name, arg_domain_name),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('copy_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        self.fillin_zi_id(arg_dict)
        arg_dict['login_id'] = self.login_id
        try:
            create_results = engine.copy_zi(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except (ZiNotFound, ZoneNotFound) as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return


    def do_set_zone(self, line):
        """
        Set Zone flags: set_zone <domain-name> <zone-option> [zone-option] ...

        where zone-option can be: use_apex_ns|auto_dnssec|edit_lock
        p to 4 times
        """
        syntax = ((arg_domain_name, arg_zone_option, arg_zone_option,
                        arg_zone_option, arg_zone_option),
                    (arg_domain_name, arg_zone_option, arg_zone_option,
                        arg_zone_option),
                    (arg_domain_name, arg_zone_option, arg_zone_option),
                    (arg_domain_name, arg_zone_option),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.set_zone_admin(**arg_dict)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present." 
                    % arg_dict['name'], file=self.stdout)
            return
        except TypeError as exc:
            self.exit_code = os.EX_USAGE
            print(self.error_prefix + str(exc), file=self.stdout)
        return

    def do_delete_zone(self, line):
        """
        Delete a zone: delete_zone <domain-name>

        Edit locked zones can not be deleted.
        """
        #syntax = ((arg_domain_name, arg_force),)
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            delete_results = engine.delete_zone(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone '%s' not present." 
                    % arg_dict['name'], file=self.stdout)
            return
        except ZoneBeingCreated as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_TEMPFAIL
            return
        return

    def do_undelete_zone(self, line):
        """
        Undelete a zone: undelete_zone <domain-name>

        This can only be done to a disabled or unconfigured zone.
        """
        syntax = ((arg_zone_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            undelete_results = engine.undelete_zone(**arg_dict)
        except ZoneNotFound as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOHOST
            return
        except ActiveZoneExists as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        return

    def do_destroy_zone(self, line):
        """
        Destroy a zone: destroy_zone <zi_id>

        This can only be done to a deleted zone.
        """
        syntax = ((arg_zone_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('destroy_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            destroy_results = engine.destroy_zone(**arg_dict)
        except ZoneNotFoundByZoneId as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOHOST
            return
        except ZoneNotDeleted as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except ZoneSmFailure as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        return

    def do_load_zone(self, line):
        """
        Load a zone : 
        
        load_zone  [-g sg-name] [-i] [-r reference] <file_name> <domain-name> 
                    [zone-option] ...
        
        where   -g <sg-name>: specify an SG name other than default_sg
                -i:            set inc_updates flag on the new zone
                -r reference:  set reference
                zone-option:   use_apex_ns|auto_dnssec|edit_lock|nsec3
                                    |inc_updates
                                        up to 5 times
        """
        syntax = ((arg_file_name, arg_domain_name, arg_zone_option,
                        arg_zone_option, arg_zone_option, arg_zone_option,
                        arg_zone_option),
                    (arg_file_name, arg_domain_name, arg_zone_option,
                        arg_zone_option, arg_zone_option, arg_zone_option),
                    (arg_file_name, arg_domain_name, arg_zone_option,
                        arg_zone_option, arg_zone_option),
                    (arg_file_name, arg_domain_name, arg_zone_option,
                        arg_zone_option),
                    (arg_file_name, arg_domain_name, arg_zone_option),
                    (arg_file_name, arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('load_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_reference(arg_dict)
            self.fillin_sg_name(arg_dict)
            self.fillin_inc_updates(arg_dict)
            file_name = arg_dict.pop('file_name')
            name = arg_dict.get('name')
            arg_dict['zi_data'], origin_name, update_type, zone_reference \
                            = bind_to_data(file_name, name)
            if not arg_dict.get('reference'):
                arg_dict['reference'] = zone_reference
            arg_dict['login_id'] = self.login_id
            load_results = engine.create_zone_admin(**arg_dict)
        except (IOError,OSError) as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_OSERR
            return
        except BinaryFileError as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except (ZoneNameUndefined, BadInitialZoneName,
                InvalidDomainName) as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (ParseBaseException, ZoneParseError, ZoneHasNoSOARecord,
                ZiParseError, SOASerialError) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            if (isinstance(exc, ParseBaseException) 
                or isinstance(exc, ZoneParseError)):
                print(exc.markInputline(), file=self.stdout)
            msg = "Parse error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist, 
                SecTagPermissionDenied) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            msg = "Privilege error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        except (NoSgFound, ZoneCfgItem) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
        # Zone SM failures - keep these separate as these are not many
        except UpdateZoneFailure as exc:
            msg = ("Update Error - changes not saved - %s" 
                    % exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_TEMPFAIL
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return

        except ZoneExists:
            msg = "Zone '%s' already exists."  % arg_dict['name']
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        return
        
    def do_load_zones(self, line):
        """
        Load zones : load_zones [-fi] <file-name> [file-name] ...

        where   -f:            force operation - don't ask yes/no
                -g <sg-name>: specify an SG name other than default_sg
                -i:            set inc_updates flag on the new zone
                -r reference:  set reference

        CAREFUL: If $ORIGIN is not in the files, the basename of the 
                 file-name is used as the domain name
        """
        # Preprocess argument list
        try:
            # This is to pick up commandline switches
            args = parse_line(None, line)
        except DoHelp:
            self.do_help("load_zones")
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if not len(args):
            self.exit_code = os.EX_USAGE
            self.do_help('load_zones')
            return
        # Come up with seed arg_dict
        try:
            seed_arg_dict = {}
            self.fillin_reference(seed_arg_dict)
            self.fillin_sg_name(seed_arg_dict)
            self.fillin_inc_updates(seed_arg_dict)
        except (NoReferenceFound, NoSgFound) as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        # Check through given domains
        try:
            args_list = []
            for arg in args:
                # We are using file names as the domain names  
                # - parse all and apply checks
                arg_pair = arg_file_name(arg)
                if not arg_pair:
                    raise DoNothing()
                name = basename(arg) 
                if not self.get_use_origin_as_name():
                    arg_name = arg_domain_name_text(name)
                    if not arg_name:
                        raise DoNothing()
                else:
                    if not name.endswith('.'):
                        name += '.'
                    arg_name = {'name': name.lower()}
                arg_pair.update(arg_name)
                args_list.append(arg_pair)
        except DoHelp:
            self.do_help('load_zones')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        for arg_pair in args_list:
            try:
                zi_data, name, update_type, zone_reference \
                        = bind_to_data(arg_pair['file_name'], 
                                    arg_pair['name'], 
                                    self.get_use_origin_as_name())
                if name.find('.') < 0:
                    msg = ("%s: zone name must have '.' in it!" 
                            % arg_pair['file_name'])
                    print(error_msg_wrapper.fill(msg), file=self.stdout)
                    self.exit_code = os.EX_DATAERR
                    continue
                arg_dict = seed_arg_dict
                arg_dict.update({'zi_data': zi_data, 'name': name})
                if not seed_arg_dict.get('reference'):
                    arg_dict['reference'] = zone_reference
                arg_dict['login_id'] = self.login_id
                load_results = engine.create_zone_batch(**arg_dict)
            except (ParseBaseException, ZoneParseError,
                ZoneHasNoSOARecord, ZiParseError, SOASerialError) as exc:
                # Must not commit changes to DB when cleaning up!
                engine.rollback()
                if (isinstance(exc, ParseBaseException) 
                    or isinstance(exc, ZoneParseError)):
                    print(exc.markInputline(), file=self.stdout)
                msg = ("Zone file '%s': parse error - %s" 
                        % (arg_pair['file_name'], exc))
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_DATAERR
                continue
            except (PrivilegeNeeded, ZoneSecTagDoesNotExist, 
                SecTagPermissionDenied) as exc:
                # Must not commit changes to DB when cleaning up!
                engine.rollback()
                msg = ("Zone file '%s': privilege error - %s" 
                        % (arg_pair['file_name'], exc))
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_NOPERM
                return
            except (NoSgFound, ZoneCfgItem) as exc:
                # Must not commit changes to DB when cleaning up!
                engine.rollback()
                msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_CANTCREAT
                return
            except LoginIdError as exc:
                print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
                self.exit_code = os.EX_PROTOCOL
                return
            # Zone SM failures - keep these separate as these are not many
            except UpdateZoneFailure as exc:
                msg = ("Zone file '%s': update Error "
                        "- changes not saved - %s" 
                        % (arg_pair['file_name'], exc))
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_TEMPFAIL
                continue
            except ZoneSmFailure as exc:
                msg = ("Zone file '%s': ZoneSM failure - %s" 
                        % (arg_pair['file_name'], exc))
                print (error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_PROTOCOL
                return
            except ZoneExists as exc:
                msg = ("Zone file '%s': zone '%s' already exists."
                        % (arg_pair['file_name'], exc.data['name']))
                print(error_msg_wrapper.fill(msg), file=self.stdout) 
                self.exit_code = os.EX_CANTCREAT
                continue

            except (ZoneNameUndefined, BadInitialZoneName,
                    InvalidDomainName) as exc:
                msg = str(exc)
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_DATAERR
                continue
            except (OSError, IOError) as exc:
                msg = ("Zone file '%s': %s" 
                        % (arg_pair['file_name'], str(exc)))
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_OSERR
                if exc.errno in (errno.ENOENT, errno.EISDIR,
                        errno.EPERM, errno.EACCES):
                    continue
                return
            except BinaryFileError as exc:
                msg = str(exc)
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_IOERR
                continue

            except KeyboardInterrupt:
                self.exit_code = os.EX_TEMPFAIL
                return
        return

    def do_load_zone_zi(self, line):
        """
        Load a zi into a zone : load_zone_zi <file_name> <domain-name> ...
        """
        syntax = ((arg_file_name, arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('load_zone_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return

        try:
            zone_sm_data, edit_lock_token = engine.edit_zone_admin(
                                                        arg_dict['name'],
                                                        login_id=self.login_id)
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print("Zone/Zone Instance '%s' not present." % arg_dict['name'], 
                    file=self.stdout)
            return
        except EditLockFailure as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_UNAVAILABLE
            return

        try:
            file_name = arg_dict.pop('file_name')
            name = arg_dict.get('name')
            arg_dict['zi_data'], origin_name, update_type, zone_reference \
                                = bind_to_data(file_name, name)
            # Use normalize_ttls with imported data to stop surprises
            arg_dict['normalize_ttls'] = True
            arg_dict['login_id'] = self.login_id
            arg_dict['edit_lock_token'] = edit_lock_token
            load_results = engine.update_zone_admin(**arg_dict)
        except (IOError,OSError) as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_OSERR
            return
        except BinaryFileError as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        except (ZoneNameUndefined, BadInitialZoneName, 
                InvalidDomainName) as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return

        except (ParseBaseException, ZoneParseError,
            ZoneHasNoSOARecord, ZiParseError, SOASerialError) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            if (isinstance(exc, ParseBaseException) 
                or isinstance(exc, ZoneParseError)):
                print(exc.markInputline(), file=self.stdout)
            msg = "Parse error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist, 
                SecTagPermissionDenied) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            msg = "Privilege error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        except (NoSgFound, ZoneCfgItem) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            msg = "Zone '%s' can't create - %s" % (arg_dict['name'], exc) 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREAT
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        # Zone SM failures - keep these separate as these are not many
        except UpdateZoneFailure as exc:
            msg = ("Update Error - changes not saved - %s" 
                    % exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_TEMPFAIL
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_delete_zi(self, line):
        """
        Delete a zi: delete_zi <domain-name> <zi_id>

        This can only be done for a zi that is not currently in use .
        """
        syntax = ((arg_domain_name, arg_zi_id),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            results = engine.delete_zi(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone/Zone Instance '%s' not present."
                    % line, file=self.stdout)
            return
        except ZiInUse:
            self.exit_code = os.EX_CANTCREAT
            print(self.error_prefix + "Zone/Zone Instance  '%s' is in use "
                    "- can't delete" % line, file=self.stdout)
            return
        return

    def do_nuke_zones(self, line):
        """
        Nuke zones (+ wildcards) nuke_zones: [domain-name] [domain-name] ....
        """
        try:
            args = parse_line(None, line)
        except DoHelp:
            self.do_help('nuke_zones')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        if not args:
            self.do_help('nuke_zones')
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            arg_dict = {}
            self.fillin_reference(arg_dict)
            self.fillin_sg_name(arg_dict)
            zones = engine.nuke_zones(*args, **arg_dict)
        except (NoReferenceFound, NoSgFound) as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            self.exit_code = os.EX_PROTOCOL
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
        except NoZonesFound as exc:
            self.exit_code = os.EX_NOHOST
            msg = "Zones: %s - not present." % exc.data['name_pattern']
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_show_sectags(self, line):
        """
        Display all security tags: show_sectags
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('show_sectags')
            return
        try:
            result = engine.show_sectags()
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoSecTagsExist as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code  = os.EX_NOHOST
            return
        out = []
        out += [(self.indent + '%-16s' % x['sectag_label'])
                        for x in result]
        out.sort()
        out = '\n'.join(out)
        self.exit_code = self.pager(out, file=self.stdout)

    def do_create_sectag(self, line):
        """
        Create a new security tag: create_sectag <sectag-label>
        """
        syntax = ((arg_sectag_label,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_sectag')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.create_sectag(**arg_dict)
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSecTagExists as exc:
            msg = ("Security tag '%s' already exists." 
                        % exc.data['sectag_label'])
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_OK
        return

    def do_delete_sectag(self, line):
        """
        Delete an unused security tag: delete_sectag <sectag-label>
        """
        syntax = ((arg_sectag_label,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_sectag')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.delete_sectag(**arg_dict)
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSecTagDoesNotExist as exc:
            self.exit_code = os.EX_NOHOST
            msg = ("Security tag '%s' does not exist." 
                        % exc.data['sectag_label'])
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneSecTagStillUsed as exc:
            self.exit_code = os.EX_UNAVAILABLE
            msg = ("Security tag '%s' is still in use." 
                        % exc.data['sectag_label'])
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_show_zone_sectags(self, line):
        """
        Display a zones security tags: show_zone_sectags <domain-name>
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_zone_sectags')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_zone_sectags(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoZoneSecTagsFound as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code  = os.EX_NOHOST
            return
        out = []
        out += [(self.indent + '%-16s' % x['sectag_label'])
                        for x in result]
        out.sort()
        out = '\n'.join(out)
        self.exit_code = self.pager(out, file=self.stdout)

    def do_add_zone_sectag(self, line):
        """
        Add security tag to zone: add_zone_sectag <domain-name> <sectag-label>
        """
        syntax = ((arg_domain_name,arg_sectag_label),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('add_zone_sectag')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.add_zone_sectag(**arg_dict)
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSecTagDoesNotExist as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_delete_zone_sectag(self, line):
        """
        Delete security tag from zone: delete_zone_sectag <domain-name>
                                                          <sectag-label>
        """
        syntax = ((arg_domain_name,arg_sectag_label),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('add_zone_sectag')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.delete_zone_sectag(**arg_dict)
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSecTagDoesNotExist as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return

    def do_replace_zone_sectags(self, line):
        """
        Replace all sectags for a zone: replace_zone_sectags <domain-name>
                                                          <sectag-label> ...
        """
        # Improvise a little here...
        syntax = ((arg_domain_name,),)
        try:
            args = list(ln2strs(line))
            arg_dict = parse_line(syntax, args.pop(0))
            sectag_labels = []
            for arg in args:
                arg = arg_sectag_label(arg)
                if (not arg):
                    raise DoNothing()
                sectag_labels.append(arg)
            arg_dict['sectag_labels']  = sectag_labels
        except DoHelp:
            self.do_help('replace zone_sectags')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return

        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.replace_zone_sectags(**arg_dict)
        except SecTagPermissionDenied  as exc:
            self.exit_code = os.EX_NOPERM
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSecTagDoesNotExist as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return

    def _print_show_mastersm(self, result, verbose=False):
        """
        show_mastersm output.
        """
        if not verbose:
            result.pop('master_server_id', None)
            result.pop('replica_sg_id', None)
            result.pop('master_id', None)
        out = []
        out += [ (self.indent + '%-18s' % (str(x) + ':')
                    + ' ' + str(result[x])) 
                        for x in result ]
        master_server = [ x for x in out if (x.find(' master_server:') >= 0)][0]
        out.remove(master_server)
        out.sort()
        master_server = master_server.replace('master_server', 'MASTER_SERVER')
        master_sm_banner  = self.indent + 'NAMED master configuration state:'
        out.insert(0, '')
        out.insert(1, master_server)
        out.insert(2, '')
        out.insert(3, master_sm_banner)
        out.insert(4, '')
        out.append('')
        out = '\n'.join(out)
        return out

    def do_show_master_status(self, line):
        """
        Show state of master_sm: show_master_status [-v]
        """
        syntax = ((),)
        try:
            args = parse_line(syntax, line)
        except DoHelp:
            self.exit_code = os.EX_USAGE
            self.do_help('show_master_status')
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        verbose = self.get_verbose()
        result = engine.show_mastersm()
        if not result:
            print(self.error_prefix 
                    + "Error, no configuration returned from DB.",
                    file=self.stdout)
        out = self._print_show_mastersm(result, verbose)
        self.exit_code = self.pager(out, file=self.stdout)

    def do_reset_master(self, line):
        """
        Reset master_sm: reset_master

        Only do this if necessary. Resets master_sm to initial state,
        and issues a MasterSMAllReconfig event.
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('reset_master')
            return
        engine.reset_mastersm()

    def do_ls_sg(self, line):
        """
        List all Server Groups: list_sg/lssg/ls_sg

        List all Server Groups
        """
        if line:
            self.exit_code =os.EX_USAGE
            self.do_help('ls_sg')
            return
        result = engine.list_sg()
        out = []
        out += [ self.indent + '%-32s' % str(x['sg_name']) +' ' 
                + '%-4s' % str(x['sg_id']) + ' ' + str(x['config_dir']) 
                    for x in result ]
        out = '\n'.join(out)
        self.exit_code = self.pager(out, file=self.stdout)

    def _print_show_sg(self, result, verbose=False):
        """
        SG display backend
        """
        def format_server(x):
            out_str = (self.indent + '%-28s' % str(x['server_name']) + ' ' 
                    + '%-40s' % str(x['address']) + '\n' 
                    + self.indent + self.indent + str(x['state']))
            if x.get('is_master'):
                out_str += '  (check result on DMS NAMED master server)'
            return out_str

        if not result:
            return '\n'
        servers = result.pop('servers', None)
        if not verbose:
            result.pop('sg_id', None)
        out = []
        out += [ (self.indent + '%-20s' % (str(x) + ':')
                    + ' ' + str(result[x])) for x in result ]
        sg_name = [ x for x in out if (x.find(' sg_name:') >= 0)][0]
        out.remove(sg_name)
        out.sort()
        out.insert(0, sg_name)
        if result.get('replica_sg'):
            server_header = 'Replica SG named status'
        else:
            server_header = 'DNS server status'

        if servers:
            if not verbose:
                servers = [ s for s in servers 
                        if not (s.get('is_master') 
                            and s.get('state') in (SSTATE_OK, SSTATE_CONFIG))]
            out.append('')
            out.append(self.indent + server_header + ':')
            out += [format_server(x)
                        for x in servers ]
        out.append('')
        out = '\n'.join(out)
        return out

    def do_show_sg(self, line):
        """
        Show an SG and its servers: show_sg [-v] <sg-name>

        Display an SG and its servers in brief.
        """
        syntax = ((arg_sg_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        verbose = self.get_verbose()
        try:
            result = engine.show_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        out = self._print_show_sg(result, verbose)
        self.exit_code = self.pager(out, file=self.stdout)
        return

    def do_show_replica_sg(self, line):
        """
        Show any replica SG and its servers: show_replica_sg [-v]

        Display any replica SG and its servers in brief.
        """
        syntax = ((),)
        try:
            args = parse_line(syntax, line)
        except DoHelp:
            self.exit_code = os.EX_USAGE
            self.do_help('show_replica_sg')
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        verbose = self.get_verbose()
        try:
            result = engine.show_replica_sg()
        except NoReplicaSgFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        out = self._print_show_sg(result, verbose)
        self.exit_code = self.pager(out, file=self.stdout)
        return

    def do_create_sg(self, line):
        """
        Create a new SG: 
        
        create_sg [-p] <sg-name> [config-dir] [address] [alt-address]

        where:
                sg-name    SG name
                -p          SG created is the replica SG
                config-dir  SG configuration directory.  If not given
                            defaults to config file value sg_config_dir.
                            If given as 'none' or 'default', same thing.
                address     Master server address for use in filling 
                            in server zone templates
                alt-address Master server address for use in filling 
                            in server zone templates
        """
        syntax = ((arg_sg_name, arg_config_dir, arg_address_none, 
                    arg_alt_address_none),
                (arg_sg_name, arg_config_dir, arg_address_none),
                (arg_sg_name, arg_config_dir),
                (arg_sg_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        arg_dict['replica_sg'] = self.get_replica_sg()
        try:
            result = engine.create_sg(**arg_dict)
        except ReplicaSgExists as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
        except SgExists as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_OK
        except (IOError, OSError) as exc:
            if exc.errno == errno.EOWNERDEAD:
                self.exit_code = os.EX_NOUSER
            else:
                self.exit_code = os.EX_NOPERM
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_delete_sg(self, line):
        """
        Delete an unused SG: delete_sg <sg_name>
        where:
                sg_name    SG name
        """
        syntax = ((arg_sg_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.delete_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except SgStillUsed as exc:
            self.exit_code = os.EX_UNAVAILABLE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_rename_sg(self, line):
        """
        Rename an SG: rename_sg [-f] <sg-name> <new-sg-name>
        where:
                sg_name    SG name
        """
        syntax = ((arg_sg_name, arg_new_sg_name),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('rename_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.rename_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except SgExists as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_UNAVAILABLE
        return

    def do_set_sg_config(self, line):
        """
        Set SG configuration dir: set_sg_config [-f] <sg-name> <config-dir>

        where:
                sg-name    SG name
                config-dir  SG configuration directory.
                            Use 'none' or 'default',  to return to 
                            config file value sg_config_dir.
        """
        syntax = ((arg_sg_name, arg_config_dir),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_sg_config')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.set_sg_config(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except (IOError, OSError) as exc:
            if exc.errno == errno.EOWNERDEAD:
                self.exit_code = os.EX_NOUSER
            else:
                self.exit_code = os.EX_NOPERM
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_set_sg_master_address(self, line):
        """
        Set SG master server address:
        
        set_sg_master_address <sg-name> <address>

        where:
                sg-name    SG name
                address     Master server IP address for use in filling 
                            in server zone templates.
                            Use 'none' or 'default',  to return to 
                            address used for the primary server hostname.
        """
        syntax = ((arg_sg_name, arg_address_none),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_sg_master')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.set_sg_master_address(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_set_sg_master_alt_address(self, line):
        """
        Set SG alternate master server address:
        
        set_sg_master_alt_address <sg-name> <alt-address>

        where:
                sg-name     SG name
                alt-address  Alternate master server IP address for use in
                             filling in server zone templates.
                             Use 'none' or 'default',  to return to 
                             address used for the primary server hostname.
        """
        syntax = ((arg_sg_name, arg_alt_address_none),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_sg_master_alt')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.set_sg_master_alt_address(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_set_sg_replica_sg(self, line):
        """
        Set SG alternate master server address:
        
        set_sg_replica_sg [-f] <sg-name>

        where:
                -f          Force operation     
                sg-name    SG name or None/no
        """
        syntax = ((arg_sg_name_none,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_sg_replica_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.set_sg_replica_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ReplicaSgExists as exc:
            self.exit_code = os.EX_PROTOCOL
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_set_zone_sg(self, line):
        """
        Set the sg for a zone: 
        
        set_zone_sg [-g sg-name] <zone> [sg-name]

        No SG given means to set SG back to default
        """
        syntax = ((arg_domain_name, arg_sg_name),
                    (arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_zone_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_sg_name(arg_dict, fillin_required=False)
            result = engine.set_zone_sg(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotDisabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_CONFIG
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_dupe_zone_alt_sg(self, line):
        """
        Duplicate a zone to an alternate SG, or set it there: 
        
        dupe_zone_alt_sg <zone> <sg-name>

        This is useful if you want to include an external zone on 
        in (for example) a private internal SG group behind a firewall.
        """
        syntax = ((arg_domain_name, arg_sg_name),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('dupe_zone_alt_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.set_zone_alt_sg(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    # For WSGI API test mode
    do_set_zone_alt_sg = do_dupe_zone_alt_sg

    def do_delete_zone_alt_sg(self, line):
        """
        Delete/Clear the alternate sg for a zone: 
        
        delete_zone_alt_sg <zone>

        This removes any alternate SG on a zone.
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_zone_alt_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            arg_dict['sg_name'] = None
            result = engine.set_zone_alt_sg(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_swap_zone_sg(self, line):
        """
        Swap over the SGs for a zone: 
        
        swap_zone_sg [-f] <zone>

        This is part of the process of moving a zone from one SG to another.
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('swap_zone_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.swap_zone_sg(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except (ZoneNoAltSgForSwap, ZoneSmFailure) as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_reconfig_master(self, line):
        """
        Reconfigure master DNS server: reconfig_master

        Reconfigures the master DNS server via 'rndc reconfig'
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('reconfig_master')
            return
        result = engine.reconfig_master()

    def do_reconfig_sg(self, line):
        """
        Reconfigure an SG's DNS servers: reconfig_sg <sg-name>

        Reconfigures an SG's DNS servers via the equivalent of
        'rndc reconfig'
        """
        syntax = ((arg_sg_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('reconfig_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.reconfig_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_reconfig_replica_sg(self, line):
        """
        Reconfigure the Replica SG's DNS servers: 
        
        reconfig_replica_sg

        Rsyncs DNSSEC key material to all DR replicas, and reconfigure all the
        DR replica named processes.
        """
        syntax = ()
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('reconfig_replica_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.reconfig_replica_sg()
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_reconfig_all(self, line):
        """
        Reconfigure all DNS servers: reconfig_all

        Reconfigures the all dns servers via 'rndc reconfig' or
        nearest equivalent, maybe even SIG_HUP for nsd3.
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('reconfig_all')
            return
        result = engine.reconfig_all()

    def do_sign_zone(self, line):
        """
        Sign a zone: sign_zone <domain-name>

        DNSSEC sign a zone via 'rndc sign'
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('sign_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.sign_zone(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotDnssecEnabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_loadkeys_zone(self, line):
        """
        Load keys for a zone: loadkeys_zone <domain-name>

        Load keys for a zone via 'rndc loadkeys'
        """
        syntax = ((arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('loadkeys_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.loadkeys_zone(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotDnssecEnabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_reset_zonesm(self, line):
        """
        Reset state machine for a zone: reset_zone [-f] <domain-name> [zi-id]
        """
        syntax = (  (arg_domain_name, arg_zi_id),
                    (arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('reset_zonesm')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        msg = "WARNING - doing this destroys DNSSEC RRSIG data."
        print(error_msg_wrapper.fill(msg), file=self.stdout)
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.reset_zone(**arg_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_reset_all_zones(self, line):
        """
        Reset all zones: reset_all [-f]

        Resets all zones.  This will rebuild Master bind9 on disk DB.  It is
        a ZoneSM stress test command that only root can run.
        """
        if line:
            self.exit_code = os.EX_USAGE
            self.do_help('reset_all_zones')
            return
        # Check that we are toor so that we can proceed
        if not self.check_if_root():
            return
        # Query user as this may be unadvisable
        msg = ("WARNING - doing this destroys DNSSEC RRSIG data,"
            " and it is mainly a ZoneSM stress testing command.")
        print(error_msg_wrapper.fill(msg), file=self.stdout)
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.reset_all_zones()
        except ZoneNotFoundByZoneId as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return


    def do_refresh_zone(self, line):
        """
        Refresh a zone: refresh_zone/update_zone [-f] <domain-name> [zi_id]

        This is done by queuing a zone update event.
        """
        syntax = (  (arg_domain_name, arg_zi_id),
                    (arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('refresh_zone')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if (arg_dict.get('zi_id') and not self.check_or_force()):
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.refresh_zone(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return
    
    def do_refresh_sg(self, line):
        """
        Refresh an SG's zones: refresh_sg/update_sg [-f] <sg-name>

        Refreshes an SG's by queuing zone update events.
        """
        syntax = ((arg_sg_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('refresh_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.refresh_sg(**arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotFoundByZoneId as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_refresh_all(self, line):
        """
        Refresh all zones: refresh_all/update_all [-f]

        Refreshes all zones by queuing zone update events.
        """
        syntax = ((),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('refresh_all')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.refresh_all()
        except ZoneNotFoundByZoneId as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_ls_reference(self, line):
        """
        List references + wildcards: lsref [reference] [reference] ...
        """
        try:
            args = parse_line(None, line)
        except DoHelp:
            self.do_help('lsref')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        error_on_nothing = True if len(args) else False
        try:
            arg_dict = {}
            self.fillin_reference(arg_dict)
            if arg_dict.get('reference'):
                args.insert(0, arg_dict['reference'])
            ref_list = engine.list_reference(*args)
        except NoReferenceFound as exc:
            ref_list = []
            if (error_on_nothing):
                self.exit_code = os.EX_DATAERR
                msg = "References: %s - not present." % line
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                return
        references = [self.indent + r['reference'] for r in ref_list]
        if references:
            references = '\n'.join(references)
            self.exit_code = self.pager(references, file=self.stdout)

    def do_create_reference(self, line):
        """
        Create a new reference: create_reference <reference>
        """
        syntax = ((arg_reference,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_reference')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.create_reference(**arg_dict)
        except ReferenceExists as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_OK
        return

    def do_delete_reference(self, line):
        """
        Delete an unused reference: delete_reference <reference>
        """
        syntax = ((arg_reference,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_reference')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.delete_reference(**arg_dict)
        except ReferenceDoesNotExist as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ReferenceStillUsed as exc:
            self.exit_code = os.EX_UNAVAILABLE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_rename_reference(self, line):
        """
        rename a reference: rename_reference <reference> <dst-reference>
        """
        syntax = ((arg_reference, arg_dst_reference,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('rename_reference')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.rename_reference(**arg_dict)
        except ReferenceDoesNotExist as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ReferenceExists as exc:
            self.exit_code = os.EX_UNAVAILABLE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        return

    def do_set_zone_reference(self, line):
        """
        Set the reference for a zone: 
        
        set_zone_reference [-r reference] <zone> [reference]
        """
        syntax = ((arg_domain_name,arg_reference),
                    (arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_zone_reference')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_reference(arg_dict)
            result = engine.set_zone_reference(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoReferenceFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_vacuum_event_queue(self, line):
        """
        Clean out processed events
        
        vacuum_event_queue [-fv] [age-days]

        where:
                -f          force operation.  Don't ask yes/no
                -v          verbose output.
                age-days    age in days to be kept.

        Destroy processed events older than age-days if given or 
        event_max_age in the sm_event_queue table. event_max_age is set via
        the set_config command. Use the show_config command to view current
        settings.
        """
        syntax = ((arg_age_days,), ())
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_event_queue')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if len(arg_dict) and not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.vacuum_event_queue(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            msg = "Processed Events destroyed: %s" % result['num_deleted']
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_vacuum_zones(self, line):
        """
        Clean out deleted zones
        
        vacuum_zones [-fv] [age-days]

        where:
                -f          force operation.  Don't ask yes/no
                -v          verbose output.
                age-days    age in days to be kept.

        Destroy deleted zones older than age-days if given, or zone_del_age
        which is set via the set_config command. Use the show_config command
        to view current settings.
        """
        syntax = ((arg_age_days,), ())
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_zones')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if len(arg_dict) and not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.vacuum_zones(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            msg = "Deleted Zones destroyed: %s" % result['num_deleted']
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_vacuum_zis(self, line):
        """
        Clean out old zone instances
        
        vacuum_zis [-fv] [age-days] [zi-max-num]

        where:
                -f          force operation.  Don't ask yes/no
                -v          verbose output.
                age-days    age in days to be kept,
                zi-max-num  till maximum number of zis.

        Destroy deleted zone instances older than zi_max_age, and over
        that keeping up to zi_max_num, both set via the set_config command.
        These defaults can be overridden by giving parameters. Use
        the show_config command to view current settings.
        """
        syntax = ((arg_age_days, arg_zi_max_num),
                  (arg_age_days,),
                  (),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_zis')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if len(arg_dict) and not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.vacuum_zis(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            msg = "Zone Instances destroyed: %s" % result['num_deleted']
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_vacuum_pare_deleted_zone_zis(self, line):
        """
        Pare ZIs off deleted zones 
        
        vacuum_pare_deleted_zone_zis [-fv] [age-days]

        where:
                -f          force operation.  Don't ask yes/no
                -v          verbose output.
                age-days    age in days to be kept.

        Pare ZIs off deleted zone older than age-days if given, 
        or zone_del_pare_age, which is set via the set_config command. Use
        the show_config command to view current settings.
        """
        syntax = ((arg_age_days,),
                  (),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_pare_deleted_zone_zis')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if len(arg_dict) and not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.vacuum_pare_deleted_zone_zis(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            msg = "Zone Instances pared: %s" % result['num_deleted']
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_vacuum_syslog(self, line):
        """
        Clean out syslog messages
        
        vacuum_syslog [-fv] [age-days]

        where:
                -f          force operation.  Don't ask yes/no
                -v          verbose output.
                age-days    age in days to be kept.

        Destroy received syslog messages older than age-days if given, 
        or syslog_max_age which is set via the set_config command. The
        syslog messages are stored in the systemevents table.
        """
        syntax = ((arg_age_days,), ())
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_syslog')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if len(arg_dict) and not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.vacuum_syslog(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            msg = "Syslog messages destroyed: %s" % result['num_deleted']
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def do_vacuum_all(self, line):
        """
        Clean out cruft using default values set in DB
        
        vacuum_all [-v]

        Same as vacuum_event_queue, vacuum_zones, vacuum_pare_deleted_zone_zis
        and vacuum_zis run using defaults in DB config.  Use set_config command
        to set defaults, show_config command to show them.

        Refer to help for the above commands for more details.
        """
        syntax = ((),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('vacuum_all')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result_eq = engine.vacuum_event_queue(**arg_dict)
            result_zones = engine.vacuum_zones(**arg_dict)
            result_zis = engine.vacuum_zis(**arg_dict)
            result_pared_zis = engine.vacuum_pare_deleted_zone_zis(**arg_dict)
            result_syslog = engine.vacuum_syslog(**arg_dict)
        except ZoneCfgItem as exc:
            self.exit_code = os.EX_DATAERR
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        if self.get_verbose():
            total = result_eq['num_deleted'] + result_zones['num_deleted'] \
                    + result_zis['num_deleted'] \
                    + result_pared_zis['num_deleted'] \
                    + result_syslog['num_deleted']
            msg = ("Items destroyed: total %s, zones %s,"
                    " zis pared %s, zis aged %s, events %s, syslog_msgs %s" 
                    % (total, result_zones['num_deleted'],
                        result_pared_zis['num_deleted'],
                        result_zis['num_deleted'],
                        result_eq['num_deleted'],
                        result_syslog['num_deleted']))
            print(result_msg_wrapper.fill(msg), file=self.stdout)
        return

    def _oping_servers(self, server_list):
        """
        OPing a list of servers, and stuff info back into server_list
        """
        error_msg = ''
        output = ''
        try:
            oping_args = settings['oping_args'].split()
            cmdline = [settings['oping_path']]
            cmdline.extend(oping_args)
            s_ips = [(s['address']) 
                        for s in server_list
                            if (s['state'] != SSTATE_DISABLED)]
            cmdline.extend(s_ips)
            output = check_output(cmdline, stderr=STDOUT)
        except CalledProcessError as exc:
            error_msg = (settings['oping_path'] + ': ' 
                                + exc.output.decode(errors='replace').strip())
        except (IOError, OSError) as exc:
            error_msg = exc.strerror
        
        if not error_msg:
            try:
                output = output.decode().split('\n\n',)[1:]
                output = [o.splitlines()[1] for o in output]
                output = [o.rsplit(',',1)[0] for o in output]
                output = [o.strip() for o in output]
            except UnicodeDecodeError as exc:
                error_msg = str(exc)
            except Exception as exc:
                error_msg = str(exc)
        index = 0
        for s in server_list:
            if s['state'] == SSTATE_DISABLED:
                s['ping_results'] = 'server disabled'
                continue
            elif not error_msg:
                s['ping_results'] = output[index]
            else:
                s['ping_results'] = error_msg
            index += 1

        return

    def _print_ls_server(self, server_list, verbose, oping_servers=False):
        """
        Print ls_server output
        """
        if not server_list:
            return '\n'

        if oping_servers:
            self._oping_servers(server_list)
        out = []
        if verbose or oping_servers:
            for s in server_list:
                out += [("%-28s %-39s %s\n" 
                    + self.indent + "%-39s %s")
                        % (s['server_name'], s['last_reply'],
                            s['state'], s['address'], s['ssh_address'])]
                if oping_servers:
                    out += [self.indent + "ping: " + s['ping_results']]
                if s.get('retry_msg'):
                    out += [(self.indent + 'retry_msg:'), 
                            output_msg_wrapper.fill(str(s.get('retry_msg')))]
        else:
            out += [s['server_name'] for s in server_list]
        out.append('')
        out = '\n'.join(out)
        return out
    
    def do_ls_slave(self, line):
        """
        List slave servers + wildcards: 

            ls_slave [-ajtv] [-g sg_name] [server-name] [server-name] ...

        where:
                -a              show all
                -j              do ping test of each server
                -t              show active
                -v              verbose output
                -g sg_name      in server group
                server-name     server name - wildcards accepted
        """
        try:
            args = parse_line(None, line)
        except DoHelp:
            self.do_help('ls_slave')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        error_on_nothing = True if len(args) else False
        try:
            arg_dict = {}
            self.fillin_sg_name(arg_dict, fillin_required=False)
            self.fillin_show_all(arg_dict, fillin_required=False)
            self.fillin_show_active(arg_dict, fillin_required=False)
            # Invert show_all default to False for only listing true slaves
            if not arg_dict.get('show_all'):
                arg_dict['show_all'] = False
            server_list = engine.list_server(*args, **arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoServerFound as exc:
            server_list = []
            if (error_on_nothing):
                self.exit_code = os.EX_DATAERR
                msg = "Server: %s - not present." % line
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                return
        out = self._print_ls_server(server_list, self.get_verbose(), 
                    self.get_oping_servers())
        if out:
            self.exit_code = self.pager(out, file=self.stdout)

    def do_ls_server(self, line):
        """
        List all servers + wildcards: 

            ls_server [-jtv] [-g sg_name] [server-name] [server-name] ...
        
        where:
                -j              do ping test of each server
                -t              show active
                -v              verbose output
                -g sg_name      in server group
                server-name     server name - wildcards accepted
        """
        try:
            args = parse_line(None, line)
        except DoHelp:
            self.do_help('ls_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing: 
            self.exit_code = os.EX_USAGE
            return
        error_on_nothing = True if len(args) else False
        try:
            arg_dict = {}
            self.fillin_sg_name(arg_dict, fillin_required=False)
            self.fillin_show_active(arg_dict, fillin_required=False)
            server_list = engine.list_server(*args, **arg_dict)
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoServerFound as exc:
            server_list = []
            if (error_on_nothing):
                self.exit_code = os.EX_DATAERR
                msg = "Server: %s - not present." % line
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                return
        out = self._print_ls_server(server_list, self.get_verbose(), 
                self.get_oping_servers())
        if out:
            self.exit_code = self.pager(out, file=self.stdout)

    def _show_server(self, server_sm_dict):
        """
        Backend for showing server
        """
        out = []
        out += [ (self.indent + '%-16s' % (str(x) + ':')
                    + ' ' + str(server_sm_dict[x])) 
                        for x in server_sm_dict]
        name = [ x for x in out if (x.find(' server_name:') >= 0)][0]
        out.remove(name)
        retry_msg_list = [ x for x in out if (x.find(' retry_msg:') >= 0)]
        retry_msg = None
        if len(retry_msg_list):
            retry_msg = retry_msg_list[0]
            out.remove(retry_msg)
        out.sort()
        out.insert(0, name)
        if retry_msg:
            retry_msg = retry_msg.split(':', 1)[-1].strip()
            out.append(self.indent + 'retry_msg:')
            out.append(output_msg_wrapper.fill(retry_msg))
        out = '\n'.join(out)
        self.exit_code = self.pager(out, file=self.stdout)
        return

    def do_show_server(self, line):
        """
        Show a server SM: show_server <server-name>

        Display a server.
        """
        syntax = ((arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        self._show_server(result)
        return

    def do_show_server_byaddr(self, line):
        """
        Show a server SM by address: show_server_byaddr <address>

        Display a server by address
        """
        syntax = ((arg_address,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_server_byaddr')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_server_byaddress(**arg_dict)
        except (NoServerFound, NoServerFoundByAddress) as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        self._show_server(result)
        return
    
    def do_create_server(self, line):
        """
        Create a Server SM: 
        
        create_server [-g sg-name] <server-name> <address> [server-type]
                                        [ssh-address]

        where   sg-name         SG group name
                server-name     server name - a human tag
                address         server IP address
                server-type     bind9|nsd3  - the server type
                ssh-address     ssh administration address of server
        """
        syntax = ((arg_server_name, arg_address, arg_server_type, 
                        arg_ssh_address_none),
                    (arg_server_name, arg_address, arg_server_type),
                    (arg_server_name, arg_address),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('create_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_sg_name(arg_dict)
            engine.create_server(**arg_dict)
        except (ServerExists, ServerAddressExists) as exc:
            self.exit_code = os.EX_CANTCREAT
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_delete_server(self, line):
        """
        Delete a server: delete_server [-f] <server-name>

        The server must be disabled before doing this.
        """
        syntax = ((arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('delete_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.delete_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerNotDisabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_set_server_type(self, line):
        """
        Set server type: set_server_type <server-name> <server-type>

        where   server-name     server name - a human tag
                server-type     bind9|nsd3  - the server type

        The server must be disabled before doing this.
        """
        syntax = ((arg_server_name, arg_server_type),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_server_type')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.set_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerNotDisabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_set_server_address(self, line):
        """
        Set server address: set_server_address <server-name> <address>

        where   server-name     server name - a human tag
                address         server address

        The server must be disabled before doing this.
        """
        syntax = ((arg_server_name, arg_address),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_server_address')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.set_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerNotDisabled as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_rename_server(self, line):
        """
        Rename a server: rename_server [-f] <server-name> <new-server-name>

        where   server-name      server name - a human tag
                new-server-name  new server name

        The server must be disabled before doing this.
        """
        syntax = ((arg_server_name, arg_new_server_name),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('rename_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.rename_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_set_server_ssh_address(self, line):
        """
        Set server ssh address: set_server_ssh_address <server-name> <ssh-address>

        where   server-name     server name - a human tag
                ssh-address     server ssh administration address or 'none'
        """
        syntax = ((arg_server_name, arg_ssh_address_none),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('set_server_ssh_address')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.set_server_ssh_address(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_move_server_sg(self, line):
        """
        Move a server between SGs:

        move_server_sg <server-name> <sg-name>

        where   server-name  server name
                sg-name      SG name
        """
        syntax = ((arg_server_name, arg_sg_name),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('move_server_sg')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_sg_name(arg_dict)
            engine.move_server_sg(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except NoSgFound as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_enable_server(self, line):
        """
        Enable a server: enable_server <server-name>
        """
        syntax = ((arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('enable_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.enable_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerSmFailure as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_disable_server(self, line):
        """
        Disable a server: disable_server <server-name>
        """
        syntax = ((arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('disable_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.disable_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerSmFailure as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_reset_server(self, line):
        """
        Reset server SM: reset_server <server-name>
        """
        syntax = ((arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('reset_server')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.reset_server(**arg_dict)
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ServerSmFailure as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_write_rndc_conf(self, line):
        """
        Write out a new rndc.conf: write_rndc_conf

        Must be run as root to get ownership/permissions set correctly.

        Key files in rndc.conf-header must exist!!
        """
        syntax = ()
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('write_rndc_conf')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Check that we are toor so that we can proceed
        if not self.check_if_root():
            return
        try:
            engine.write_rndc_conf()
        except (OSError, IOError) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        except KeyError as exc:
            msg = ("Invalid template key in file in template dir %s - %s"
                    % (settings['config_template_dir'], str(exc)))
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CONFIG
            return
        return

    def do_generate_tsig_key(self, line):
        """
        Generate a new tsig key: 
        
        generate_tsig_key [-f] <key-name> [hmac-type] [file-name]

        Must be run as root if creating a key file to get ownership/permissions
        set correctly.
        """
        syntax = ((arg_key_name, arg_hmac_type, arg_file_name),
                (arg_key_name, arg_hmac_type),
                (arg_key_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('generate_tsig_key')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Check that we are toor so that we can proceed
        if arg_dict['key_name'].endswith('.'):
            arg_dict['key_name'] = arg_dict['key_name'][:-1]
        if arg_dict.get('file_name'):
            if not self.check_if_root():
                return
            if not self.check_or_force():
                self.exit_code = os.EX_TEMPFAIL
                return
        else:
            arg_dict['file_name'] = None
        try:
            engine.generate_tsig_key(**arg_dict)
        except (OSError, IOError) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        except InvalidHmacType as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        return

    def do_rsync_server_admin_config(self, line):
        """
        Rsync administration config files/includes to a replica/slave server:

        rsync_server_admin_config <server-name> [no_rndc]

        Files rsynced depend on the servers type, bind9, nsd3 etc.
        """
        syntax = ((arg_server_name, arg_no_rndc),
                (arg_server_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('rsync_admin_config')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Check that we are toor so that we can proceed
        if not self.check_if_root():
            return
        try:
            engine.rsync_server_admin_config(**arg_dict)
        except CalledProcessError as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = exc.returncode
            return
        except NoServerFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except (OSError, IOError) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        return

    def do_record_query_db(self, line):
        """
        Query the database for a resource record ala libc resolv

        rr_query_db [-av] [-n domain] [-z zi-id] <label> [rr_type] [rdata]
        """
        syntax = ((arg_label, arg_rr_type, arg_rdata),
                  (arg_label, arg_rr_type),
                  (arg_label,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('record_query_db')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_domain_name(arg_dict)
            self.fillin_show_all(arg_dict)
            self.fillin_zi_id(arg_dict)
            results = engine.rr_query_db(**arg_dict)
        except RrQueryDomainError as exc:
            self.exit_code = os.EX_DATAERR
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        if results:
            out = []
            if self.get_verbose():
                zi_id = results.get('zi_id')
                if zi_id == 0:
                    zi_id = '*'
                out += ["%1s label: %-16s domain: %-32s zi_id: %s\n" 
                            % ('X' if results.get('zone_disabled') else ' ',
                                results.get('label'), results.get('name'), 
                                zi_id)]
                for rr in results['rrs']:
                    out += ["%1s %-32s %-12s %s" 
                            % ('X' if rr.get('disable') else ' ',
                                rr['label'], rr['type'], rr['rdata']) ]
            else:
                for rr in results['rrs']:
                    out += ["%-32s %-12s %s" 
                            % (rr['label'], rr['type'], rr['rdata']) ]
            out = '\n'.join(out)
            self.exit_code = self.pager(out, file=self.stdout)
        else:
            self.exit_code = os.EX_NOHOST
        return

    # For WSGI test mode
    do_rr_query_db = do_record_query_db
    
    def do_update_rrs(self, line):
        """
        Submit a file or stdin as an incremental update. This frontend
        is mainly for test purposes

        update_rrs [-n domain-name] [file-name] [domain-name]

        where:
                domain-name     domain name
                file-name       file containing update delta

        Example update file:

        $ORIGIN     foo.bar.org.
        $UPDATE_TYPE SpannerReplacement_ShouldBeUUIDperClientOpType

        ;!RROP:DELETE
        ns5             IN  ANY     ""  ; All records for ns5
        ;!RROP:DELETE
        ns7             IN  A       ""  ; All A records for ns2
        ;!RROP:DELETE
        ns67            IN  A       192.168.2.3 ; Specific record

        ;!RROP:ADD
        ns99            IN  TXT     "Does not know Maxwell Smart"
        ;!RROP:ADD
        ns99            IN  AAAA       2002:fac::1

        ;!RROP:UPDATE_RRTYPE
        ns99            IN  AAAA    ::1

        """
        syntax = (  (arg_file_name, arg_domain_name),
                    (arg_file_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('update_rrs')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            self.fillin_domain_name(arg_dict)
            file_name = arg_dict.pop('file_name')
            if file_name == '-':
                file_name = self.stdin
            name = arg_dict.get('name')
            arg_dict['update_data'], origin_name, arg_dict['update_type'], \
                    zone_reference \
                            = bind_to_data(file_name, name, \
                                    use_origin_as_name=True, update_mode=True)
            if origin_name.find('.') < 0:
                msg = ("%s: zone name must have '.' in it!" 
                        % file_name)
                print(error_msg_wrapper.fill(msg), file=self.stdout)
                self.exit_code = os.EX_DATAERR
            arg_dict.update({'name': origin_name, 'login_id': self.login_id})
            results = engine.update_rrs_admin(**arg_dict)
        except (IOError, OSError) as exc:
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_OSERR
            return
        except BinaryFileError as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_IOERR
            return
        except (ZiNotFound, ZoneNotFound) as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except (ZoneNameUndefined, BadInitialZoneName,
                InvalidDomainName, UpdateTypeRequired) as exc:
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (ParseBaseException, ZoneParseError, ZiParseError,
                SOASerialError, ZoneHasNoSOARecord) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            if (isinstance(exc, ParseBaseException) 
                or isinstance(exc, ZoneParseError)):
                print(exc.markInputline(), file=self.stdout)
            msg = "Parse error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_DATAERR
            return
        except (PrivilegeNeeded, ZoneSecTagDoesNotExist, 
                SecTagPermissionDenied) as exc:
            # Must not commit changes to DB when cleaning up!
            engine.rollback()
            msg = "Privilege error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        except (ZoneDisabled, IncrementalUpdatesDisabled) as exc:
            msg = "Privilege error - %s" % exc
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_NOPERM
            return
        except LoginIdError as exc:
            print (error_msg_wrapper.fill(str(exc)), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except (UpdateTypeAlreadyQueued) as exc:
            engine.rollback()
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return

    def do_refresh_zone_ttl(self, line):
        """
        Refresh a zone: refresh_zone_ttl <domain-name> [zone-ttl]

        This is done by queuing a zone update event.
        """
        syntax = ((arg_domain_name, arg_zone_ttl), (arg_domain_name,))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('refresh_zone_ttl')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            engine.refresh_zone_ttl(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneHasNoZi as exc:
            self.exit_code = os.EX_SOFTWARE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return
    
    def _diff_zone(self, zi1_data, zi2_data, z1_name=None, z2_name=None, 
                z1_reference=None, z2_reference=None, no_info_header=False):
        """
        Take difference between 2 ZIs and display it, hopefullu colorized
        """
        def clean_up():
            if (z1_filename):
                os.unlink(z1_filename)
            if (z2_filename):
                os.unlink(z2_filename)

        # Write zi data to a temporary files
        z1_filename = ''
        z2_filename = ''
        (z1_fd, z1_filename) = tempfile.mkstemp(
                                        prefix=settings['process_name']
                                        + '-', suffix='.zone')
        z1_file = io.open(z1_fd, mode='wt')
        data_to_bind(zi1_data, name=z1_name, 
                reference=z1_reference, no_info_header=no_info_header,
                file=z1_file)
        z1_file.flush()
        z1_file.close()
        (z2_fd, z2_filename) = tempfile.mkstemp(
                                        prefix=settings['process_name']
                                        + '-', suffix='.zone')
        z2_file = io.open(z2_fd, mode='wt')
        data_to_bind(zi2_data, name=z2_name, 
                reference=z2_reference, no_info_header=no_info_header,
                file=z2_file)
        z2_file.flush()
        z2_file.close()

        # do diff
        diff_bin = self.get_diff()
        diff_args = self.get_diff_args()
        diff_args = [diff_bin] + diff_args.split()
        diff_args.append(z1_filename)
        diff_args.append(z2_filename)
        tail_bin = self.get_tail()
        tail_args = self.get_tail_args()
        tail_argv = [tail_bin] + tail_args.split()
        # Make sure Less is secure
        pager_env = os.environ
        if not self.admin_mode:
            pager_env.update({'LESSSECURE': '1'})
        pager_bin = self.get_pager()
        pager_args = self.get_pager_args()
        pager_argv = [pager_bin] + pager_args.split()
        try:
            p1 = Popen(diff_args, stdout=PIPE)
            p2 = Popen(tail_argv, stdin=p1.stdout, stdout=PIPE)
            p3 = Popen(pager_argv, stdin=p2.stdout, env=pager_env)
            p2.stdout.close() # Allow p1, p2 to receive a SIGPIPE if p3
            p1.stdout.close() # exits
            # Do it
            output = p3.communicate()
        except (IOError,OSError) as exc:
            print (error_msg_wrapper.fill("Running %s failed: %s" 
                    % (exc.filename, exc.strerror)),
                    file=self.stdout)
            self.exit_code = os.EX_SOFTWARE
            return
        finally:
            clean_up()
        return

    def do_diff_zones(self, line):
        """
        Given two zones, display the difference:

        diff_zones <domain1-name> <domain2-name> [zi1-id [zi2-id]]

        where: 
                domain1-name    older domain name
                domain2-name    newer domain name
                zi1-id          zi-id for domain1-name
                                    defaults to published ZI
                zi2-id          zi-id for domain2-name
                                    defaults to published ZI
        """
        syntax = ((arg_domain1_name, arg_domain2_name, arg_zi1_id, arg_zi2_id),
                    (arg_domain1_name, arg_domain2_name, arg_zi1_id),
                    (arg_domain1_name, arg_domain2_name))
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('diff_zones')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            arg1_dict = {}
            arg1_dict['name'] = arg_dict['domain1_name']
            if arg_dict.get('zi1_id'):
                arg1_dict['zi_id'] = arg_dict['zi1_id']
            arg2_dict = {}
            arg2_dict['name'] = arg_dict['domain2_name']
            if arg_dict.get('zi2_id'):
                arg2_dict['zi_id'] = arg_dict['zi2_id']
            result1 = engine.show_zone_full(**arg1_dict)
            result2 = engine.show_zone_full(**arg2_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone/Zone Instance '%s' not present." 
                    % line, file=self.stdout)
            return
        self._diff_zone(result1['zi'], result2['zi'], 
                z1_name=result1['name'], z2_name=result2['name'],
                z1_reference=result1.get('reference'),
                z2_reference=result2.get('reference'))

    def do_diff_zone_zi(self, line):
        """
        Given a zone, display the differences between older and newer ZIs:

        diff_zone_zi <domain-name> zi1-id [zi2-id]

        where: 
                domain-name     domain name
                zi1-id          older zi-id for domain-name
                zi2-id          newer zi-id for domain-name,
                                    defaults to published ZI
        """
        syntax = ((arg_domain_name, arg_zi1_id, arg_zi2_id),
                    (arg_domain_name, arg_zi1_id),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('diff_zone_zi')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            arg1_dict = {}
            arg1_dict['name'] = arg_dict['name']
            if arg_dict.get('zi1_id'):
                arg1_dict['zi_id'] = arg_dict['zi1_id']
            arg2_dict = {}
            arg2_dict['name'] = arg_dict['name']
            if arg_dict.get('zi2_id'):
                arg2_dict['zi_id'] = arg_dict['zi2_id']
            result1 = engine.show_zone_full(**arg1_dict)
            result2 = engine.show_zone_full(**arg2_dict)
        except ZiIdSyntaxError as exc:
            self.exit_code = os.EX_USAGE
            msg = str(exc)
            print(error_msg_wrapper.fill(msg), file=self.stdout)
            return
        except ZoneNotFound:
            self.exit_code = os.EX_NOHOST
            print(self.error_prefix + "Zone/Zone Instance '%s' not present." 
                    % line, file=self.stdout)
            return
        self._diff_zone(result1['zi'], result2['zi'], 
                z1_name=result1['name'], z2_name=result2['name'],
                z1_reference=result1.get('reference'),
                z2_reference=result2.get('reference'),
                no_info_header=True)

    def do_restore_named_db(self, line):
        """
        Reestablish Named DB from dms DB for DR

        restore_named_db [-f]

        Note that root only may execute this, and that named and dmsdmd must
        not be running.
        """
        syntax = ((),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('restore_named_db')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Check that we are toor so that we can proceed
        if not self.check_if_root():
            return
        msg = ("WARNING - doing this destroys DNSSEC RRSIG data. "
            "It is a last resort in DR recovery.")
        print(error_msg_wrapper.fill(msg), file=self.stdout)
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.restore_named_db(**arg_dict)
        except CalledProcessError as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = exc.returncode
            return
        except (NamedStillRunning,DmsdmdStillRunning) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_UNAVAILABLE
            return
        except (PidFileValueError, PidFileAccessError) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        except (NamedConfWriteError, ZoneFileWriteError) as exc:
            msg = str(exc)
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_CANTCREATE
            return
        except ZoneNotFoundByZoneId as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def _print_ls_pending_events(self, result, verbose):
        """
        Format output for ls_pending_events
        """
        out = []
        for event in result:
            name = event['parameters'].get('name', '')
            name = event['parameters'].get('server_name', '') \
						if not name else name
            zi_id = event['parameters'].get('zi_id', '')
            zi_id = event['parameters'].get('publish_zi_id', '') \
						if not zi_id else zi_id
            zi_id = str(zi_id)
            if verbose:
                time3 = event['processed'] if event['processed'] else '--'
                event_str = (('%-19s  %-25s  %s\n'
                                        + '  ' + '%-27s  %s\n'
                                        + '  ' + '%s  %s  %s') % (
                                                event['event_type'], 
                                                event['event_id'],
                                                event['state'],
                                                name,
                                                zi_id,
                                                event['created'],
                                                event['scheduled'],
                                                time3))
            else:
                name = name + ' ' + zi_id if zi_id else name
                event_str = '%-25s %-27s  %s' % (event['event_type'],
                                                name,
                                                event['scheduled'])
            out += [event_str]
        
        out.append('')
        out = '\n'.join(out)
        return out

    def do_ls_pending_events(self, line):
        """
        List all pending events

        ls_pending_events [-v]

        where:
                -v          Do verbose output

        Shows event_id, event_type, name (if any), scheduled, created fields

        Note:  If queue really busy, may take a few seconds
        """
        syntax = ((),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('ls_pending_events')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        result = engine.list_pending_events()
        out = self._print_ls_pending_events(result, self.get_verbose())
        if out:
            self.exit_code = self.pager(out, file=self.stdout)

    def _print_ls_events(self, result, verbose):
        """
        Format output for ls_failed_events
        """
        out = []
        for event in result:
            name = event['parameters'].get('name', '')
            name = event['parameters'].get('server_name', '') \
						if not name else name
            zi_id = event['parameters'].get('zi_id', '')
            zi_id = event['parameters'].get('publish_zi_id', '') \
						if not zi_id else zi_id
            zi_id = str(zi_id)
            if not verbose:
                name = name + ' ' + zi_id if zi_id else name
                time2 = (event['scheduled'] 
                        if event['state'] in (ESTATE_NEW, ESTATE_RETRY)
                            else event['processed'])
                event_str = (('%-19s  %-25s  %s\n'
                                        + '  ' + '%-26s  %s  %s') % (
                                                event['event_type'], 
                                                event['event_id'],
                                                event['state'],
                                                name,
                                                event['created'],
                                                time2))
            else:
                time3 = event['processed'] if event['processed'] else '--'
                event_str = (('%-19s  %-25s  %s\n'
                                        + '  ' + '%-27s  %s\n'
                                        + '  ' + '%s  %s  %s') % (
                                                event['event_type'], 
                                                event['event_id'],
                                                event['state'],
                                                name,
                                                zi_id,
                                                event['created'],
                                                event['scheduled'],
                                                time3))
            out += [event_str]
        
        out.append('')
        out = '\n'.join(out)
        return out

    def do_ls_failed_events(self, line):
        """
        List the last n last-limit failed events in descending  order

        ls_pending_events [-v] [last-limit]

        where:
                -v              Do verbose output
                last-limit      Number of failed events to list
                                Default is 25

        Shows event_id, event_type, name (if any), created, scheduled fields

        Note:  If queue really busy, may take a few seconds
        """
        syntax = ((arg_last_limit,),(),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('ls_failed_events')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        result = engine.list_failed_events(**arg_dict)
        out = self._print_ls_events(result, self.get_verbose())
        if out:
            self.exit_code = self.pager(out, file=self.stdout)

    def do_ls_events(self, line):
        """
        List last events in descending order

        ls_events [-v] [last-limit]

        where:
                -v              Do verbose output
                last-limit      Number of failed events to list
                                Default is 25

        Shows event_id, event_type, name (if any), created, scheduled, 
        processed fields. If not verbose, show created time, then either
        prcessed or scheduled time if event has not been processed.

        Note:  If queue really busy, may take a few seconds
        """
        syntax = ((arg_last_limit,),(),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('ls_failed_events')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        result = engine.list_events(**arg_dict)
        out = self._print_ls_events(result, self.get_verbose())
        if out:
            self.exit_code = self.pager(out, file=self.stdout)
   
    def _print_show_event(self, result):
        """
        Format show_event output
        """
        parameters = result.pop('parameters', None)
        results = result.pop('results', None)
        out = []
        
        out += [ (self.indent + '%-16s' % (str(x) + ':')
                    + ' ' + str(result[x])) 
                        for x in result] 
        event_id = [ x for x in out if (x.find(' event_id:') >= 0)][0]
        out.remove(event_id)
        out.sort()
        out.insert(0, event_id)
        
        if parameters:
            p_out = []
            p_out += [ (self.indent + '%-16s' % (str(x) + ':')
                        + ' ' + str(parameters[x]))
                        for x in parameters]
            p_out.sort()
            p_out.insert(0, '')
            p_out.insert(1, self.indent + 'Event parameters:')
            out += p_out

        if results:
            r_out = []
            r_out += [ (self.indent + '%-16s' % (str(x) + ':')
                        + ' ' + str(results[x]))
                        for x in results]
            message_list  = [ x for x in r_out if (x.find(' message:') >= 0)]
            message = None
            if len(message_list):
                message = message_list[0]
                r_out.remove(message)
            r_out.sort()
            r_out.insert(0, '')
            r_out.insert(1, self.indent + 'Event results:')
            if message:
                message = message.split(':', 1)[-1].strip()
                r_out.append(self.indent + 'message:')
                r_out.append(output_msg_wrapper.fill(message))
            out += r_out

        out = '\n'.join(out)
        return out

    def do_show_event(self, line):
        """
        Show an event, given an event-id

        show_event <event-id>
        """
        syntax = ((arg_event_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('show_event')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        try:
            result = engine.show_event(**arg_dict)
        except EventNotFoundById as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        out = self._print_show_event(result)
        if out:
            self.exit_code = self.pager(out, file=self.stdout)

    def do_fail_event(self, line):
        """
        Fail an event, given an event-id

        fail_event [-f] <event-id>

        where:
                -f              Force operation
        """
        syntax = ((arg_event_id,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('fail_event')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            result = engine.fail_event(**arg_dict)
        except EventNotFoundById as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except CantFailEventById as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        return

    def do_poke_zone_set_serial(self, line):
        """
        Set the SOA serial number for a published zone: 
        
        poke_zone_set_serial [-fu] <domain-name> <soa-serial>

        where:
                -f              Force operation
                -u              Incrementally update SOA Serial number
                domain-name     Zone name
                soa-serial      Use this SOA serial number

        This is done by queuing a zone update event.
        """
        syntax = ((arg_domain_name, arg_soa_serial),
                    (arg_domain_name,), )
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('poke_zone_set_serial')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            self.fillin_force_soa_serial_update(arg_dict)
            engine.poke_zone_set_serial(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except SOASerialError as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotPublished as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return
    
    def do_poke_zone_wrap_serial(self, line):
        """
        Wrap the SOA serial for a published zone: 
        
        poke_zone_wrap_serial [-f] <domain-name>

        This is done by queuing a zone update event.
        """
        syntax = (  (arg_domain_name,),)
        try:
            arg_dict = parse_line(syntax, line)
        except DoHelp:
            self.do_help('poke_zone_wrap_serial')
            self.exit_code = os.EX_USAGE
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        # Query user as this may be unadvisable
        if not self.check_or_force():
            self.exit_code = os.EX_TEMPFAIL
            return
        try:
            engine.poke_zone_wrap_serial(**arg_dict)
        except ZoneNotFound as exc:
            self.exit_code = os.EX_NOHOST
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except SOASerialError as exc:
            self.exit_code = os.EX_PROTOCOL
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneNotPublished as exc:
            self.exit_code = os.EX_UNAVAILABLE
            print(error_msg_wrapper.fill(str(exc)), file=self.stdout)
            return
        except ZoneSmFailure as exc:
            msg = "ZoneSM failure - %s" % exc 
            print (error_msg_wrapper.fill(msg), file=self.stdout)
            self.exit_code = os.EX_PROTOCOL
            return
        return
    
    def do_show_dms_status(self, line):
        """
        Show DMS system status information
        
        show_dms_status [-v]
        """
        syntax = ((),)
        try:
            args = parse_line(syntax, line)
        except DoHelp:
            self.exit_code = os.EX_USAGE
            self.do_help('show_dms_status')
            return
        except DoNothing:
            self.exit_code = os.EX_USAGE
            return
        verbose = self.get_verbose()
        result = engine.show_dms_status()
        out = '\nshow_master_status:\n'
        out += self._print_show_mastersm(result['show_mastersm'], verbose)
        out += '\nshow_replica_sg:\n'
        out += self._print_show_sg(result['show_replica_sg'], verbose)
        out += '\nls_server:\n'
        out += self._print_ls_server(result['list_server'], verbose=True, 
                oping_servers=True)
        out += '\nlist_pending_events:\n'
        out += self._print_ls_pending_events(result['list_pending_events'], 
                                        verbose=False)
        out += '\n'
        self.exit_code = self.pager(out, file=self.stdout)
        return




class SIGALRMHandler(SignalHandler):
    """
    Handle a SIGALRM signal.

    Just make action() return False
    """
    def action(self):
        log_debug('SIGALRM received - system timer went off.')
        return False


class ForceCmdCmdLineArg(BooleanCmdLineArg):
    """
    Process force command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='f',
                            long_arg='force-cmd',
                            help_text="Force command, say if file unchanged",
                            settings_key = 'force_cmd',
                            settings_default_value = False,
                            settings_set_value = True)

class OriginCmdLineArg(BooleanCmdLineArg):
    """
    Process origin command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='o',
                            long_arg='use-origin-as-name',
                            help_text="Use $ORIGIN to set zone name from file",
                            settings_key = 'use_origin_as_name',
                            settings_default_value = False,
                            settings_set_value = True)

class ShowAllCmdLineArg(BooleanCmdLineArg):
    """
    Process show-active command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='a',
                        long_arg='show-all',
                        help_text="Show disabled zones, RRs, and all Servers",
                        settings_key = 'show_all',
                        settings_default_value = False,
                        settings_set_value = True)

class ShowActiveCmdLineArg(BooleanCmdLineArg):
    """
    Process show-active command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='t',
                        long_arg='show-active',
                        help_text="Show only active Servers and Zones",
                        settings_key = 'show_active',
                        settings_default_value = False,
                        settings_set_value = True)

class SoaSerialUpdateCmdLineArg(BooleanCmdLineArg):
    """
    Process soa-serial-update command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                            short_arg='u',
                        long_arg='soa-serial-update',
                        help_text="Force SOA Serial update",
                        settings_key = 'force_soa_serial_update',
                        settings_default_value = False,
                        settings_set_value = True)

class WsgiApiTestCmdLineArg(BooleanCmdLineArg):
    """
    IncUpdates is turned on for zone load
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self, short_arg='D',
                                long_arg="wsgi-api-test",
                                help_text="Enable zone_tool test WSGI commands",
                                settings_key='wsgi_api_test_flag',
                                settings_default_value= False,
                                settings_set_value=True)

class ReferenceCmdLineArg(BaseCmdLineArg):
    """
    Set reference used 
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='r:',
                                long_arg="reference=",
                                help_text="Set the reference used")
        settings['reference'] = None

    def process_arg(self, process, value, *args, **kwargs):
        """
        Set the default value of the reference used
        """
        settings['reference'] = value 

class SecTagCmdLineArg(BaseCmdLineArg):
    """
    Set Security tag used
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='s:',
                                long_arg="sectag=",
                                help_text="Set the security tag used")
        settings['sectag_label'] = None

    def process_arg(self, process, value, *args, **kwargs):
        """
        Set the default value of the security tag used
        """
        settings['sectag_label'] = value 

class SgCmdLineArg(BaseCmdLineArg):
    """
    Set server group used
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='g:',
                                long_arg="server-group=",
                                help_text="Set the server group")
        settings['default_sg'] = None

    def process_arg(self, process, value, *args, **kwargs):
        """
        Set the default SG 
        """
        settings['default_sg'] = value 

class ReplicaSgCmdLineArg(BooleanCmdLineArg):
    """
    SG is made the replica SG
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self, short_arg='p',
                                long_arg="replica-sg",
                                help_text="Set/Show the replica SG",
                                settings_key='replica_sg_flag',
                                settings_default_value= False,
                                settings_set_value=True)

class IncUpdatesCmdLineArg(BooleanCmdLineArg):
    """
    IncUpdates is turned on for zone load
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self, short_arg='i',
                                long_arg="inc-updates",
                                help_text="Set inc_updates for loading zones",
                                settings_key='inc_updates_flag',
                                settings_default_value= False,
                                settings_set_value=True)

class OPingServersCmdLineArg(BooleanCmdLineArg):
    """
    OPing is enabled for ls_server
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self, short_arg='j',
                                long_arg="oping-servers",
                                help_text="oping servers when listing them",
                                settings_key='oping_servers_flag',
                                settings_default_value= False,
                                settings_set_value=True)

class ZoneCmdLineArg(BaseCmdLineArg):
    """
    Set the domain used in RR queries
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='n:',
                                long_arg="domain=",
                                help_text="Set domain used in RR queries")
        settings['zone_name'] = None

class ZiCmdLineArg(BaseCmdLineArg):
    """
    Set the ZI used in RR queries
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='z:',
                                long_arg="zi=",
                                help_text="Set ZI used in RR queries")
        settings['zi_id'] = None
    def process_arg(self, process, value, *args, **kwargs):
        """
        Set query_zone
        """
        if value == '*':
            settings['zi_id'] = 0
            return
        try:
            settings['zi_id'] = int(value)
        except ValueError as exc:
            print(error_msg_wrapper.fill(str(exc)), file=sys.stderr)
            sys.exit(os.EX_USAGE)

class ZoneTool(Process):
    """
    Process Main Daemon class
    """
    def __init__(self, *args, **kwargs):
        Process.__init__(self, usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION,
            use_gnu_getopt=False,
            *args, **kwargs)
        self.cmdline_arg_list.append(ForceCmdCmdLineArg())
        self.cmdline_arg_list.append(SecTagCmdLineArg())
        self.cmdline_arg_list.append(ReplicaSgCmdLineArg())
        self.cmdline_arg_list.append(IncUpdatesCmdLineArg())
        self.cmdline_arg_list.append(OPingServersCmdLineArg())
        self.cmdline_arg_list.append(OriginCmdLineArg())
        self.cmdline_arg_list.append(SgCmdLineArg())
        self.cmdline_arg_list.append(ReferenceCmdLineArg())
        self.cmdline_arg_list.append(ShowAllCmdLineArg())
        self.cmdline_arg_list.append(ShowActiveCmdLineArg())
        self.cmdline_arg_list.append(SoaSerialUpdateCmdLineArg())
        self.cmdline_arg_list.append(ZoneCmdLineArg())
        self.cmdline_arg_list.append(ZiCmdLineArg())
        self.cmdline_arg_list.append(WsgiApiTestCmdLineArg())
        # Initialise command line environment
        self.cmd = ZoneToolCmd()
        self.argv_cmd = ''
        # Set logging level to critical to stop too much feedback!
        # Does not affect debug command line flag
        settings['log_level'] = MAGLOG_CRITICAL

    def usage_full(self, tty_file=sys.stdout):
        """
        Full usage string
        """
        super().usage_full(tty_file=tty_file)
        self.cmd.do_help('', no_pager=True)

    def parse_argv_left(self, argv_left):
        """
        Handle any arguments left after processing all switches

        Override in application if needed.
        """
        if len(argv_left):
            self.argv_cmd = ' '.join(argv_left)

    def main_process(self):
        """Main process editzone
        """
        global engine
        global db_session

        # Connect to database, intialise SQL Alchemy
        setup_sqlalchemy()
        db_session = sql_data['scoped_session_class']()

        # Set up WSGI API test mode
        self.cmd.init_wsgi_apt_test_mode()

        # Create 'engine'
        sectag_label = settings['sectag_label']
        sectag_label = (sectag_label if sectag_label 
                            else settings['admin_sectag'])
        log_info('Using sectag_label: %s' % sectag_label) 
        try:
            engine = CmdLineEngine(sectag_label=sectag_label)
        except ZoneSecTagConfigError as exc:
            print(error_msg_wrapper.fill(str(exc)), file=sys.stderr)
            sys.exit(os.EX_USAGE)

        if self.argv_cmd:
            # Running as a command from shell
            self.cmd.onecmd(self.argv_cmd)
            sys.exit(self.cmd.exit_code)
        elif sys.stdin and hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
            # Running as a command shell attached to a tty
            loop = True
            while loop:
                try:
                    self.cmd.cmdloop()
                    loop = False
                except KeyboardInterrupt:
                    # Stop Welcome message
                    self.cmd.intro = ' '
                    pass
            print('\n', file=sys.stdout)
            sys.exit(os.EX_OK)
        else:
            # Running aattached to a pipe
            self.cmd.intro = None
            #self.cmd.indent = ''
            self.cmd.cmdloop()
            sys.exit(os.EX_OK)


if (__name__ is "__main__"):
    exit_code = ZoneTool(sys.argv, len(sys.argv))
    sys.exit(exit_code)


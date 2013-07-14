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
"""Test Utility

Program implemented by subclassing net.24.core.process.Process, and 
replacing the main() method.
"""


import os
import sys
import io
import re
import tempfile
import stat
import socket
from subprocess import check_call
from subprocess import CalledProcessError

import dns.zone

from magcode.core.process import Process
from magcode.core.process import BooleanCmdLineArg
from magcode.core.process import BaseCmdLineArg
from magcode.core.globals_ import *
from dms.dyndns_update import DynDNSUpdate
from dms.database.resource_record import dnspython_to_rr
from dms.database.zone_instance import ZoneInstance
from dms.exceptions import DynDNSCantReadKeyError
from dms.exceptions import NoSuchZoneOnServerError
from magcode.core.database import RCODE_OK
from magcode.core.database import RCODE_ERROR
from magcode.core.database import RCODE_RESET
from magcode.core.database import RCODE_FATAL
from magcode.core.database import RCODE_NOCHANGE


USAGE_MESSAGE = "Usage: %s [-dfhknprsuvy] [-c config_file] <domain-name> [dns-server]"
COMMAND_DESCRIPTION = "Edit or manipulate a domain directly via dynamic DNS"

settings['config_section'] = 'DEFAULT'

class NoSOASerialUpdateCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='n',
                                long_arg='no-serial',
                                help_text="Don't update SOA serial no",
                                settings_key = 'no_serial',
                                settings_default_value = False,
                                settings_set_value = True)

class WrapSOASerialCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='r',
                                long_arg='wrap-serial',
                                help_text="Wrap SOA serial no",
                                settings_key = 'wrap_serial',
                                settings_default_value = False,
                                settings_set_value = True)

class UpdateSOASerialCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='u',
                                long_arg='update-serial',
                                help_text="Just update SOA serial normally",
                                settings_key = 'update_serial',
                                settings_default_value = False,
                                settings_set_value = True)

class ForceUpdateCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='f',
                                long_arg='force-update',
                                help_text="Force update if file unchanged",
                                settings_key = 'force_update',
                                settings_default_value = False,
                                settings_set_value = True)

class ClearDnskeyCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='y',
                                long_arg='clear-dnskey',
                                help_text="Delete apex DNSKEY RRs",
                                settings_key = 'clear_dnskey',
                                settings_default_value = False,
                                settings_set_value = True)

class ClearNsec3CmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='k',
                                long_arg='clear-nsec3',
                                help_text="Delete NSEC3PARAM RR",
                                settings_key = 'clear_nsec3',
                                settings_default_value = False,
                                settings_set_value = True)

class Nsec3SeedCmdLineArg(BooleanCmdLineArg):
    """
    Process verbose command Line setting
    """
    def __init__(self):
        BooleanCmdLineArg.__init__(self,
                                short_arg='s',
                                long_arg='nsec3-seed',
                                help_text="Create NSEC3PARAM RR",
                                settings_key = 'nsec3_seed',
                                settings_default_value = False,
                                settings_set_value = True)

class PortCmdLineArg(BaseCmdLineArg):
    """
    Handle configuration file setting
    """
    def __init__(self):
        BaseCmdLineArg.__init__(self, short_arg='p:',
                                long_arg="port=",
                                help_text="set DNS server port")
    
    def process_arg(self, process, value, *args, **kwargs):
        """
        Set configuration file name
        """
        settings['dns_port'] = value 


class DynDNSTool(Process):
    """
    Process Main Daemon class
    """
    def __init__(self, *args, **kwargs):
        Process.__init__(self, usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION, *args, **kwargs)
        self.cmdline_arg_list.append(NoSOASerialUpdateCmdLineArg())
        self.cmdline_arg_list.append(WrapSOASerialCmdLineArg())
        self.cmdline_arg_list.append(UpdateSOASerialCmdLineArg())
        self.cmdline_arg_list.append(ForceUpdateCmdLineArg())
        self.cmdline_arg_list.append(Nsec3SeedCmdLineArg())
        self.cmdline_arg_list.append(ClearNsec3CmdLineArg())
        self.cmdline_arg_list.append(ClearDnskeyCmdLineArg())
        self.cmdline_arg_list.append(PortCmdLineArg())

    def parse_argv_left(self, argv_left):
        """
        Handle any arguments left after processing all switches

        Override in application if needed.
        """
        if (len(argv_left) != 1 and len(argv_left) != 2):
            self.usage_short()
            sys.exit(os.EX_USAGE)
        
        self.argv_left = argv_left
        self.zone_name = argv_left[0]
        if not re.match('^[\S\.]+$', self.zone_name):
            self.usage_short()
            sys.exit(os.EX_USAGE)
        if (not self.zone_name.endswith('.')):
            self.zone_name += '.'

        if (len(argv_left) ==2):
            if not re.match('^[\S\.]+$', argv_left[1]):
                self.usage_short()
                sys.exit(os.EX_USAGE)
            settings['dns_server'] = argv_left[1]


    def _get_editor(self):
        """
        Work out the users preference of editor, and return that
        """
        editor = os.getenvb(b'VISUAL')
        if (editor):
            return editor
        
        editor = os.getenvb(b'EDITOR')
        if (editor):
            return editor

        editor = b'/usr/bin/sensible-editor'
        if os.path.isfile(editor):
            return editor 
        
        editor = b'/usr/bin/editor'
        if os.path.isfile(editor):
            return editor 

        # Fall back if none of the above is around...
        return b'/usr/bin/vi'

    def main_process(self):
        """Main process editzone
        """
        def clean_up():
            if (tmp_file):
                os.unlink(tmp_file)

        tmp_file = ''
        # Get update session object
        error_str = ''
        try:
            update_session = DynDNSUpdate(settings['dns_server'],
                                    settings['dyndns_key_file'],
                                    settings['dyndns_key_name'],
                                    )
        except (socket.error, DynDNSCantReadKeyError, IOError) as exc:
            error_str = str(exc)
        # Process above error...
        if (error_str):
            log_error("%s" % error_str)
            sys.exit(os.EX_NOHOST)

        # Do AXFR to obtain current zone data
        msg = None
        try:
            (zone, dnskey_flag, nesc3param_flag) \
                = update_session.read_zone(self.zone_name)
        except NoSuchZoneOnServerError as exc:
            msg = str(exc)
        if msg:
            log_error(msg)
            sys.exit(os.EX_NOINPUT)
            
        # Only edit zone if not wrapping SOA serial number 
        if (not settings['wrap_serial'] and not settings['update_serial']
                and not settings['nsec3_seed'] and not settings['clear_nsec3']
                and not settings['clear_dnskey']):
            # Write zone out to a temporary file
            (fd, tmp_file) = tempfile.mkstemp(prefix=settings['process_name'] + '-',
                                    suffix='.zone')
            os.close(fd)
            zone.to_file(tmp_file)

            # Edit zone data
            old_stat = os.stat(tmp_file)
            editor = self._get_editor()
            try:
                output = check_call([editor, tmp_file])
            except CalledProcessError as exc:
                log_error("editor exited with '%s'." % exc.returncode)
                sys.exit(os.EX_SOFTWARE)
                
            new_stat = os.stat(tmp_file)
            if (not settings['force_update'] 
                    and old_stat[stat.ST_MTIME] == new_stat[stat.ST_MTIME]
                    and old_stat[stat.ST_SIZE] == new_stat[stat.ST_SIZE]
                    and old_stat[stat.ST_INO] == new_stat[stat.ST_INO]):
                log_info("File '%s' unchanged after editing - exiting." % tmp_file)
                clean_up()
                sys.exit(os.EX_OK)
     
            # Read in file and form zi structure
            zone = dns.zone.from_file(tmp_file, self.zone_name)
        # At the moment these values are just for the sake of it.
        zi = ZoneInstance(soa_refresh='5m', soa_retry='5m', soa_expire='7d', soa_minimum='600')
        for rdata in zone.iterate_rdatas():
            zi.add_rr(dnspython_to_rr(rdata))

        # Update Zone in DNS
        rcode, msg, soa_serial, *stuff = update_session.update_zone(
                            self.zone_name, zi, 
                            force_soa_serial_update=not(settings['no_serial']),
                            wrap_serial_next_time=settings['wrap_serial'],
                            nsec3_seed=settings['nsec3_seed'],
                            clear_nsec3=settings['clear_nsec3'],
                            clear_dnskey=settings['clear_dnskey']
                            )

        if rcode == RCODE_NOCHANGE:
            log_info(msg)
            sys.exit(os.EX_OK)

        # Delete temporary file
        clean_up()

        if rcode == RCODE_ERROR:
            log_warning(msg)
            sys.exit(os.EX_TEMPFAIL)
        elif rcode == RCODE_RESET:
            log_error(msg)
            sys.exit(os.EX_IOERR)
        elif rcode == RCODE_FATAL:
            log_error(msg)
            sys.exit(os.EX_IOERR)

        # Everything good - Lets GO!
        if (settings['verbose']):
            log_info(msg)
        else:
            log_debug(msg)
        sys.exit(os.EX_OK)




if (__name__ is "__main__"):
    exit_code = DynDNSTool(sys.argv, len(sys.argv))
    sys.exit(exit_code)


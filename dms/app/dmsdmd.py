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
"""Main DNS Management Daemon Code

Program implemented by subclassing magcode.core.process.Process, and 
replacing the main() method.
"""

import os
import os.path
import errno
import sys
import pwd
import time
import copy
import signal
import gc
import json

import psutil

from magcode.core.process import ProcessDaemon
from magcode.core.process import SignalHandler
from magcode.core.globals_ import *
from magcode.core.database import *
from magcode.core.database.event import EventQueue
from magcode.core.utility import get_numeric_setting
from magcode.core.utility import get_boolean_setting
# import to pull in and init ProcessSM
import magcode.core.database.process_sm
# import to pull in and init ZoneSMs
import dms.database.zone_sm
from magcode.core.utility import connect_test_address
from dms.database.master_sm import recalc_machine_dns_server_info
from dms.database.server_sm import init_soaquery_rcodes
# import to fully init settings for config file DEFAULT section
from dms.globals_ import update_engine
from dms.dyndns_update import DynDNSUpdate
from dms.exceptions import DynDNSCantReadKeyError


USAGE_MESSAGE = "Usage: %s [-dhv] [-c config_file]"
COMMAND_DESCRIPTION = "DMS DNS Management Daemon"


class SIGUSR1Handler(SignalHandler):
    """
    Handle a SIGUSR1 signal.

    Just make action() return False to wake loop
    """
    def action(self):
        log_info('SIGUSR1 received - running event queue.')
        return False

class DmsDMDProcess(ProcessDaemon):
    """
    Process Main Daemon class
    """
    def __init__(self, *args, **kwargs):
        super().__init__(usage_message=USAGE_MESSAGE,
            command_description=COMMAND_DESCRIPTION, *args, **kwargs)

    def init_signals(self):
        """
        Initialise signal handlers for the daemon
        """
        super().init_signals()
        self.register_signal_handler(signal.SIGUSR1, SIGUSR1Handler())
    
    def init_master_dns_address(self):
        """
        Master dns server setting in an IP addr

        Results determined by getaddrinfo(3) and thus by /etc/hosts contents, 
        or else DNS if hostname not in /etc/hosts!
        """
        test_hostname = settings['master_dns_server']
        if not test_hostname:
            test_hostname = socket.getfqdn()
        connect_retry_wait = get_numeric_setting('connect_retry_wait', float)
        exc_msg = ''
        for t in range(3):
            try:
                # Transform any hostname to an IP address
                settings['master_dns_server'] = connect_test_address(
                                                test_hostname,
                                                port=settings['master_dns_port'])
                break
            except(IOError, OSError) as exc:
                exc_msg = str(exc)
                time.sleep(connect_retry_wait)
                continue
        else:
            log_error("Testing master DNS server IP address '%s:%s' - %s" 
                        % (test_hostname, settings['master_dns_port'], exc_msg))
            systemd_exit(os.EX_NOHOST, SDEX_CONFIG)
        # If we get here without raising an exception, we can talk to
        # the server address (mostly)
        return

    def init_master_dns_server_data(self):
        """
        Read in configuration values for these, and then process them

        This is a bit messy, but it does the job just here.
        """
        # We use config file initially to set list
        this_servers_addresses = settings['this_servers_addresses']
        if isinstance(this_servers_addresses, str):
            try:
                this_servers_addresses = settings['this_servers_addresses']\
                                        .replace(',', ' ')\
                                        .replace("'", ' ')\
                                        .replace('"', ' ')\
                                        .replace('[', ' ')\
                                        .replace(']', ' ')\
                                        .strip().split()
            except ValueError as exc:
                log_error("Could not parse 'this_servers_addresses' to obtain"
                        " list of this servers DNS listening addresses - %s"
                            % str(exc))
                systemd_exit(os.EX_CONFIG, SDEX_CONFIG)
        settings['this_servers_addresses'] = this_servers_addresses
        # Recalculate host information - this will do nothing 
        # if 'ifconfig -a' et al won't work
        ifconfig_exc = (True if not settings['this_servers_addresses'] 
                            else False)
        try:
            db_session = sql_data['scoped_session_class']()
            recalc_machine_dns_server_info(db_session, ifconfig_exc)
            db_session.commit()
        except Exception as exc:
            log_error(str(exc))
            systemd_exit(os.EX_UNAVAILABLE, SDEX_NOTRUNNING)
        log_info("List of local IPs, 'this_servers_addresses' - %s"
                    % ', '.join(settings['this_servers_addresses']))
        log_info("Master DNS server on this machine, 'master_dns_server' - %s"
                    % settings['master_dns_server'])

    def init_update_engines(self):
        """
        Initialise the update engines used
        """
        connect_retry_wait = get_numeric_setting('connect_retry_wait', float)
        error_str = ''
        for t in range(3):
            try:
                dyndns_engine = DynDNSUpdate(settings['dns_server'],
                                        settings['dyndns_key_file'],
                                        settings['dyndns_key_name'])
                break
            except (DynDNSCantReadKeyError, IOError, OSError) as exc:
                error_str = ("Can't connect to named for dynamic updates - %s" 
                                % str(exc))
                time.sleep(connect_retry_wait)
                continue
        # Process above error...
        else:
            log_error("%s" % error_str)
            systemd_exit(os.EX_NOHOST, SDEX_CONFIG)
        update_engine['dyndns'] = dyndns_engine

    def do_garbage_collect(self):
        """
        Do Resource Release exercise at low memory threshold, blow up over max
        """
        error_str = ''
        try:
            rss_mem_usage = (float(self.proc_monitor.get_memory_info().rss)
                                    /1024/1024)
        except Exception as exc:
            error_str = str(exc)
        # Process above error...
        if (error_str):
            log_error("Error obtaining resource usage - %s" % error_str) 
            systemd_exit(os.EX_SOFTWARE, SDEX_NOTRUNNING)
        memory_exec_threshold = get_numeric_setting('memory_exec_threshold', float)
        if (rss_mem_usage > memory_exec_threshold):
            log_warning('Memory exec threshold %s MB reached, actual %s MB - execve() to reclaim.'
                        % (memory_exec_threshold, rss_mem_usage))
            file_path = os.path.join(sys.path[0], sys.argv[0])
            file_path = os.path.normpath(file_path)
            os.execve(file_path, sys.argv, os.environ)
        else:
            # Spend idle time being RAM thrifty...
            gc.collect()
            return

    def main_process(self):
        """Main process for dmsdmd
        """
        
        if (settings['rpdb2_wait']):
            # a wait to attach with rpdb2...
            log_info('Waiting for rpdb2 to attach.')
            time.sleep(float(settings['rpdb2_wait']))

        log_info('program starting.')
        log_debug("The daemon_canary is: '%s'" % settings['daemon_canary'])
        # Do a nice output message to the log
        pwnam = pwd.getpwnam(settings['run_as_user'])
        log_debug("PID: %s daemon: '%s' User: '%s' UID: %d GID %d" 
                % (os.getpid(), self.i_am_daemon(), pwnam.pw_name,
                    os.getuid(), os.getgid()))

        # Check we can reach DNS server
        self.init_update_engines()
        
        # Initialise ServerSM rcodes from settings
        init_soaquery_rcodes()

        # Initialize master dns address if required
        self.init_master_dns_address()

        # Connect to database, intialise SQL Alchemy
        setup_sqlalchemy()

        # Initialize master DNS server data
        self.init_master_dns_server_data()

        # Create a queue
        event_queue = EventQueue()

        # Create a Process object so that we can check in on ourself resource
        # wise
        self.proc_monitor = psutil.Process(pid=os.getpid())

        # Initialise  a few nice things for the loop
        debug_mark = get_boolean_setting('debug_mark') 
        sleep_time = get_numeric_setting('sleep_time', float)
        # test Read this value...
        master_hold_timeout = get_numeric_setting('master_hold_timeout', float)

        if (settings['memory_debug']):
            # Turn on memory debugging
            log_info('Turning on GC memory debugging.')
            gc.set_debug(gc.DEBUG_LEAK)

        # Process Main Loop
        while (self.check_signals()):
            
            event_queue.process_queue()
            if event_queue.queue_empty():
                self.do_garbage_collect()
            if debug_mark:
                log_debug("----MARK---- sleep(%s) seconds ----"
                        % sleep_time) 
            time.sleep(sleep_time)

        log_info('Exited main loop - process terminating normally.')
        sys.exit(os.EX_OK)


if (__name__ is "__main__"):
    exit_code = DmsDMDProcess(sys.argv, len(sys.argv))
    sys.exit(exit_code)

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
Globals file for dms system
"""

from magcode.core.globals_ import settings

# settings for where files are
settings['config_dir'] = '/etc/dms'
settings['log_dir'] = '/var/log/dms'
settings['run_dir'] = '/var/run/dms'
settings['var_lib_dir'] = '/var/lib/dms'
settings['config_file'] = settings['config_dir'] + '/' + 'dms.conf'
# DMS only uses one daemon 
settings['pid_file'] = settings['run_dir'] + '/' + 'dmsdmd.pid'
settings['event_queue_pid_file'] = settings['pid_file']
settings['log_file'] = settings['log_dir'] \
        + '/' + settings['process_name'] + '.log'
settings['panic_log'] = settings['log_dir'] \
        + '/' + settings['process_name'] + '-panic.log'

# settings initialisations that cause trouble with config key checking
# if in /etc/dms.conf [DEFAULT] section

# DB settings to help prevent RAM piggery
settings['db_query_slice'] = 1000
settings['preconvert_int_settings'] += 'db_query_slice'
# DB event queue columns
# DO NOT CHANGE THIS UNLESS YOU KNOW WHAT YOU ARE DOING!
settings['event_queue_fkey_columns'] = 'zone_id server_id master_id'

# dmsdmd.py
# Print debug mark
settings['debug_mark'] = False
# Number of seconds we wait while looping in main loop...
settings['sleep_time'] = 3 # seconds
settings['debug_sleep_time'] = 20 # seconds
settings['memory_exec_threshold'] = 250 #MB

# dyndns_update.py
settings['dig_path'] = 'dig'
settings['dig_arguments'] = "+noall +answer"
settings['rndc_path'] = "rndc"
settings['rndc_arguments'] = ""
settings['nsupdate_path'] = "rndc"
settings['nsupdate_arguments'] = ""
# The following works because of the import at the top!
if (settings['os_family'] == 'FreeBSD'):
    settings['dyndns_key_file'] = '/etc/namedb/update-session.key'
else:
    settings['dyndns_key_file'] = '/etc/bind/update-session.key'
settings['dyndns_key_name'] = 'update-ddns'
settings['dnssec_filter'] = 'RRSIG DNSKEY NSEC3 NSEC3PARAM TYPE65534 NSEC'
settings['dyndns_success_rcodes'] = 'NOERROR'
settings['dyndns_retry_rcodes'] = 'SERVFAIL NOTAUTH NXRRSET'
settings['dyndns_reset_rcodes'] = 'NXDOMAIN'
settings['dyndns_fatal_rcodes'] = 'BADVERS NOTIMP NOTZONE YXRRSET YXDOMAIN FORMERR REFUSED'

# update_engine.py
settings['dns_server'] = 'localhost'
settings['dns_port'] = 'domain'
settings['dns_query_timeout'] = 30 # seconds
settings['soa_serial_wrap_threshold'] = 9950
settings['nsec3_salt_bit_length'] = 64
settings['nsec3_hash_algorithm'] = 1
settings['nsec3_flags'] = 1
settings['nsec3_iterations'] = 10
# Place for Update engines fo be registered.
update_engine = {}

# zone_text_utils.py
settings['apex_rr_tag'] = 'APEX_RRS'
settings['comment_group_leader'] = ';|'
settings['comment_rr_leader'] = ';#'
settings['comment_rrflags_leader'] = ';!'
# Don't use '^' at the start of the following regexp - comment line will cause
# the zone_parser to fail!
settings['comment_anti_regexp'] = ';[^!#|]'
settings['rr_flag_lockptr'] = 'LOCKPTR'
settings['rr_flag_forcerev'] = 'FORCEREV'
settings['rr_flag_disable'] = 'DISABLE'
settings['rr_flag_ref'] = 'REF:'
settings['rr_flag_rrop'] = 'RROP:'
settings['rr_flag_trackrev'] = 'TRACKREV'

#zone_cfg.py
settings['apex_ns_key'] = 'apex_ns'

# zone_sm.py
settings['apex_comment_template'] = 'Apex resource records for %s'
settings['edit_lock_timeout'] = 30 # minutes
if (settings['os_family'] == 'Linux'):
    settings['master_bind_config_dir'] = '/etc/bind'
    settings['master_config_dir'] = settings['var_lib_dir'] \
                                     + '/' + 'master-config'
    settings['master_dyndns_dir'] = '/var/lib/bind/dynamic'
    settings['master_slave_dir'] = '/var/lib/bind/slave'
    settings['master_static_dir'] = '/var/lib/bind/static'
    settings['master_dnssec_key_dir'] = '/var/lib/bind/keys'
elif (settings['os_family'] == 'FreeBSD'):
    settings['master_bind_config_dir'] = '/etc/namedb'
    settings['master_config_dir'] = '/etc/namedb/master-config'
    settings['master_dyndns_dir'] = '/etc/namedb/dynamic'
    settings['master_slave_dir'] = '/etc/namedb/slave'
    settings['master_static_dir'] = '/etc/namedb/static'
    settings['master_dnssec_key_dir'] = '/etc/namedb/keys'
settings['master_template_dir_name'] = 'master-config-templates'
settings['master_template_dir'] = settings['config_dir'] + '/' \
                                        + settings['master_template_dir_name']
MASTER_DYNDNS_TEMPLATE = 'master_dyndns_template'
settings[MASTER_DYNDNS_TEMPLATE] = 'dynamic-config.conf'
MASTER_AUTO_DNSSEC_TEMPLATE = 'master_auto_dnssec_template'
settings[MASTER_AUTO_DNSSEC_TEMPLATE] = 'auto-dnssec-config.conf'
MASTER_SERVER_ACL_TEMPLATE = 'master_server_acl_template'
settings[MASTER_SERVER_ACL_TEMPLATE] = 'server-acl.conf'
MASTER_STATIC_TEMPLATE = 'master_static_template'
settings[MASTER_STATIC_TEMPLATE] = 'static-config.conf'
MASTER_SLAVE_TEMPLATE = 'master_slave_template'
settings[MASTER_SLAVE_TEMPLATE] = 'slave-config.conf'
# This is a file name as a tempfile is created and mved into place
settings['master_include_file'] = settings['master_config_dir'] \
                                    + '/' + 'zones.conf' 
settings['master_server_acl_file'] = settings['master_config_dir'] \
                                    + '/' + 'server-acl.conf' 
settings['acl_name_extension'] = '-servers'
settings['default_acl_name'] = 'dms' + settings['acl_name_extension']
settings['zone_file_mode'] = '00664'
settings['zone_file_group'] = 'bind'

# master_sm.py
settings['master_hold_timeout'] = 10  #minutes
settings['master_rndc_settle_delay'] = 5 #seconds
settings['config_file_mode'] = '00644'

# server_group.py
settings['server_config_dir'] = settings['config_dir'] \
                + '/server-config-templates'
settings['server_replica_suffix'] = '-replica'
settings['sg_config_dir'] = settings['var_lib_dir'] + '/dms-sg'
# These 2 settings are initialized in dms/apps/dmsdmd.py
settings['master_dns_server'] = None
settings['master_dns_port'] = 'domain'
settings['this_servers_addresses'] = []

# server_sm.py
settings['rsync_path'] = 'rsync'
settings['rsync_password_file'] = settings['config_dir'] \
                + '/' + 'rsync-dnsconf-password'
settings['rsync_args'] = '--quiet -rptv'
settings['rsync_target_user'] = 'dnsconf'
settings['rsync_target_module'] = 'dnsconf'
settings['rsync_target'] = (settings['rsync_target_user'] + '@%s::' 
                + settings['rsync_target_module'] + '/')
settings['rsync_dnssec_args'] = '--quiet -av'
settings['rsync_dnssec_password_file'] = settings['config_dir'] \
                                + '/' + 'rsync-dnssec-password'
settings['rsync_dnssec_user'] = 'dnssec'
settings['rsync_dnssec_module'] = 'dnssec'
settings['rsync_dnssec_target'] = (settings['rsync_dnssec_user'] + '@%s::' 
                            + settings['rsync_dnssec_module'] + '/')
settings['serversm_soaquery_success_rcodes'] = 'NOERROR'
settings['serversm_soaquery_ok_rcodes'] = settings['serversm_soaquery_success_rcodes'] + ' ' + 'NXDOMAIN REFUSED NOTAUTH'
settings['serversm_soaquery_retry_rcodes'] = ''
settings['serversm_soaquery_broken_rcodes'] = 'SERVFAIL FORMERR BADVERS NOTIMP YXDOMAIN YXRRSET NXRRSET'
settings['serversm_soaquery_domain'] = 'localhost.'
settings['bind9_zone_count_tag'] = 'number of zones:'

# Administrative security role tag
settings['admin_sectag'] = 'Admin'
# Accept GET Method for JSON RPC request(s)
# Some old JSON RPC libraries might need this...
settings['jsonrpc_accept_get'] = False

# cmdline_engine
settings['zone_del_off_age'] = 1000 * 366 # days
settings['preconvert_float_settings'] += 'zone_del_off_age'

# zone_engine.py
settings['list_events_last_limit'] = 25

# zone_tool.py
# admin_group_list shifted to magcode.core.globals_
settings['restricted_mode_commands'] = 'clear_edit_lock create_zone copy_zone copy_zi delete_zone diff_zone_zi diff_zones disable_zone enable_zone edit_zone exit EOF help ls ls_deleted ls_reference lszi quit refresh_zone refresh_zone_ttl reset_zonesm record_query_db show_apex_ns show_config show_dms_status show_zi show_zone show_zone_byid show_zone_sectags show_zonesm show_zonesm_byid undelete_zone'
settings['wsgi_test_commands'] = 'create_zi_zone cancel_edit_zone rr_query_db set_zone_alt_sg show_zi_byid list_zone list_zone_deleted list_zi'
# Command log facility
settings['commands_not_to_syslog'] = 'help show EOF list quit exit rr ls'
settings['zone_tool_log_facility'] = 'local7'
settings['zone_tool_log_level'] = 'info'
# zone_tool rndc  and key file stuff
settings['config_template_dir'] = settings['config_dir'] + '/config-templates'
settings['rndc_header_template'] = settings['config_template_dir'] \
                                    + '/rndc.conf-header'
settings['rndc_server_template'] = settings['config_template_dir'] \
                                    + '/rndc.conf-server'
settings['rndc_conf_file'] = settings['var_lib_dir'] + '/rndc' + '/rndc.conf'
settings['rndc_conf_file_mode'] = '00644'
settings['server_admin_config_dir'] = settings['config_dir'] \
                                        + '/server-admin-config'
settings['tsig_key_template'] = settings['config_template_dir'] \
                                    + '/tsig.key'
settings['key_file_mode'] = '00640'
settings['key_file_owner'] = 'root'
settings['key_file_group'] = 'bind'
# zone_tool ping stuff
settings['oping_path'] = 'oping'
settings['oping_args'] = '-i 0.2 -c 5'

# auto reverse control settings
settings['auto_reverse'] = True
settings['auto_create_ipv4_ptr'] = False
settings['auto_create_ipv6_ptr'] = True
settings['preconvert_bool_settings'] += 'auto_reverse auto_create_ipv4_ptr auto_create_ipv6_ptr'


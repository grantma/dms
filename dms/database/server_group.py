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
Server Groups
"""


import io
import errno
import tempfile
from os.path import basename

from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref

from magcode.core.utility import get_numeric_setting
from magcode.core.database import *
import dms.database.server_sm
from dms.template_cache import read_template


@saregister
class ServerGroup(object):
    """
    Server Group 
    """
    _table = 'server_groups'
    
    @classmethod
    def _mapper_properties(class_):
        zone_sm_type = sql_types['ZoneSM']
        server_sm_type = sql_types['ServerSM']
        zone_cfg_type = sql_types['ZoneCfg']
        sg_table = sql_data['tables'][ServerGroup]
        zone_sm_table = sql_data['tables'][zone_sm_type]
        return {'zones': relationship(zone_sm_type, 
                            primaryjoin=(zone_sm_table.c.sg_id 
                                        == sg_table.c.get('id')),
                                    passive_deletes=True, lazy='dynamic'),
                'alt_zones': relationship(zone_sm_type, 
                            primaryjoin=(zone_sm_table.c.alt_sg_id 
                                        == sg_table.c.get('id')),
                                    passive_deletes=True, lazy='dynamic'),
                'servers': relationship(server_sm_type, passive_deletes=True,
                                    backref='sg'),
                'zone_cfg_entries': relationship(zone_cfg_type,
                                    passive_deletes=True,
                                    backref='sg'),
                            }

    def __init__(self, sg_name, config_dir, master_address, 
            master_alt_address):
        """
        Create an SG object
        """
        self.name = sg_name
        self.config_dir = config_dir
        self.master_address = master_address
        self.master_alt_address = master_alt_address

    def __eq__(self, other):
        if not other:
            return False
        return self.name == other.name

    def __ne__(self, other):
        if not other:
            return True
        return self.name != other.name

    def to_engine_brief(self, time_format=None):
        """
        Output server group attributes as JSON
        """
        config_dir = self.config_dir if self.config_dir \
                        else settings['server_config_dir']
        replica_sg = (True if hasattr(self, 'master_sm') 
                            and self.master_sm else False)
        return {'sg_id': self.id_, 'sg_name': self.name,
                'config_dir': config_dir,
                'master_address': self.master_address,
                'master_alt_address': self.master_alt_address,
                'replica_sg': replica_sg,
                'zone_count': self.zone_count}

    # Use assignment to fill out to_engine() method
    to_engine = to_engine_brief

    def get_include_dir(self):
        """
        Function to return include dir for SG
        """
        include_dir = settings['sg_config_dir'] + '/' + self.name
        return include_dir

    def get_include_file(self, server_type):
        """
        Function to return the include file path for a server type.
        """
        include_dir = settings['sg_config_dir'] + '/' + self.name
        include_file = include_dir + '/' + server_type + '.conf'
        return include_file

    def write_config(self, db_session, op_exc):
        """
        Write out all configuration files needed for a server group.
        """
        def write_zone_include(zone_sm):
            # Remove dot at end of zone name as this gives more
            # human literate filenames
            filler_name = zone_sm.name[:-1]  \
                    if zone_sm.name.endswith('.') \
                            else zone_sm.name

            filler = {'name': filler_name, 
                    'master': master_address}
            tmp_file.write(template % filler)
        
        replica_sg = (True if hasattr(self, 'master_sm') 
                            and self.master_sm else False)
        # Calculate master addresses
        if (self.master_address 
                    and self.master_address 
                    in settings['this_servers_addresses']):
                master_address = self.master_address
        elif (self.master_alt_address
                    and self.master_alt_address 
                    in settings['this_servers_addresses']):
                master_address = self.master_alt_address
        else:
            master_address = settings['master_dns_server']

        # Get list of server types in SG
        ServerSM = sql_types['ServerSM']       
        server_types = [s.server_type for s in self.servers]
        # sort|uniq the types list
        server_types = list(set(sorted(server_types)))
        if replica_sg:
            server_types = [ st + settings['server_replica_suffix'] 
                            for st in server_types ]
        db_query_slice = get_numeric_setting('db_query_slice', int)
        for server_type in server_types:
            include_dir = self.get_include_dir()
            include_file = self.get_include_file(server_type)
            if self.config_dir:
                # This allows us to override default template configuration
                # for say internal domains which IPV6 ULA/
                # IPV4 RFC1918 addressing
                template_file = (self.config_dir  + '/'
                                    + server_type + '.conf')
            else:
                template_file = (settings['server_config_dir'] + '/'
                                    + server_type + '.conf')
            try:
                # Make directory if it already does not exist
                # This is in here to avoid try: verbosity
                if not os.path.isdir(include_dir):
                    os.mkdir(include_dir)
                template = read_template(template_file)
                (fd, tmp_filename) = tempfile.mkstemp(
                            dir=include_dir,
                            prefix='.' + basename(include_file) + '-')
                tmp_file = io.open(fd, mode='wt')
                zone_sm_type = sql_types['ZoneSM']
                zone_count = 0
                if replica_sg:
                    # Master SG  - include all zones
                    query = db_session.query(zone_sm_type)
                    query = zone_sm_type.query_sg_is_configured(query)\
                                .yield_per(db_query_slice)
                    for zone_sm in query:
                        write_zone_include(zone_sm)
                        zone_count += 1
                        # Prevent Memory leaks...
                        del zone_sm
                else:
                    query = zone_sm_type.query_sg_is_configured(self.zones)\
                                .yield_per(db_query_slice)
                    for zone_sm in query:
                        write_zone_include(zone_sm)
                        zone_count += 1
                        # Prevent Memory leaks...
                        del zone_sm
                    query = zone_sm_type.query_sg_is_configured(
                                self.alt_zones)\
                                .yield_per(db_query_slice)
                    for zone_sm in query:
                        write_zone_include(zone_sm)
                        zone_count += 1
                        # Prevent Memory leaks...
                        del zone_sm
                tmp_file.close()
                # Rename tmp file into place so that replacement is atomic
                os.chmod(tmp_filename, int(settings['config_file_mode'],8))
                os.rename(tmp_filename, include_file)
                # Store zone_count for monitoring data input 
                self.zone_count = zone_count

            except (IOError, OSError) as exc:
                msg = ( "SG %s - '%s' - %s." 
                                % (self.name, exc.filename, exc.strerror))
                if exc.errno in (errno.ENOENT, errno.EPERM, errno.EACCES):
                    raise op_exc(msg)
                else:
                    raise exc
            except KeyError as exc:
                msg = ("SG %s - Invalid template key in template file %s - %s"
                        % (self.name, template_file, str(exc)))
                raise op_exc(msg)
            finally:
                # clean up if possible
                try:
                    os.unlink(tmp_filename)
                except:
                    pass
        return




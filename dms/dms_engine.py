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
Module to contain DMS Zone editing engine
"""

import json

import sqlalchemy.exc

from magcode.core import *
from magcode.core.database import sql_data
from magcode.core.wsgi.jsonrpc_server import *
from dms.zone_engine import ZoneEngine
from dms.exceptions import DMSError
from dms.exceptions import DBReadOnlyError
from dms.exceptions import ZoneHasNoSOARecord 


class DMSEngine(ZoneEngine):
    """
    Zone Editing Engine for use with the dms daemon.
    """

    def list_zone_helpdesk(self, names=None, reference=None, 
            include_deleted=False, toggle_deleted=False, include_disabled=True):
        """
        Help desk privilege list_zone()
        """
        return self._list_zone(names=names, reference=reference, 
                include_deleted=include_deleted, toggle_deleted=toggle_deleted,
                include_disabled=include_disabled)

    def update_zone_helpdesk(self, name, zi_data, login_id, 
                                edit_lock_token=None):
        """
        Update a zone with admin privilege
        """
        return self._update_zone(name, zi_data, login_id, edit_lock_token, 
                 helpdesk_privilege=True)
    
    def update_zone_text_helpdesk(self, name, zi_text, login_id, 
                            edit_lock_token=None):
        """
        Update a zone with admin privilege
        """
        return self._update_zone_text(name, zi_text, login_id, 
                            edit_lock_token, helpdesk_privilege=True)

    def update_zone(self, name, zi_data, login_id, edit_lock_token=None):
        """
        Update a zone with no privileges
        """
        return self._update_zone(name, zi_data, login_id, edit_lock_token)

    def update_zone_text(self, name, zi_text, login_id, edit_lock_token=None):
        """
        Update a zone with admin privilege
        """
        return self._update_zone_text(name, zi_text, login_id, edit_lock_token)

    def create_zone_helpdesk(self, name, login_id, zi_data=None, edit_lock=None,
            auto_dnssec=None, nsec3=None, inc_updates=None, 
            reference=None, sg_name=None):
        """
        Create a zone with admin privilege
        """
        return self._create_zone(name, zi_data, login_id, edit_lock=edit_lock,
                auto_dnssec=auto_dnssec, nsec3=nsec3, inc_updates=inc_updates, 
                reference=reference, sg_name=sg_name,
                use_apex_ns=None, helpdesk_privilege=True)
    

    def load_zone_helpdesk(self, name, login_id, zi_text, edit_lock=None,
            auto_dnssec=None, nsec3=None, inc_updates=None, 
            reference=None, sg_name=None):
        """
        Create a zone from a zone text blob with admin privilege
        """
        return self._load_zone(name, zi_text, login_id, edit_lock=edit_lock,
                auto_dnssec=auto_dnssec, nsec3=nsec3, inc_updates=inc_updates, 
                reference=reference, sg_name=sg_name,
                use_apex_ns=None, helpdesk_privilege=True)
    
    def load_zi_helpdesk(self, name, login_id, zi_text):
        """
        Load a zi text blob into a zone.  Help desk version
        """
        return self._load_zi(name, zi_text, login_id, helpdesk_privilege=True)

    def create_zone(self, name, reference, login_id, zi_data=None):
        """
        Create a zone with no privileges

        Note: inc_updates hard-wired here to True
        """
        return self._create_zone(name, zi_data, use_apex_ns=None,
                edit_lock=None, auto_dnssec=None, nsec3=None, inc_updates=True,
                reference=reference, login_id=login_id)
    
    def load_zone(self, name, reference, login_id, zi_text):
        """
        Load a zone from a zi_text blob. Customer version
        """
        return self._load_zone(name, zi_text, use_apex_ns=None,
                edit_lock=None, auto_dnssec=None, nsec3=None, inc_updates=True,
                reference=reference, login_id=login_id)

    def load_zi(self, name, login_id, zi_text):
        """
        Load a zi_text blob into a zone. Customer version
        """
        return self._load_zi(name, zi_text, login_id)

    def copy_zone_helpdesk(self, src_name, name, login_id, zi_id=None, 
                edit_lock=None, auto_dnssec=None,
                nsec3=None, inc_updates=None, reference=None, sg_name=None,
                sectags=None):
        """
        Copy a zone with helpdesk privilege
        """
        return self._create_zone(name, src_name=src_name, src_zi_id=zi_id,
                edit_lock=edit_lock, 
                auto_dnssec=auto_dnssec, nsec3=nsec3, inc_updates=inc_updates, 
                reference=reference, sg_name=sg_name, login_id=login_id, 
                zi_data=None,
                helpdesk_privilege=True)

    def copy_zone(self, src_name, name, login_id, zi_id=None):
        """
        Copy a zone
        """
        return self._create_zone(name, src_name=src_name, src_zi_id=zi_id, 
                                login_id=login_id, zi_data=None)

    def delete_zone_helpdesk(self, name):
        """
        Delete a zone helpdesk front end
        """
        self._delete_zone(name, force=True) 

    def set_zone_helpdesk(self, name, **kwargs): 
        for arg in kwargs:
            if arg not in ('edit_lock', 'auto_dnssec',):
                raise InvalidParamsJsonRpcError("Argument '%s' not supported."
                                                    % arg)
        return self._set_zone(name, **kwargs)
    
    def update_rrs(self, name, update_data, update_type, login_id):
        """
        Incremental updates, normal customer api privilege
        """
        return self._update_rrs(name, update_data, update_type, login_id)

    def update_rrs_helpdesk(self, name, update_data, update_type, login_id):
        """
        Incremental updates, help desk privilege
        """
        return self._update_rrs(name, update_data, update_type, login_id,
                                helpdesk_privilege=True)

    # Test code for exception raising
    #def list_zone(self, *args):
    #   raise ZoneHasNoSOARecord(args[0])

class BaseJsonRpcContainer(object):
    
    """
    Implements mapping between JSON RPC method names, and the appropriate
    engine methods.  Each application should descend from this class, and 
    define methods, in a class called 'JSONRpcCaller'.  
    The application function will create an instance of that class, 
    """
    def __init__(self, sectag, time_format=None):
        self._engine = DMSEngine(time_format=time_format, sectag_label=sectag)

    def _exc_rollback(self):
        """
        Cleanup db_session if there is an exception!
        """
        self._engine.rollback()

class DmsJsonRpcServer(object):
    """
    DMS JSON RPC Server class

    Creates a callable object that has the RPC call security container class
    and sectag as attributes.  This allows per request initialisation of
    SQL Alchemy session etc.
    """
    def __init__(self, rpc_container_class, sectag, time_format=None):
        self.rpc_container_class = rpc_container_class
        self.sectag = sectag
        self.time_format = time_format

    def __call__(self, environ, start_response, requests):
            
        # Initialise DB and engine object
        rpc_container = self.rpc_container_class(
                                                time_format=self.time_format, 
                                                sectag=self.sectag)
        
        # Process requests
        response = []
        for request in requests:
            # Process request
            call_id = request.get('id')
            if not call_id:
                # Skip any notifications at the moment
                continue
            params = request.get('params')
            if not hasattr(rpc_container, request['method']):
                response.append({'jsonrpc': '2.0', 'id':call_id,
                        'error': { 'code': JSONRPC_METHOD_NOT_FOUND,
                        'message': jsonrpc_errors[JSONRPC_METHOD_NOT_FOUND]}})
            # Double nested EXC so that standard exception processing
            # happens for PostgresQL in Read Only hot-standby.  This is lowest
            # common point where this can be trapped properly.
            try:
                try:
                    # Sort out params  - needs to be feed in correctly as
                    # python *args or **kwargs depending wether it is a JSON
                    # array or JSON object
                    if isinstance(params, list):
                        result = getattr(rpc_container,
                                    request['method'])(*params)
                    elif isinstance(params, dict):
                        result = getattr(rpc_container, 
                                    request['method'])(**params)
                    else:
                        result = getattr(rpc_container, request['method'])()
                    response.append({'id': call_id, 'result': result,
                                    'jsonrpc': '2.0'})
                except sqlalchemy.exc.InternalError as exc:
                    raise DBReadOnlyError(str(exc))
            except BaseJsonRpcError as exc:
                rpc_container._exc_rollback() 
                data = exc.data
                data.update({'exception_message': str_exc(exc),
                                'exception_type': str_exc_type(exc)})
                if jsonrpc_error_stack_trace():
                    data['stack_trace'] = format_exc()
                response.append({'jsonrpc': '2.0', 'id':call_id,
                        'error': { 'code': exc.jsonrpc_error,
                        'message': str(exc),
                        'data': data}})
            except (TypeError,AttributeError) as exc:
                rpc_container._exc_rollback() 
                data = {'exception_message': str_exc(exc),}
                if jsonrpc_error_stack_trace():
                    data['stack_trace'] = format_exc() 
                response.append({'jsonrpc': '2.0', 'id':call_id,
                        'error': { 'code': JSONRPC_INVALID_PARAMS,
                        'message': jsonrpc_errors[JSONRPC_INVALID_PARAMS],
                        'data': data}})
        return response


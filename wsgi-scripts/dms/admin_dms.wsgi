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

# Hack so that we can run python3.2 on this with PDB to sort out 
# any import problems...
import sys
sys.path.insert(0, '/usr/share/dms')

from magcode.core.wsgi import *
from magcode.core.wsgi.jsonrpc_server import WsgiJsonRpcServer
from dms.dms_engine import BaseJsonRpcContainer
from dms.dms_engine import DmsJsonRpcServer


# Initialise environment
wsgi_setup()

# Engine arguments passed through BaseRpcContainer.__init__() call stack
# set security tag
sectag = settings['admin_sectag']
# set strftime() format
time_format = None

# RPC method/permissions container class
# This should be set to a string that is also configured into DMS database
class JsonRpcContainer(BaseJsonRpcContainer):
    """
    Implement JsonRpcCaller for Administrative DMI client
    """
    def list_zone(self, **kwargs):
        return self._engine.list_zone_admin(**kwargs)

    def list_zi(self, **kwargs):
        return self._engine.list_zi(**kwargs)

    def show_zone(self, **kwargs):
        return self._engine.show_zone(**kwargs)

    def show_zone_text(self, **kwargs):
        return self._engine.show_zone_text(**kwargs)

    def show_zone_byid(self, **kwargs):
        return self._engine.show_zone_byid(**kwargs)

    def show_zi(self, **kwargs):
        return self._engine.show_zi(**kwargs)

    def show_zi_byid(self, **kwargs):
        return self._engine.show_zi_byid(**kwargs)

    def create_zone(self, **kwargs):
        return self._engine.create_zone_admin(**kwargs)

    def load_zone(self, **kwargs):
        return self._engine.load_zone_admin(**kwargs)

    def load_zi(self, **kwargs):
        return self._engine.load_zi_admin(**kwargs)

    def delete_zone(self, **kwargs):
        return self._engine.delete_zone_admin(**kwargs)
    
    def set_zone(self, **kwargs):
        return self._engine.set_zone_admin(**kwargs)

    def disable_zone(self, **kwargs):
        return self._engine.disable_zone(**kwargs)

    def enable_zone(self, **kwargs):
        return self._engine.enable_zone(**kwargs)
    
    def destroy_zone(self, **kwargs):
        return self._engine.destroy_zone(**kwargs)
    
    def undelete_zone(self, **kwargs):
        return self._engine.undelete_zone(**kwargs)

    def copy_zone(self, **kwargs):
        return self._engine.copy_zone_admin(**kwargs)
    
    def copy_zi(self, **kwargs):
        return self._engine.copy_zi(**kwargs)

    def delete_zi(self, **kwargs):
        return self._engine.delete_zi(**kwargs)

    def edit_zone(self, **kwargs):
        return self._engine.edit_zone(**kwargs)

    def tickle_editlock(self, **kwargs):
        return self._engine.tickle_editlock(**kwargs)

    def cancel_edit_zone(self, **kwargs):
        return self._engine.cancel_edit_zone(**kwargs)

    def update_zone(self, **kwargs):
        return self._engine.update_zone_admin(**kwargs)

    def update_zone_text(self, **kwargs):
        return self._engine.update_zone_text_admin(**kwargs)

    def add_zone_sectag(self, **kwargs):
        return self._engine.add_zone_sectag(**kwargs)

    def delete_zone_sectag(self, **kwargs):
        return self._engine.delete_zone_sectag(**kwargs)

    def show_sectags(self, **kwargs):
        return  self._engine.show_sectags(**kwargs)

    def show_zone_sectags(self, **kwargs):
        return self._engine.show_zone_sectags(**kwargs)

    def replace_zone_sectags(self, **kwargs):
        return self._engine.replace_zone_sectags(**kwargs)

    def sign_zone(self, **kwargs):
        return self._engine.sign_zone(**kwargs)

    def load_keys(self, **kwargs):
        return self._engine.load_keys(**kwargs)

    def refresh_zone(self, **kwargs):
        return self._engine.refresh_zone(**kwargs)

    def reset_zone(self, **kwargs):
        return self._engine.reset_zone(**kwargs)

    def refresh_zone_ttl(self, **kwargs):
        return self._engine.refresh_zone_ttl(**kwargs)

    def show_configsm(self):
        return self._engine.show_configsm()

    def create_reference(self, **kwargs):
        return self._engine.create_reference(**kwargs)

    def delete_reference(self, **kwargs):
        return self._engine.delete_reference(**kwargs)

    def rename_reference(self, **kwargs):
        return self._engine.rename_reference(**kwargs)

    def list_reference(self, *references):
        return self._engine.delete_reference(*references)

    def set_zone_reference(self, **kwargs):
        return self._engine.set_zone_reference(**kwargs)

    def rr_query_db(self, **kwargs):
        return self._engine.rr_query_db(**kwargs)

    def update_rrs(self, **kwargs):
        return self._engine.update_rrs_admin(**kwargs)

    def set_zone_sg(self, **kwargs):
        return self._engine.set_zone_sg(**kwargs)
    
    def set_zone_alt_sg(self, **kwargs):
        return self._engine.set_zone_alt_sg(**kwargs)
    
    def list_sg(self):
        return self._engine.list_sg()




# Create application instance - Object created is a callable function object
# Python magic __call__ methods!
jsonrpc_application = DmsJsonRpcServer(rpc_container_class=JsonRpcContainer,
                                    sectag=sectag, time_format=time_format)
application = WsgiJsonRpcServer(jsonrpc_application)

# Debug stuff below here
def main(*args):
    """
    Test and debug routine
    """
    # import pdb; pdb.set_trace()
    # Initialise DB and engine object
    rpc_container = JsonRpcContainer(sectag=sectag, time_format=time_format)
    result = getattr(rpc_container, args[0])()
    return result

if __name__ == '__main__':
    main(*sys.argv[1:])

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
sectag = 'HOSTED'
# set strftime() format
time_format = None

# RPC method/permissions container class
# This should be set to a string that is also configured into DMS database
class JsonRpcContainer(BaseJsonRpcContainer):
    """
    Implement JsonRpcCaller for Administrative DMI client
    """
    def list_zone(self, **kwargs):
        return self._engine.list_zone(*kwargs)

    def edit_zone(self, **kwargs):
        return self._engine.edit_zone(**kwargs)

    def tickle_editlock(self, **kwargs):
        return self._engine.tickle_editlock(**kwargs)

    def cancel_edit_zone(self, **kwargs):
        return self._engine.cancel_edit_zone(**kwargs)

    def update_zone(self, **kwargs):
        return self._engine.update_zone_helpdesk(**kwargs)

    def show_zone(self, **kwargs):
        return self._engine.show_zone(**kwargs)

    def list_zi(self, **kwargs):
        return self._engine.list_zi(**kwargs)

    def create_zone(self, **kwargs):
        return self._engine.create_zone_helpdesk(**kwargs)

    def delete_zone(self, **kwargs):
        return self._engine.delete_zone_helpdesk(**kwargs)
    
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

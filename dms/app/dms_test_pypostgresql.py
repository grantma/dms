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

Program implemented by subclassing magcode.core.process.Process, and 
replacing the main() method.
"""

import os
import sys

from magcode.core.process import Process
from magcode.core.globals_ import *
from magcode.core.database import *
from dms.globals_ import *


settings['config_section'] = 'DEFAULT'

@saregister
class TestPyPostgresql(object):
    """
    Reference object for tagging data in database with things like customer IDs.
    """
    _table = 'test_pypostgresql'

    def __init__(self, name, inet='192.168.1.1/24', cidr='192.168.110.0/24', 
                    macaddr='de:ad:00:be:00:ef' ):
        """
        Initialize a Test Object
        """
        self.name = name
        self.inet = inet
        self.cidr = cidr
        self.macaddr = macaddr



class DmsTestPyPostgresqlApp(Process):
    """
    Process Main Daemon class
    """
    
#    def parse_argv_left(self, argv_left):
#        """
#        Handle any arguments left after processing all switches
#
#        Override in application if needed.
#        """
#        if (len(argv_left) == 0):
#            self.usage_short()
#            sys.exit(os.EX_USAGE)
#        
#        self.argv_left = argv_left
#
    def main_process(self):
        """Main process for dms_test_pypostgresql
        """
        # Connect to database, intialise SQL Alchemy
        setup_sqlalchemy()
        db_session = sql_data['scoped_session_class']()

        import pdb; pdb.set_trace()

        sys.exit(os.EX_OK)





if (__name__ is "__main__"):
    exit_code = DmsTestPyPostgresqlApp(sys.argv, len(sys.argv))
    sys.exit(exit_code)


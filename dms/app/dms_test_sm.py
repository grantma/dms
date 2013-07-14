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
import pwd
import time
import json

from magcode.core.process import Process
from magcode.core.globals_ import *
from magcode.core.database import *
from magcode.core.database.event import Event
from magcode.core.database.process_sm import new_process
from dms.globals_ import *


settings['config_section'] = 'DEFAULT'

class DmsTestApp(Process):
    """
    Process Main Daemon class
    """
    
    def parse_argv_left(self, argv_left):
        """
        Handle any arguments left after processing all switches

        Override in application if needed.
        """
        if (len(argv_left) == 0):
            self.usage_short()
            sys.exit(os.EX_USAGE)
        
        self.argv_left = argv_left

    def main_process(self):
        """Main process for dms-test-sm
        """
        # Connect to database, intialise SQL Alchemy
        setup_sqlalchemy()
        executable = self.argv_left[0]
        name = os.path.basename(executable)
        db_session = sql_data['scoped_session_class']()

        new_process(db_session=db_session, commit=True, name=name, exec_path=executable, 
                argv = self.argv_left, stdin="GUMBOOT\n", 
                success_event=Event(),
                success_event_kwargs={'role_id': 4, 'zone_id': 1000})
        sys.exit(os.EX_OK)





if (__name__ is "__main__"):
    exit_code = DmsTestApp(sys.argv, len(sys.argv))
    sys.exit(exit_code)


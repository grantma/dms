--
-- Copyright (c) Net24 Limited, Christchurch, New Zealand 2011-2012
--       and     Voyager Internet Ltd, New Zealand, 2012-2013
--
--    This file is part of py-magcode-core.
--
--    Py-magcode-core is free software: you can redistribute it and/or modify
--    it under the terms of the GNU  General Public License as published
--    by the Free Software Foundation, either version 3 of the License, or
--    (at your option) any later version.
--
--    Py-magcode-core is distributed in the hope that it will be useful,
--    but WITHOUT ANY WARRANTY; without even the implied warranty of
--    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
--    GNU  General Public License for more details.
--
--    You should have received a copy of the GNU  General Public License
--    along with py-magcode-core.  If not, see <http://www.gnu.org/licenses/>.
--
CREATE OR REPLACE FUNCTION sm_servers_update_mtime_column() 
        RETURNS TRIGGER AS '
  BEGIN
    NEW.mtime = NOW();
    RETURN NEW;
  END;
' LANGUAGE 'plpgsql';

DROP TRIGGER sm_servers_update_mtime ON sm_servers;
CREATE TRIGGER sm_servers_update_mtime BEFORE UPDATE on sm_servers
	FOR EACH ROW
	WHEN (OLD.name IS DISTINCT FROM NEW.name 
		OR OLD.address IS DISTINCT FROM NEW.address
		OR OLD.server_type is DISTINCT FROM NEW.server_type)
       	EXECUTE PROCEDURE sm_servers_update_mtime_column();

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
CREATE OR REPLACE FUNCTION update_mtime_column() 
        RETURNS TRIGGER AS '
  BEGIN
    IF (OLD.mtime = NEW.mtime) THEN
      NEW.mtime = NOW();
    END IF;
    RETURN NEW;
  END;
' LANGUAGE 'plpgsql';

DROP TRIGGER update_mtime ON zone_instances;
CREATE TRIGGER update_mtime BEFORE UPDATE on zone_instances
	FOR EACH ROW EXECUTE PROCEDURE update_mtime_column();

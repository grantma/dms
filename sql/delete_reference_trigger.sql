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
CREATE OR REPLACE FUNCTION delete_associated_reference() RETURNS trigger AS $delete_associated_reference$
DECLARE
	ref_count bigint := -1;
BEGIN
	-- Deletes references that are not used anymore
	IF OLD.ref_id IS NULL THEN
		RETURN NULL;
	END IF;
	ref_count := count(id) FROM sm_zone WHERE OLD.ref_id = ref_id;
	IF ref_count = 0 THEN
		DELETE from reference WHERE OLD.ref_id = id;
	END IF;
	RETURN NULL;
END;
$delete_associated_reference$ LANGUAGE plpgsql;

DROP TRIGGER delete_associated_reference ON sm_zone;
CREATE TRIGGER delete_associated_reference AFTER DELETE on sm_zone
	FOR EACH ROW EXECUTE PROCEDURE delete_associated_reference();

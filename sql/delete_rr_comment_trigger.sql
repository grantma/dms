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
CREATE OR REPLACE FUNCTION delete_associated_comment() RETURNS trigger AS $delete_associated_comment$
DECLARE
	rrc_count bigint := -1;
	cg_count bigint := -1;
BEGIN
	-- Deletes a RR Comment that is not used anymore
	IF OLD.comment_rr_id IS NOT NULL THEN
		rrc_count := count(id) FROM resource_records
					WHERE OLD.comment_rr_id = comment_rr_id;
		IF rrc_count = 0 THEN
			DELETE FROM rr_comments
				WHERE OLD.comment_rr_id = id;
		END IF;	
	END IF;
	IF OLD.comment_group_id IS NOT NULL THEN
		cg_count := count(id) FROM resource_records
					WHERE OLD.comment_group_id = comment_group_id;
		IF cg_count = 0 THEN
			DELETE FROM rr_comments 
					WHERE OLD.comment_group_id = id;
		END IF;
	END IF;
	RETURN NULL; -- result is ignored as this is an AFTER trigger
END;
$delete_associated_comment$ LANGUAGE plpgsql;

DROP TRIGGER delete_associated_comment ON resource_records;
CREATE TRIGGER delete_associated_comment AFTER DELETE on resource_records
	FOR EACH ROW EXECUTE PROCEDURE delete_associated_comment();

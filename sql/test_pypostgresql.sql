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

--
-- PostgreSQL database dump
--

SET statement_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;

SET search_path = public, pg_catalog;

ALTER TABLE ONLY public.test_pypostgresql DROP CONSTRAINT test_pypostgresql_pkey;
ALTER TABLE public.test_pypostgresql ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE public.test_pypostgresql_id_seq;
DROP TABLE public.test_pypostgresql;
SET search_path = public, pg_catalog;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: test_pypostgresql; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE test_pypostgresql (
    id bigint NOT NULL,
    name character varying(1024),
    inet inet,
    cidr cidr,
    macaddr macaddr
);


ALTER TABLE public.test_pypostgresql OWNER TO pgsql;

--
-- Name: test_pypostgresql_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE test_pypostgresql_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.test_pypostgresql_id_seq OWNER TO pgsql;

--
-- Name: test_pypostgresql_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE test_pypostgresql_id_seq OWNED BY test_pypostgresql.id;


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE test_pypostgresql ALTER COLUMN id SET DEFAULT nextval('test_pypostgresql_id_seq'::regclass);


--
-- Name: test_pypostgresql_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY test_pypostgresql
    ADD CONSTRAINT test_pypostgresql_pkey PRIMARY KEY (id);


--
-- Name: test_pypostgresql; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE test_pypostgresql FROM PUBLIC;
REVOKE ALL ON TABLE test_pypostgresql FROM pgsql;
GRANT ALL ON TABLE test_pypostgresql TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE test_pypostgresql TO dms;


--
-- Name: test_pypostgresql_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE test_pypostgresql_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE test_pypostgresql_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE test_pypostgresql_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE test_pypostgresql_id_seq TO dms;


--
-- PostgreSQL database dump complete
--


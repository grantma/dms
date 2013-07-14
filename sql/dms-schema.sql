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

--
-- Name: dms; Type: COMMENT; Schema: -; Owner: pgsql
--

COMMENT ON DATABASE dms IS 'Net24 Domain Management System Database';


--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


SET search_path = public, pg_catalog;

--
-- Name: delete_associated_comment(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION delete_associated_comment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.delete_associated_comment() OWNER TO pgsql;

--
-- Name: delete_associated_reference(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION delete_associated_reference() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


ALTER FUNCTION public.delete_associated_reference() OWNER TO pgsql;

--
-- Name: delete_associated_rr(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION delete_associated_rr() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
	BEGIN
		-- Deletes Resource Records that are not guarded by a FOREIGN KEY constraint
		DELETE FROM resource_records where OLD.rr_id = resource_records.id;
		RETURN NULL; -- result is ignored as this is an AFTER trigger
	EXCEPTION
		WHEN foreign_key_violation THEN
			-- RR is still referenced.
			RETURN NULL;
	END;
$$;


ALTER FUNCTION public.delete_associated_rr() OWNER TO pgsql;

--
-- Name: sm_servers_update_mtime_column(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION sm_servers_update_mtime_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
  BEGIN
    NEW.mtime = NOW();
    RETURN NEW;
  END;
$$;


ALTER FUNCTION public.sm_servers_update_mtime_column() OWNER TO pgsql;

--
-- Name: update_mtime_column(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION update_mtime_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
  BEGIN
    IF (OLD.mtime = NEW.mtime) THEN
      NEW.mtime = NOW();
    END IF;
    RETURN NEW;
  END;
$$;


ALTER FUNCTION public.update_mtime_column() OWNER TO pgsql;

--
-- Name: zone_update_mtime_column(); Type: FUNCTION; Schema: public; Owner: pgsql
--

CREATE FUNCTION zone_update_mtime_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
  BEGIN
    NEW.mtime = NOW();
    RETURN NEW;
  END;
$$;


ALTER FUNCTION public.zone_update_mtime_column() OWNER TO pgsql;

--
-- Name: dbs_error_log_error_id; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE dbs_error_log_error_id
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.dbs_error_log_error_id OWNER TO pgsql;

--
-- Name: dbs_event_log_event_id; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE dbs_event_log_event_id
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1;


ALTER TABLE public.dbs_event_log_event_id OWNER TO pgsql;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: dbt_error_log; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE dbt_error_log (
    error_id integer DEFAULT nextval(('"dbs_error_log_error_id"'::text)::regclass) NOT NULL,
    inner_error_id integer,
    logtime timestamp without time zone DEFAULT now() NOT NULL,
    code character varying(32) NOT NULL,
    code_resolved character varying(64) NOT NULL,
    severity smallint NOT NULL,
    message text NOT NULL,
    location character varying(256) NOT NULL,
    trace text,
    info text,
    environment text
);


ALTER TABLE public.dbt_error_log OWNER TO pgsql;

--
-- Name: TABLE dbt_error_log; Type: COMMENT; Schema: public; Owner: pgsql
--

COMMENT ON TABLE dbt_error_log IS 'DMS Event Log table';


--
-- Name: dbt_event_log; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE dbt_event_log (
    event_id integer DEFAULT nextval(('"dbs_event_log_event_id"'::text)::regclass) NOT NULL,
    event_date timestamp without time zone DEFAULT now() NOT NULL,
    event_code character varying(4) NOT NULL,
    event_text text,
    client_id integer,
    username character varying(32),
    zone_name character varying(255)
);


ALTER TABLE public.dbt_event_log OWNER TO pgsql;

--
-- Name: TABLE dbt_event_log; Type: COMMENT; Schema: public; Owner: pgsql
--

COMMENT ON TABLE dbt_event_log IS 'DMS Event Log';


--
-- Name: reference; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE reference (
    id bigint NOT NULL,
    reference character varying(1024)
);


ALTER TABLE public.reference OWNER TO pgsql;

--
-- Name: reference_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE reference_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reference_id_seq OWNER TO pgsql;

--
-- Name: reference_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE reference_id_seq OWNED BY reference.id;


--
-- Name: resource_records; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE resource_records (
    id bigint NOT NULL,
    label character varying(1024),
    type character varying(20),
    ttl character varying(20),
    class character varying(20),
    comment_group_id bigint,
    zi_id bigint,
    rdata text,
    zone_ttl character varying(20),
    comment_rr_id bigint,
    lock_ptr boolean DEFAULT false,
    disable boolean DEFAULT false,
    ref_id bigint,
    update_op character varying(60),
    ug_id bigint,
    track_reverse boolean DEFAULT false
);


ALTER TABLE public.resource_records OWNER TO pgsql;

--
-- Name: resource_records_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE resource_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.resource_records_id_seq OWNER TO pgsql;

--
-- Name: resource_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE resource_records_id_seq OWNED BY resource_records.id;


--
-- Name: reverse_networks; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE reverse_networks (
    id bigint NOT NULL,
    network cidr,
    zone_id bigint
);


ALTER TABLE public.reverse_networks OWNER TO pgsql;

--
-- Name: reverse_networks_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE reverse_networks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reverse_networks_id_seq OWNER TO pgsql;

--
-- Name: reverse_networks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE reverse_networks_id_seq OWNED BY reverse_networks.id;


--
-- Name: rr_comments; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE rr_comments (
    id bigint NOT NULL,
    comment character varying(1024),
    tag character varying(60)
);


ALTER TABLE public.rr_comments OWNER TO pgsql;

--
-- Name: rr_comments_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE rr_comments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.rr_comments_id_seq OWNER TO pgsql;

--
-- Name: rr_comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE rr_comments_id_seq OWNED BY rr_comments.id;


--
-- Name: server_groups; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE server_groups (
    id bigint NOT NULL,
    name character varying(60),
    config_dir character varying(1024),
    zone_count bigint DEFAULT 0,
    master_address inet,
    master_alt_address inet
);


ALTER TABLE public.server_groups OWNER TO pgsql;

--
-- Name: server_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE server_groups_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.server_groups_id_seq OWNER TO pgsql;

--
-- Name: server_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE server_groups_id_seq OWNED BY server_groups.id;


--
-- Name: sm_event_queue; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE sm_event_queue (
    id bigint NOT NULL,
    event_type character varying(80) DEFAULT (NOT NULL::boolean),
    state character varying(60) DEFAULT 'NEW'::character varying NOT NULL,
    scheduled timestamp with time zone DEFAULT now(),
    processed timestamp with time zone,
    parameters text,
    results text,
    zone_id bigint,
    created timestamp with time zone DEFAULT now(),
    result_code integer,
    server_id bigint,
    master_id bigint
);


ALTER TABLE public.sm_event_queue OWNER TO pgsql;

--
-- Name: sm_event_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE sm_event_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sm_event_queue_id_seq OWNER TO pgsql;

--
-- Name: sm_event_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE sm_event_queue_id_seq OWNED BY sm_event_queue.id;


--
-- Name: sm_master; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE sm_master (
    id bigint NOT NULL,
    state character varying(60),
    hold_start timestamp with time zone,
    hold_sg bigint,
    hold_stop timestamp with time zone,
    hold_sg_name character varying(60),
    replica_sg_id bigint,
    master_server_id bigint,
    master_hostname character varying(1024)
);


ALTER TABLE public.sm_master OWNER TO pgsql;

--
-- Name: sm_master_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE sm_master_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sm_master_id_seq OWNER TO pgsql;

--
-- Name: sm_master_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE sm_master_id_seq OWNED BY sm_master.id;


--
-- Name: sm_process; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE sm_process (
    id bigint NOT NULL,
    name character varying(60) NOT NULL,
    state character varying(60) DEFAULT 'START'::character varying NOT NULL,
    exit_code integer,
    result_code integer,
    exec_path character varying(1024),
    argv text,
    stdin text,
    stdout text,
    stderr text,
    start timestamp with time zone,
    finish timestamp with time zone,
    pid integer,
    env text,
    cwd character varying(1024),
    success_event character varying(80),
    success_event_kwargs text
);


ALTER TABLE public.sm_process OWNER TO pgsql;

--
-- Name: sm_process_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE sm_process_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sm_process_id_seq OWNER TO pgsql;

--
-- Name: sm_process_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE sm_process_id_seq OWNED BY sm_process.id;


--
-- Name: sm_servers; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE sm_servers (
    id bigint NOT NULL,
    name character varying(1024),
    state character varying(60),
    server_type character varying(60),
    sg_id bigint,
    address inet,
    ctime timestamp with time zone DEFAULT now(),
    mtime timestamp with time zone,
    last_reply timestamp with time zone,
    ssh_address inet,
    zone_count bigint,
    retry_msg text
);


ALTER TABLE public.sm_servers OWNER TO pgsql;

--
-- Name: sm_servers_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE sm_servers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sm_servers_id_seq OWNER TO pgsql;

--
-- Name: sm_servers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE sm_servers_id_seq OWNED BY sm_servers.id;


--
-- Name: sm_zone; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE sm_zone (
    id bigint NOT NULL,
    name character varying(1024),
    zi_id bigint,
    state character varying(60),
    soa_serial bigint,
    zone_type character varying(20),
    use_apex_ns boolean DEFAULT true,
    edit_lock boolean DEFAULT false,
    edit_lock_token bigint,
    auto_dnssec boolean DEFAULT false,
    sg_id bigint,
    lock_state character varying(60),
    deleted_start timestamp with time zone,
    ref_id bigint,
    nsec3 boolean DEFAULT false,
    zi_candidate_id bigint,
    zone_files boolean DEFAULT false,
    alt_sg_id bigint,
    ctime timestamp with time zone DEFAULT now(),
    mtime timestamp with time zone DEFAULT now(),
    inc_updates boolean DEFAULT false,
    locked_by character varying(1024),
    locked_at timestamp with time zone
);


ALTER TABLE public.sm_zone OWNER TO pgsql;

--
-- Name: COLUMN sm_zone.soa_serial; Type: COMMENT; Schema: public; Owner: pgsql
--

COMMENT ON COLUMN sm_zone.soa_serial IS 'SOA RR serial number';


--
-- Name: sm_zone_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE sm_zone_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.sm_zone_id_seq OWNER TO pgsql;

--
-- Name: sm_zone_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE sm_zone_id_seq OWNED BY sm_zone.id;


--
-- Name: systemevents; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE systemevents (
    id integer NOT NULL,
    customerid bigint,
    receivedat timestamp without time zone,
    devicereportedtime timestamp without time zone,
    facility smallint,
    priority smallint,
    fromhost character varying(60),
    message text,
    ntseverity integer,
    importance integer,
    eventsource character varying(60),
    eventuser character varying(60),
    eventcategory integer,
    eventid integer,
    eventbinarydata text,
    maxavailable integer,
    currusage integer,
    minusage integer,
    maxusage integer,
    infounitid integer,
    syslogtag character varying(60),
    eventlogtype character varying(60),
    genericfilename character varying(60),
    systemid integer,
    server_id bigint,
    zone_id bigint
);


ALTER TABLE public.systemevents OWNER TO pgsql;

--
-- Name: TABLE systemevents; Type: COMMENT; Schema: public; Owner: pgsql
--

COMMENT ON TABLE systemevents IS 'rsyslog table for logging properties';


--
-- Name: systemevents_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE systemevents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.systemevents_id_seq OWNER TO pgsql;

--
-- Name: systemevents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE systemevents_id_seq OWNED BY systemevents.id;


--
-- Name: systemeventsproperties; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE systemeventsproperties (
    id integer NOT NULL,
    systemeventid integer,
    paramname character varying(255),
    paramvalue text
);


ALTER TABLE public.systemeventsproperties OWNER TO pgsql;

--
-- Name: systemeventsproperties_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE systemeventsproperties_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.systemeventsproperties_id_seq OWNER TO pgsql;

--
-- Name: systemeventsproperties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE systemeventsproperties_id_seq OWNED BY systemeventsproperties.id;


--
-- Name: update_groups; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE update_groups (
    id bigint NOT NULL,
    update_type character varying(60),
    zone_id bigint,
    ptr_only boolean DEFAULT false,
    sectag character varying(60),
    change_by character varying(1024)
);


ALTER TABLE public.update_groups OWNER TO pgsql;

--
-- Name: update_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE update_groups_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.update_groups_id_seq OWNER TO pgsql;

--
-- Name: update_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE update_groups_id_seq OWNED BY update_groups.id;


--
-- Name: zone_cfg; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE zone_cfg (
    id integer NOT NULL,
    key character varying(40),
    value character varying(1024),
    sg_id bigint
);


ALTER TABLE public.zone_cfg OWNER TO pgsql;

--
-- Name: zone_cfg_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE zone_cfg_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.zone_cfg_id_seq OWNER TO pgsql;

--
-- Name: zone_cfg_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE zone_cfg_id_seq OWNED BY zone_cfg.id;


--
-- Name: zone_instances; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE zone_instances (
    id bigint NOT NULL,
    zone_id bigint,
    ctime timestamp with time zone DEFAULT now(),
    mtime timestamp with time zone DEFAULT now(),
    soa_serial bigint,
    soa_mname character varying(1024),
    soa_rname character varying(1024),
    soa_refresh character varying(20),
    soa_retry character varying(20),
    soa_expire character varying(20),
    soa_minimum character varying(20),
    soa_ttl character varying(20),
    zone_ttl character varying(20),
    apex_comment_group_id bigint,
    ptime timestamp with time zone,
    change_by character varying(1024)
);


ALTER TABLE public.zone_instances OWNER TO pgsql;

--
-- Name: zone_instances_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE zone_instances_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.zone_instances_id_seq OWNER TO pgsql;

--
-- Name: zone_instances_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE zone_instances_id_seq OWNED BY zone_instances.id;


--
-- Name: zone_sectags; Type: TABLE; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE TABLE zone_sectags (
    id bigint NOT NULL,
    zone_id bigint,
    sectag character varying(60) DEFAULT (NOT NULL::boolean)
);


ALTER TABLE public.zone_sectags OWNER TO pgsql;

--
-- Name: zone_sectags_id_seq; Type: SEQUENCE; Schema: public; Owner: pgsql
--

CREATE SEQUENCE zone_sectags_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.zone_sectags_id_seq OWNER TO pgsql;

--
-- Name: zone_sectags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: pgsql
--

ALTER SEQUENCE zone_sectags_id_seq OWNED BY zone_sectags.id;


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY reference ALTER COLUMN id SET DEFAULT nextval('reference_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records ALTER COLUMN id SET DEFAULT nextval('resource_records_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY reverse_networks ALTER COLUMN id SET DEFAULT nextval('reverse_networks_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY rr_comments ALTER COLUMN id SET DEFAULT nextval('rr_comments_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY server_groups ALTER COLUMN id SET DEFAULT nextval('server_groups_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_event_queue ALTER COLUMN id SET DEFAULT nextval('sm_event_queue_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_master ALTER COLUMN id SET DEFAULT nextval('sm_master_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_process ALTER COLUMN id SET DEFAULT nextval('sm_process_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_servers ALTER COLUMN id SET DEFAULT nextval('sm_servers_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_zone ALTER COLUMN id SET DEFAULT nextval('sm_zone_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY systemevents ALTER COLUMN id SET DEFAULT nextval('systemevents_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY systemeventsproperties ALTER COLUMN id SET DEFAULT nextval('systemeventsproperties_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY update_groups ALTER COLUMN id SET DEFAULT nextval('update_groups_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_cfg ALTER COLUMN id SET DEFAULT nextval('zone_cfg_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_instances ALTER COLUMN id SET DEFAULT nextval('zone_instances_id_seq'::regclass);


--
-- Name: id; Type: DEFAULT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_sectags ALTER COLUMN id SET DEFAULT nextval('zone_sectags_id_seq'::regclass);


--
-- Name: dbc_error_log_error_id; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY dbt_error_log
    ADD CONSTRAINT dbc_error_log_error_id PRIMARY KEY (error_id);


--
-- Name: dbc_event_log_event_id; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY dbt_event_log
    ADD CONSTRAINT dbc_event_log_event_id PRIMARY KEY (event_id);


--
-- Name: reference_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY reference
    ADD CONSTRAINT reference_pkey PRIMARY KEY (id);


--
-- Name: resource_records_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_pkey PRIMARY KEY (id);


--
-- Name: reverse_networks_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY reverse_networks
    ADD CONSTRAINT reverse_networks_pkey PRIMARY KEY (id);


--
-- Name: rr_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY rr_comments
    ADD CONSTRAINT rr_comments_pkey PRIMARY KEY (id);


--
-- Name: server_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY server_groups
    ADD CONSTRAINT server_groups_pkey PRIMARY KEY (id);


--
-- Name: sm_event_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY sm_event_queue
    ADD CONSTRAINT sm_event_queue_pkey PRIMARY KEY (id);


--
-- Name: sm_master_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY sm_master
    ADD CONSTRAINT sm_master_pkey PRIMARY KEY (id);


--
-- Name: sm_process_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY sm_process
    ADD CONSTRAINT sm_process_pkey PRIMARY KEY (id);


--
-- Name: sm_servers_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY sm_servers
    ADD CONSTRAINT sm_servers_pkey PRIMARY KEY (id);


--
-- Name: sm_zone_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY sm_zone
    ADD CONSTRAINT sm_zone_pkey PRIMARY KEY (id);


--
-- Name: systemevents_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY systemevents
    ADD CONSTRAINT systemevents_pkey PRIMARY KEY (id);


--
-- Name: systemeventsproperties_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY systemeventsproperties
    ADD CONSTRAINT systemeventsproperties_pkey PRIMARY KEY (id);


--
-- Name: update_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY update_groups
    ADD CONSTRAINT update_groups_pkey PRIMARY KEY (id);


--
-- Name: update_groups_update_type_zone_id_key; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY update_groups
    ADD CONSTRAINT update_groups_update_type_zone_id_key UNIQUE (update_type, zone_id);


--
-- Name: zone_cfg_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY zone_cfg
    ADD CONSTRAINT zone_cfg_pkey PRIMARY KEY (id);


--
-- Name: zone_instance_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY zone_instances
    ADD CONSTRAINT zone_instance_pkey PRIMARY KEY (id);


--
-- Name: zone_sectags_pkey; Type: CONSTRAINT; Schema: public; Owner: pgsql; Tablespace: 
--

ALTER TABLE ONLY zone_sectags
    ADD CONSTRAINT zone_sectags_pkey PRIMARY KEY (id);


--
-- Name: resource_records_comment_group_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_comment_group_id_idx ON resource_records USING btree (comment_group_id);


--
-- Name: resource_records_comment_rr_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_comment_rr_id_idx ON resource_records USING btree (comment_rr_id);


--
-- Name: resource_records_label_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_label_idx ON resource_records USING btree (label);


--
-- Name: resource_records_type_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_type_idx ON resource_records USING btree (type);


--
-- Name: resource_records_ug_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_ug_id_idx ON resource_records USING btree (ug_id);


--
-- Name: resource_records_zi_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX resource_records_zi_id_idx ON resource_records USING btree (zi_id);


--
-- Name: rr_comments_tag_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX rr_comments_tag_idx ON rr_comments USING btree (tag);


--
-- Name: server_groups_name_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX server_groups_name_idx ON server_groups USING btree (name);


--
-- Name: server_groups_name_idx1; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE UNIQUE INDEX server_groups_name_idx1 ON server_groups USING btree (name);


--
-- Name: sm_event_queue_created_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_created_idx ON sm_event_queue USING btree (created);


--
-- Name: sm_event_queue_event_type_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_event_type_idx ON sm_event_queue USING btree (event_type);


--
-- Name: sm_event_queue_master_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_master_id_idx ON sm_event_queue USING btree (master_id);


--
-- Name: sm_event_queue_processed_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_processed_idx ON sm_event_queue USING btree (processed);


--
-- Name: sm_event_queue_result_code_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_result_code_idx ON sm_event_queue USING btree (result_code);


--
-- Name: sm_event_queue_scheduled_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_scheduled_idx ON sm_event_queue USING btree (scheduled);


--
-- Name: sm_event_queue_server_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_server_id_idx ON sm_event_queue USING btree (server_id);


--
-- Name: sm_event_queue_state_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_state_idx ON sm_event_queue USING btree (state);


--
-- Name: sm_event_queue_zone_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_event_queue_zone_id_idx ON sm_event_queue USING btree (zone_id);


--
-- Name: sm_master_master_server_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_master_master_server_id_idx ON sm_master USING btree (master_server_id);


--
-- Name: sm_master_replica_sg_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_master_replica_sg_id_idx ON sm_master USING btree (replica_sg_id);


--
-- Name: sm_process_finish_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_process_finish_idx ON sm_process USING btree (finish);


--
-- Name: sm_process_name_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_process_name_idx ON sm_process USING btree (name);


--
-- Name: sm_process_pid_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_process_pid_idx ON sm_process USING btree (pid);


--
-- Name: sm_process_start_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_process_start_idx ON sm_process USING btree (start);


--
-- Name: sm_process_state_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_process_state_idx ON sm_process USING btree (state);


--
-- Name: sm_servers_last_reply_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_last_reply_idx ON sm_servers USING btree (last_reply);


--
-- Name: sm_servers_name_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_name_idx ON sm_servers USING btree (name);


--
-- Name: sm_servers_name_idx1; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE UNIQUE INDEX sm_servers_name_idx1 ON sm_servers USING btree (name);


--
-- Name: sm_servers_server_type_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_server_type_idx ON sm_servers USING btree (server_type);


--
-- Name: sm_servers_sg_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_sg_id_idx ON sm_servers USING btree (sg_id);


--
-- Name: sm_servers_ssh_address_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_ssh_address_idx ON sm_servers USING btree (ssh_address);


--
-- Name: sm_servers_zone_count_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_servers_zone_count_idx ON sm_servers USING btree (zone_count);


--
-- Name: sm_zone_alt_sg_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_alt_sg_id_idx ON sm_zone USING btree (alt_sg_id);


--
-- Name: sm_zone_deleted_start_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_deleted_start_idx ON sm_zone USING btree (deleted_start);


--
-- Name: sm_zone_name_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_name_idx ON sm_zone USING btree (name);


--
-- Name: sm_zone_ref_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_ref_id_idx ON sm_zone USING btree (ref_id);


--
-- Name: sm_zone_sg_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_sg_id_idx ON sm_zone USING btree (sg_id);


--
-- Name: sm_zone_state_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_state_idx ON sm_zone USING btree (state);


--
-- Name: sm_zone_zi_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_zi_id_idx ON sm_zone USING btree (zi_id);


--
-- Name: sm_zone_zone_type_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX sm_zone_zone_type_idx ON sm_zone USING btree (zone_type);


--
-- Name: systemevents_server_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX systemevents_server_id_idx ON systemevents USING btree (server_id);


--
-- Name: systemevents_zone_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX systemevents_zone_id_idx ON systemevents USING btree (zone_id);


--
-- Name: update_groups_zone_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX update_groups_zone_id_idx ON update_groups USING btree (zone_id);


--
-- Name: zone_cfg_key_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_cfg_key_idx ON zone_cfg USING btree (key);


--
-- Name: zone_cfg_sg_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_cfg_sg_id_idx ON zone_cfg USING btree (sg_id);


--
-- Name: zone_instances_apex_comment_group_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_instances_apex_comment_group_id_idx ON zone_instances USING btree (apex_comment_group_id);


--
-- Name: zone_instances_ctime_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_instances_ctime_idx ON zone_instances USING btree (ctime);


--
-- Name: zone_instances_mtime_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_instances_mtime_idx ON zone_instances USING btree (mtime);


--
-- Name: zone_instances_ptime_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_instances_ptime_idx ON zone_instances USING btree (ptime);


--
-- Name: zone_instances_zone_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_instances_zone_id_idx ON zone_instances USING btree (zone_id);


--
-- Name: zone_sectags_sectag_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_sectags_sectag_idx ON zone_sectags USING btree (sectag);


--
-- Name: zone_sectags_zone_id_idx; Type: INDEX; Schema: public; Owner: pgsql; Tablespace: 
--

CREATE INDEX zone_sectags_zone_id_idx ON zone_sectags USING btree (zone_id);


--
-- Name: delete_associated_comment; Type: TRIGGER; Schema: public; Owner: pgsql
--

CREATE TRIGGER delete_associated_comment AFTER DELETE ON resource_records FOR EACH ROW EXECUTE PROCEDURE delete_associated_comment();


--
-- Name: delete_associated_reference; Type: TRIGGER; Schema: public; Owner: pgsql
--

CREATE TRIGGER delete_associated_reference AFTER DELETE ON sm_zone FOR EACH ROW EXECUTE PROCEDURE delete_associated_reference();


--
-- Name: sm_servers_update_mtime; Type: TRIGGER; Schema: public; Owner: pgsql
--

CREATE TRIGGER sm_servers_update_mtime BEFORE UPDATE ON sm_servers FOR EACH ROW WHEN (((((old.name)::text IS DISTINCT FROM (new.name)::text) OR (old.address IS DISTINCT FROM new.address)) OR ((old.server_type)::text IS DISTINCT FROM (new.server_type)::text))) EXECUTE PROCEDURE sm_servers_update_mtime_column();


--
-- Name: update_mtime; Type: TRIGGER; Schema: public; Owner: pgsql
--

CREATE TRIGGER update_mtime BEFORE UPDATE ON zone_instances FOR EACH ROW EXECUTE PROCEDURE update_mtime_column();


--
-- Name: zone_update_mtime; Type: TRIGGER; Schema: public; Owner: pgsql
--

CREATE TRIGGER zone_update_mtime BEFORE UPDATE ON sm_zone FOR EACH ROW WHEN (((((((((((old.name)::text IS DISTINCT FROM (new.name)::text) OR (old.use_apex_ns IS DISTINCT FROM new.use_apex_ns)) OR (old.edit_lock IS DISTINCT FROM new.edit_lock)) OR (old.nsec3 IS DISTINCT FROM new.nsec3)) OR (old.auto_dnssec IS DISTINCT FROM new.auto_dnssec)) OR (old.inc_updates IS DISTINCT FROM new.inc_updates)) OR (((old.state)::text <> 'DISABLED'::text) AND ((new.state)::text = 'DISABLED'::text))) OR (((old.state)::text <> 'DELETED'::text) AND ((new.state)::text = 'DELETED'::text))) OR (((old.state)::text <> 'CREATE'::text) AND ((new.state)::text = 'CREATE'::text)))) EXECUTE PROCEDURE zone_update_mtime_column();


--
-- Name: dbc_error_log_inner_error_id; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY dbt_error_log
    ADD CONSTRAINT dbc_error_log_inner_error_id FOREIGN KEY (inner_error_id) REFERENCES dbt_error_log(error_id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: resource_records_comment_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_comment_group_id_fkey FOREIGN KEY (comment_group_id) REFERENCES rr_comments(id);


--
-- Name: resource_records_comment_rr_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_comment_rr_id_fkey FOREIGN KEY (comment_rr_id) REFERENCES rr_comments(id);


--
-- Name: resource_records_ref_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_ref_id_fkey FOREIGN KEY (ref_id) REFERENCES reference(id) ON DELETE SET NULL;


--
-- Name: resource_records_ug_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_ug_id_fkey FOREIGN KEY (ug_id) REFERENCES update_groups(id) ON DELETE CASCADE;


--
-- Name: resource_records_zi_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY resource_records
    ADD CONSTRAINT resource_records_zi_id_fkey FOREIGN KEY (zi_id) REFERENCES zone_instances(id) ON DELETE CASCADE;


--
-- Name: reverse_networks_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY reverse_networks
    ADD CONSTRAINT reverse_networks_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE CASCADE;


--
-- Name: sm_event_queue_master_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_event_queue
    ADD CONSTRAINT sm_event_queue_master_id_fkey FOREIGN KEY (master_id) REFERENCES sm_master(id) ON DELETE SET NULL;


--
-- Name: sm_event_queue_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_event_queue
    ADD CONSTRAINT sm_event_queue_server_id_fkey FOREIGN KEY (server_id) REFERENCES sm_servers(id) ON DELETE SET NULL;


--
-- Name: sm_event_queue_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_event_queue
    ADD CONSTRAINT sm_event_queue_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE SET NULL;


--
-- Name: sm_master_master_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_master
    ADD CONSTRAINT sm_master_master_server_id_fkey FOREIGN KEY (master_server_id) REFERENCES sm_servers(id) ON DELETE SET NULL;


--
-- Name: sm_master_replica_sg_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_master
    ADD CONSTRAINT sm_master_replica_sg_id_fkey FOREIGN KEY (replica_sg_id) REFERENCES server_groups(id) ON DELETE SET NULL;


--
-- Name: sm_servers_sg_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_servers
    ADD CONSTRAINT sm_servers_sg_id_fkey FOREIGN KEY (sg_id) REFERENCES server_groups(id) ON UPDATE CASCADE;


--
-- Name: sm_zone_alt_sg_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_zone
    ADD CONSTRAINT sm_zone_alt_sg_id_fkey FOREIGN KEY (alt_sg_id) REFERENCES server_groups(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sm_zone_ref_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_zone
    ADD CONSTRAINT sm_zone_ref_id_fkey FOREIGN KEY (ref_id) REFERENCES reference(id) ON UPDATE CASCADE;


--
-- Name: sm_zone_sg_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_zone
    ADD CONSTRAINT sm_zone_sg_id_fkey FOREIGN KEY (sg_id) REFERENCES server_groups(id) ON UPDATE CASCADE ON DELETE SET NULL;


--
-- Name: sm_zone_zi_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY sm_zone
    ADD CONSTRAINT sm_zone_zi_id_fkey FOREIGN KEY (zi_id) REFERENCES zone_instances(id) ON DELETE SET NULL;


--
-- Name: systemevents_server_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY systemevents
    ADD CONSTRAINT systemevents_server_id_fkey FOREIGN KEY (server_id) REFERENCES sm_servers(id) ON DELETE SET NULL;


--
-- Name: systemevents_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY systemevents
    ADD CONSTRAINT systemevents_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE SET NULL;


--
-- Name: update_groups_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY update_groups
    ADD CONSTRAINT update_groups_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE CASCADE;


--
-- Name: zone_cfg_sg_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_cfg
    ADD CONSTRAINT zone_cfg_sg_id_fkey FOREIGN KEY (sg_id) REFERENCES server_groups(id) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: zone_instances_apex_comment_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_instances
    ADD CONSTRAINT zone_instances_apex_comment_group_id_fkey FOREIGN KEY (apex_comment_group_id) REFERENCES rr_comments(id);


--
-- Name: zone_instances_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_instances
    ADD CONSTRAINT zone_instances_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE CASCADE;


--
-- Name: zone_sectags_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: pgsql
--

ALTER TABLE ONLY zone_sectags
    ADD CONSTRAINT zone_sectags_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES sm_zone(id) ON DELETE CASCADE;


--
-- Name: public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM postgres;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO pgsql;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- Name: reference; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE reference FROM PUBLIC;
REVOKE ALL ON TABLE reference FROM pgsql;
GRANT ALL ON TABLE reference TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE reference TO dms;


--
-- Name: reference_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE reference_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE reference_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE reference_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE reference_id_seq TO dms;


--
-- Name: resource_records; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE resource_records FROM PUBLIC;
REVOKE ALL ON TABLE resource_records FROM pgsql;
GRANT ALL ON TABLE resource_records TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE resource_records TO dms;


--
-- Name: resource_records_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE resource_records_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE resource_records_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE resource_records_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE resource_records_id_seq TO dms;


--
-- Name: reverse_networks; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE reverse_networks FROM PUBLIC;
REVOKE ALL ON TABLE reverse_networks FROM pgsql;
GRANT ALL ON TABLE reverse_networks TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE reverse_networks TO dms;


--
-- Name: reverse_networks_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE reverse_networks_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE reverse_networks_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE reverse_networks_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE reverse_networks_id_seq TO dms;


--
-- Name: rr_comments; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE rr_comments FROM PUBLIC;
REVOKE ALL ON TABLE rr_comments FROM pgsql;
GRANT ALL ON TABLE rr_comments TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE rr_comments TO dms;


--
-- Name: rr_comments_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE rr_comments_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE rr_comments_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE rr_comments_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE rr_comments_id_seq TO dms;


--
-- Name: server_groups; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE server_groups FROM PUBLIC;
REVOKE ALL ON TABLE server_groups FROM pgsql;
GRANT ALL ON TABLE server_groups TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE server_groups TO dms;


--
-- Name: server_groups_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE server_groups_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE server_groups_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE server_groups_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE server_groups_id_seq TO dms;


--
-- Name: sm_event_queue; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE sm_event_queue FROM PUBLIC;
REVOKE ALL ON TABLE sm_event_queue FROM pgsql;
GRANT ALL ON TABLE sm_event_queue TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sm_event_queue TO dms;


--
-- Name: sm_event_queue_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE sm_event_queue_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE sm_event_queue_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE sm_event_queue_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE sm_event_queue_id_seq TO dms;


--
-- Name: sm_master; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE sm_master FROM PUBLIC;
REVOKE ALL ON TABLE sm_master FROM pgsql;
GRANT ALL ON TABLE sm_master TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sm_master TO dms;


--
-- Name: sm_master_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE sm_master_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE sm_master_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE sm_master_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE sm_master_id_seq TO dms;


--
-- Name: sm_process; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE sm_process FROM PUBLIC;
REVOKE ALL ON TABLE sm_process FROM pgsql;
GRANT ALL ON TABLE sm_process TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sm_process TO dms;


--
-- Name: sm_process_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE sm_process_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE sm_process_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE sm_process_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE sm_process_id_seq TO dms;


--
-- Name: sm_servers; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE sm_servers FROM PUBLIC;
REVOKE ALL ON TABLE sm_servers FROM pgsql;
GRANT ALL ON TABLE sm_servers TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sm_servers TO dms;


--
-- Name: sm_servers_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE sm_servers_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE sm_servers_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE sm_servers_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE sm_servers_id_seq TO dms;


--
-- Name: sm_zone; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE sm_zone FROM PUBLIC;
REVOKE ALL ON TABLE sm_zone FROM pgsql;
GRANT ALL ON TABLE sm_zone TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sm_zone TO dms;


--
-- Name: sm_zone_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE sm_zone_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE sm_zone_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE sm_zone_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE sm_zone_id_seq TO dms;


--
-- Name: systemevents; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE systemevents FROM PUBLIC;
REVOKE ALL ON TABLE systemevents FROM pgsql;
GRANT ALL ON TABLE systemevents TO pgsql;
GRANT INSERT ON TABLE systemevents TO rsyslog;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE systemevents TO dms;


--
-- Name: systemevents_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE systemevents_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE systemevents_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE systemevents_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE systemevents_id_seq TO rsyslog;
GRANT USAGE ON SEQUENCE systemevents_id_seq TO dms;


--
-- Name: systemeventsproperties; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE systemeventsproperties FROM PUBLIC;
REVOKE ALL ON TABLE systemeventsproperties FROM pgsql;
GRANT ALL ON TABLE systemeventsproperties TO pgsql;
GRANT SELECT,INSERT ON TABLE systemeventsproperties TO rsyslog;


--
-- Name: update_groups; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE update_groups FROM PUBLIC;
REVOKE ALL ON TABLE update_groups FROM pgsql;
GRANT ALL ON TABLE update_groups TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE update_groups TO dms;


--
-- Name: update_groups_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE update_groups_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE update_groups_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE update_groups_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE update_groups_id_seq TO dms;


--
-- Name: zone_cfg; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE zone_cfg FROM PUBLIC;
REVOKE ALL ON TABLE zone_cfg FROM pgsql;
GRANT ALL ON TABLE zone_cfg TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE zone_cfg TO dms;


--
-- Name: zone_cfg_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE zone_cfg_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE zone_cfg_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE zone_cfg_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE zone_cfg_id_seq TO dms;


--
-- Name: zone_instances; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE zone_instances FROM PUBLIC;
REVOKE ALL ON TABLE zone_instances FROM pgsql;
GRANT ALL ON TABLE zone_instances TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE zone_instances TO dms;


--
-- Name: zone_instances_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE zone_instances_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE zone_instances_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE zone_instances_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE zone_instances_id_seq TO dms;


--
-- Name: zone_sectags; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON TABLE zone_sectags FROM PUBLIC;
REVOKE ALL ON TABLE zone_sectags FROM pgsql;
GRANT ALL ON TABLE zone_sectags TO pgsql;
GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE zone_sectags TO dms;


--
-- Name: zone_sectags_id_seq; Type: ACL; Schema: public; Owner: pgsql
--

REVOKE ALL ON SEQUENCE zone_sectags_id_seq FROM PUBLIC;
REVOKE ALL ON SEQUENCE zone_sectags_id_seq FROM pgsql;
GRANT ALL ON SEQUENCE zone_sectags_id_seq TO pgsql;
GRANT USAGE ON SEQUENCE zone_sectags_id_seq TO dms;


--
-- PostgreSQL database dump complete
--


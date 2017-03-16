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

--
-- Name: server_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: pgsql
--

SELECT pg_catalog.setval('server_groups_id_seq', 1, true);


--
-- Name: zone_cfg_id_seq; Type: SEQUENCE SET; Schema: public; Owner: pgsql
--

SELECT pg_catalog.setval('zone_cfg_id_seq', 26, true);


--
-- Name: zone_sectags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: pgsql
--

SELECT pg_catalog.setval('zone_sectags_id_seq', 9543, true);


--
-- Data for Name: server_groups; Type: TABLE DATA; Schema: public; Owner: pgsql
--

INSERT INTO server_groups (id, name, config_dir, zone_count, master_address) VALUES (1, 'someorg-one', NULL, 0, NULL);


--
-- Data for Name: zone_cfg; Type: TABLE DATA; Schema: public; Owner: pgsql
--

INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (1, 'auto_dnssec', 'false', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (2, 'default_ref', 'SOMEORG-NET', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (4, 'default_stype', 'bind9', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (5, 'edit_lock', 'false', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (6, 'event_max_age', '120.0', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (7, 'inc_updates', 'false', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (8, 'nsec3', 'false', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (9, 'soa_expire', '7d', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (10, 'soa_minimum', '1h', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (11, 'soa_mname', 'ns1.someorg.net.', 1);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (12, 'soa_refresh', '2h', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (13, 'soa_retry', '900', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (14, 'soa_rname', 'soa.someorg.net.', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (15, 'use_apex_ns', 'true', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (16, 'zi_max_age', '90.0', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (17, 'zi_max_num', '25', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (18, 'zone_del_age', '0.0', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (26, 'zone_del_pare_age', '90.0', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (19, 'zone_ttl', '1h', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (23, 'apex_ns', 'ns2.someorg.net.', 1);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (24, 'apex_ns', 'ns1.someorg.net.', 1);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (3, 'default_sg', 'someorg-one', NULL);
INSERT INTO zone_cfg (id, key, value, sg_id) VALUES (25, 'syslog_max_age', '120.0', NULL);


--
-- Data for Name: zone_sectags; Type: TABLE DATA; Schema: public; Owner: pgsql
--

INSERT INTO zone_sectags (id, zone_id, sectag) VALUES (1, NULL, 'HOSTED');
INSERT INTO zone_sectags (id, zone_id, sectag) VALUES (2, NULL, 'VALUE_RESELLER');


--
-- PostgreSQL database dump complete
--


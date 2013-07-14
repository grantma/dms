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
SET standard_conforming_strings = off;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET escape_string_warning = off;

SET search_path = public, pg_catalog;

--
-- Name: zone_cfg_id_seq; Type: SEQUENCE SET; Schema: public; Owner: pgsql
--

SELECT pg_catalog.setval('zone_cfg_id_seq', 25, true);


--
-- Data for Name: zone_cfg; Type: TABLE DATA; Schema: public; Owner: pgsql
--

COPY zone_cfg (id, key, value) FROM stdin;
3	soa_retry	600
4	soa_refresh	600
5	soa_expire	7d
6	soa_minimum	10m
21	auto_dnssec	false
22	edit_lock	false
23	use_apex_ns	true
24	apex_ns	ns1.foo.bar.net.
25	apex_ns	ns2.foo.bar.net.
1	soa_mname	ns1.foo.bar.net.
2	soa_rname	soa.foo.bar.net.
7	zone_ttl	24h
\.


--
-- PostgreSQL database dump complete
--


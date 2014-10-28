********
Overview
********

Software Architecture
=====================
.. _fig_dms_system_architecture:
.. figure:: images/Dms_system_architecture.*

   *DMS System Architecture*

In *Fig:*\ :ref:`fig_dms_system_architecture`, only one of the DR replica pairs
is shown below for clarity.  As shown in *Fig:*\ :ref:`fig_network_layout` the
standby replica runs as a server of the replica SG group. PostgresQL
Replication is also live to the DR replica, carried over the IPSEC connection
between the DR master and replica servers.  The master/replica servers use
iptables/ip6tables to filter access to services carried over IPSEC.

.. _fig_network_layout:
.. figure:: images/Network_Layout.*

   *Conceptual Network Layout*

The DMS is designed to support anycast and unicast servers, as per :ref:`best-practice-guidelines`.

DMS Features
============

* IPv6 fully supported in back end and front end

* IPv6 DNS RRs (AAAA)

* Dynamic DNS configuration of Master server reduces need for reconfig and reload operations.

* DNS RRs supported include SOA NS A AAAA MX PTR TXT SPF RP SSHFP SRV NSAP NAPTR LOC KX
  IPSECKEY HINFO CERT DS. DNSSEC handled by bind9 master.

* Auto DNSSEC via Bind9 dynamic DNS. Bind9 master server auto maintains zone
  DNSSEC operations records and signing. NSEC3 and NSEC supported. DNSSEC key
  management on Master server file system pending write of key management
  module. Key material directory is replicated via DR protocol (rsync) though.
  DMS is fully enabled to use DNSSEC for securing our core domains.

* Apex resource record (SOA and NS) management across all zones - can be turned off per zone.

* Auto reverse PTR generation

* Customer control of their own automated reverse DNS. Individual PTR records,
  and complete reverse zones.  Useful for business IPv6 and IPv4 blocks.
  Enables on site use of IP PABX, intranet and email for SMBs on XDSL/Fibre.

* zone_tool command line administrative tool on master servers

* IPSEC secured communications between each of DR master replicas and slaves

* Modular design. For example, Racoon IPSEC can be replaced if needed.

* Multiple Slave DNS server software implementations. NL Netlabs nsd3 can be
  used as a slave server once backend code is completed, and a simple
  configuration monitoring/HUP daemon implemented to run on each slave.

* Slave server/Server Groups (SG) support. Live migration of zones.

* Private SGs for internal Voyager/NET24 zones.

* Retention of deleted zones in database for aged auto-deletion later.

* Multiple Zone Instances per Zone. Roll forward and roll back changes. Again
  old ZIs aged for auto deletion above a threshold number.

* Templates used for generating name server configuration includes - master, replicas and slaves.

* Rsync to distribute name server configuration to servers.

* Central distribution of name server configuration segments.

* Hot standby master replica for DR purposes with manually controlled fail
  over. Includes automatic replica/slave server reconfiguration.

* WSGI JSON RPC over HTTPS API for mulitple front ends

* Security tags to control what front ends can see

* Zone reference metadata to tag the zone with the owner/customer entity ID.
  Set by DMI when a zone is created. Tag out of table in DB via foreign key for
  easy reference renaming.

* zone_tool has built in pager support and editor support via standard shell environment variables.

* zone_tool has a configurable restricted shell mode for Help Desk use

* RR Groups and RR comments supported in DB for use in text editor and in Web Admin DMI

* zone_tool has colourised diff support to display changes between different ZIs for a zone

* Vim can be used as zone tool editor, giving DNS colourised Zone file syntax
  high lighting. (zone_tool supports editor selection by standard \*NIX
  environment variables.)

Programming Language
====================

The DMS backend software is written in Python 3.x, which is a good choice given
the code base size of 22,000 lines. Python is well suited to larger projects,
and fully object oriented, and very clear and systematically defined.  Python
3.x was chosen over 2.x for future proofing.

The Python JSON RPC interface is implemented with Apache2 mod_wsgi, with a back
end DNS Manager Daemon.  zone_tool is a command line shell environment that
implements all the functionality of the JSON RPC calls, as well as DMS systems
configuration and management functionality. This common code functionality
allows the JSON RPC calls to be called from a terminal, where a debugger can be
used, for ease of development.

A state machine and event queue design is used, with state and event
information recorded in PostgresQL. State machines exist for each:

* DNS zone to track life-cycle state of zone
* Master server configuration
* DNS replica/slave server configuration and reload cycles.

DNS Server Software
===================

Decided to go forward using ISC Bind 9 as DNSSEC is on the way, and Bind 9 will
be the software used to roll this out. Other implementations of DNS software
exist, Netlabs NL NSD3 is one, but it looks more suited to a TLD registry and
large site/domain use than for DNS Provider use for small zones.

The DNS server state machine classes are designed so that NL Netlabs nsd 3.x
can be added latter on as a slave server. This is done achieved by the use of
state machine design, object oriented code and modularity.

A Hidden Master DNS architecture is implemented, with a DR replica master server.

Backend Database
================

PosgresQL 9.1+. PostgresQL has a significant history of high end functionality
including transactions and stored procedures. Replication is also baked in as
well.

DMI Server/Clients
==================

DNS Website Software (DNS Management Interface - DMI) will communicate with DMS
via the WSGI server. The DMS server can handle multiple Web UIs via different
Web services URIs. An administrative help desk DNS Management Interface can be
implemented as well. To begin with, the DMS will be administered via
*zone_tool* by ssh into the Master DMS system.

Network Protocols and Security
==============================

DNS and logging traffic between the slave servers outside Net24 is be secured
using IPSEC. Iptables filtering and IPSEC SAs are used to control the traffic
that the slave servers accept from the network and Internet. IPSEC SAs exist
for zone update and port 53 administrative traffic, and secure that traffic.
Ie, DNS Traffic from the Master DNS server will be secured using IPSEC. This
keeps all the cryptographic verbiage out of the DNS server configurations, and
makes them a lot simpler to generate from templates. IP numbers and acls may
need to be inserted in the named.conf files to identify the designation of
administrative control and updates from the Master DNS server, but this is a
lot easier that having to track of lot of configuration details about TSIG/SIG0
keys for each individual master-slave relationship, and where they are used....

Web UI Framework
================

The Web GUI for the DMI will be rendered using ExtJS. Check logic, and business
logic will be separated out and not mixed in (as much as possible) with the UI.
This is basically a Mode View Controller programming model.

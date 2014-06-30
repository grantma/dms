*********************************************
Master Server Install from Source Repostitory
*********************************************

.. note::

   This may be a bit out of date, but useful for details hidden by Debian
   Packaging.

Packages to Install
===================

Install from Debian 6.0 business card CD, Expert install. On downloading
release information offered a choice to install Squeeze(stable),
Wheezy(Testing) or Sid(unstable). Choose Wheezy and follow prompts.

Just do the following.

Useful sys admin tools::

 # aptitude install screen vim-nox colordiff ssh lsof strace at less sudo \
   telnet-ssl dnsutils curl 
 # aptitude install git postgresql-9.1 python3.2 python3.2-dev apache2 \
   libapache2-mod-wsgi-py3 rsyslog-pgsql bind9 curl racoon libpq-dev \
   build-essential haveged ntp 
 
``Haveged`` is installed as it helps a lot with entropy material for
/dev/random on a Linux VM, by finding randomness in the memory allocation and
LDT tables etc.

Choose ``racoon-tool`` as the mode of control of the IKE daemon. With
rsyslog-pgsql, choose not to configure with dbconfig-common as rsyslog database
will be part of dms database.

Linux Kernel Tuning
===================

This is to increase SYSV shared memory and semaphore limits.

::
 
 # echo "# Shared memory settings for PostgreSQL
 
 # Note that if another program uses shared memory as well, you will have to
 # coordinate the size settings between the two.
 
 # Maximum size of shared memory segment in bytes
 #kernel.shmmax = 33554432
 
 # Maximum total size of shared memory in pages (normally 4096 bytes)
 #kernel.shmall = 2097152

 kernel.shmmax = 134217728
 kernel.shmall = 32768
 " > /etc/sysctl.d/30-postgresql-shm.conf

 # service procps start

Shared memory settings also have to be adjusted in postgresql.conf

Debian Setup
============

NTP
---

Add::

 server ntp.net24.net.nz iburst maxpoll 9
 server ntp2.net24.net.nz iburst maxpoll 9
 
to ``/etc/ntp.conf``, commenting out the default Debian NTP server pool
servers.

Get DMS Master Source code
==========================

In your home directory::

 $ git clone https://git.devel.net.nz/dms/dms-2011.git

PostgresQL set up
=================

The procedures here will create PostgresQL setups that are cross compatible.
Using Unicode in the DB (above) makes the dumps compatible with Debian's PGSQL
install, and creating the pgsql super user on Debian means that access control
statements in the dumps work on FreeBSD and Debian.

su to the postgres user, and add a pgsql super user::

 # sh ./setup_scripts/create-debian-db.sh

and of course for development::

 $ createuser -sEP <your-login>

Again, record data base passwords for later on, when setting up dms.conf

PostgresQL network and user account mapping
-------------------------------------------

The files ``pg_hba.conf``, ``postgresql.conf``, and ``pg_ident.conf`` are found
in ``/etc/postgresql/9.3/main``, the configuration directory for the main DB
cluster. Peer mapping is used instead of trust, as it is far more secure. MD5
authentication is used on localhost as configuring Unix sockets is a lot harder
to do in Python SQLAlchemy. Also, at some point in the future, the master DB
may be run as a cluster for scalability.

*On Debian, do not disable the administrative access in* ``pg_hba.conf`` *for the
postgres user across a unix socket. All sorts of maintenance and system cron
jobs won't work then!*

Production
^^^^^^^^^^

Edit ``/etc/postgresql/9.3/pg_hba.conf`` to be::

 # TYPE     DATABASE              USER                  CIDR-ADDRESS                      METHOD

 # "local" is for Unix domain socket connections only
 local   all             all                                                              peer
 # IPv4 local connections:
 host    all             all             127.0.0.1/32                                     md5
 # IPv6 local connections:
 host    all             all             ::1/128                                          md5

This turns on password checking for localhost IP access, and sets Unix socket
connections from psql to have no passwords from the command line.

Development
^^^^^^^^^^^

On Debian, to make work easier and to enable Python DB stuff to work with less
fuss add the following to ``/etc/postgresql/9.1/main/pg_ident.conf``::


       # MAPNAME             SYSTEM-USERNAME                  PG-USERNAME
       net24                 <login>                          pgsql
       net24                 <login>                          <login>

And edit ``/etc/postgresql/main/pg_hba.conf`` to be::

       # TYPE     DATABASE              USER                  CIDR-ADDRESS                      METHOD

       # "local" is for Unix domain socket connections only
       local   all             all                                                              peer
       map=net24
       # IPv4 local connections:
       host    all             all             127.0.0.1/32                                     md5
       # IPv6 local connections:
       host    all             all             ::1/128                                          md5

This turns on password checking for localhost IP access, and sets Unix socket
connections from psql to have no passwords from the command line.

Of course you can also set the following environment variables in ``.profile``
or ``.bashrc``::

       PGDATABASE="dms"
       PGUSER="pgsql"
       export PGUSER PGDATABASE

Postgresql.conf settings
------------------------

On Debian, set ``listen_addresses`` to ``ip6-localhost,localhost``, and on both system
types set shared_buffers to 64MB.

DR Postgresql.conf settings
---------------------------

For reference see the `PostgesQL wiki
<https://wiki.postgresql.org/wiki/Streaming_Replication>`

For DR, add external interface address to ``listen_addresses``, set
``max_wal_senders`` to 3, set ``wal_keep_segments`` to 256 (4GB WAL logs), and
set ``hot_standby`` to on. Do this on both machines as the ``recovery.conf``
file in the PostgresQL cluster data directory is what determines whether
postgresql comes up in standby mode or not.

Create the DR user on the master as shell user ``postgres`` or ``pgsql``
(FreeBSD)::

       postgres $ psql -c "CREATE USER ruser WITH REPLICATION PASSWORD
       'SomethingSimplyDuplex';"

Rsync the contents of the data directory, after stopping PostgresQL on the
master::

       root@master # rsync -a /var/lib/postgresql/9.1/main/
       root@dr:/var/lib/postgresql/9.1/main

On the DR server, in the main cluster data directory create the file
``recovery.conf``

       primary_conninfo = 'host=master port=5432 user=ruser
       password=SomethingSimplyDuplex'
       standby_mode = on

Add the replication user ``ruser`` to the PG cluster's ``pg_hba.conf`` on both
master and DR servers::

       host       replication           ruser                 2001:db8::1/128        md5

Now do this on the DR::

      # chown postgres:postgres /var/lib/postgresql/9.1/main/recovery.conf
      # chmod 640 /var/lib/postgresql/9.1/main/recovery.conf
      # ls -l /var/lib/postgresql/9.1/main/recovery.conf
      -rw-r----- 1 postgres postgres 108 May 14 17:06
      /var/lib/postgresql/9.1/main/recovery.conf

When the DR DB is promoted to read/write via the ``prctl promote`` command, the
``recovery.conf`` file will be renamed ``recovery.done``

Restart postgresql to make the new settings take effect::

      service postgresql restart

Load database schema and functions
----------------------------------

Run psql as DB superuser and load the DB dms schema onto the fresh ``dms``
database created above. Its also a good time to load the seed configuration
settings as well.

::

      $ psql -U pgsql dms
      dms=# \i sql/dms-schema.sql
      dms=# \i sql/zone-cfg.sql

This contains all stored procedures and triggers etc for the database, created
by ``pg_dump -s -U pgsql dms``

Install Python Stack
====================

As ``root`` from ``dms`` source code directory, run
``./setup_scripts/bootstrap-python-packages.sh``

Create System Users
===================

The following will create the 2 system/pseudo users ``dms`` and ``dmsdmd`` the
DMS sofware will run as::

 # sh ./setup_scripts/create-debian-users.sh

Don't forget to add users who need access to ``zone_tool`` to the ``dms`` group
so that they can read the ``dms.conf`` file that also stores the database
password.

Install Software
================

As ``root`` on Debian::

 # make install


Edit dms.conf and test
======================

Edit ``dms.conf`` in ``/etc/dms`` on Debian to set up DB passwords recorded
from above. Also note that logging settings can also be adjusted here. Each
different program and ``mod_wsgi`` has their own section, that overrides the
DEFAULT section.

Test using::

      $ zone_tool
      Welcome to the zone_tool program.
      Type help or ? to list commands.

      zone_tool > show_config
              auto_dnssec:      false
              default_ref:      net24
              default_ssg:      net24-one
              default_stype:    bind9
              edit_lock:        false
              event_max_age:    120.0
              inc_updates:      false
              nsec3:            false
              soa_expire:       7d
              soa_minimum:      24h
              soa_mname:        ns1.someorg.org. (someorg-one)
              soa_refresh:      7200
              soa_retry:        7200
              soa_rname:        soa.someorg.org.
              use_apex_ns:      true
              zi_max_age:       90.0
              zi_max_num:       25
              zone_del_age:     90.0
              zone_ttl:         24h
      zone_tool > show_apex_ns
              ns1.someorg.org.
              ns2.someorg.org.
      zone_tool > show_sectags
              DOMAIN_RESELLER
              Admin
              SOMEORG
      zone_tool > ls_sg
              someorg-one    /etc/dms/server-config-templates
      zone_tool >

Configuring BIND named
======================

Generate the following keys and ``rndc.conf`` using ``zone_tool``::

      #   zone_tool   generate_tsig_key rndc-key hmac-md5 rndc-local.key
      #   zone_tool   generate_tsig_key remote-key hmac-md5 rndc-remote.key
      #   zone_tool   generate_tsig_key update-ddns hmac-sha256 update-session.key
      #   zone_tool   write_rndc_conf


Go to the named ``/etc/bind`` directory and copy the ``rndc-remote.key`` key to
the ``/etc/dms/server-admin-config`` directory::

      # cd /etc/bind
      # cp rndc-remote.key /etc/dms/server-admin-config/bind9

Edit ``named.conf`` to set up the options and include statements for the master server. ``Named.conf`` segments can be
found in ``etc/master-named.conf-segments``, off an example Debian system.

Named options settings:: 

      //
      // DMS ACL set up for master server
      //
      // ACLs need to be configured here to use in options...

      // include public SG ACL
      include "/var/lib/dms/master-config/master-server-acl.conf";

      options {
              //     OS bind options here
              //     .
              //     .
              //     .

              // On multi-homed box, where bind is not on primary
              // hostname and IP use the following to stop named 
              // twittering to itself
              // as it thinks it is not the master server!
              //server-id "full.host.name.on.internet.";
              //hostname "full.host.name.on.internet.";

              // we want to do this....
              dnssec-validation auto;

              auth-nxdomain no;    # conform to RFC1035
              listen-on-v6 { any; };


              // secure this name server for use on internet
              recursion no;
              //allow-recursion {
              //        localhost;
              //};

              // Slave and AXFR settings
              allow-transfer {
                   localhost;
              };
              transfers-in 10;
              transfers-out 150;
              transfers-per-ns 50;

              allow-query {
                      any;
              };

              // Notify only from port 53
              notify-source * port 53;
              notify-source-v6 * port 53;
              // notify to SOA mname server?
              notify-to-soa no;

              // DNSSEC related options

                 key-directory "keys";
        };


Master server include zone setup. Add this to ``/etc/bind/named.conf.local``::


       // local rndc key
       include "/etc/bind/rndc-local.key";
       controls {
               inet 127.0.0.1 port 953 allow { 127.0.0.1; } keys { "rndc-key"; };
       };
       include "/etc/bind/update-session.key";

       include "/var/lib/dms/master-config/master-config.conf";

1. Restart ``named`` and make sure it works.

2. Start dmsdmd in debug mode and make sure it runs::

             # dmsdmd -d 1

   It should start and keep running, not detaching from the terminal.

3. In another terminal, do a ``zone_tool reconfig_master``. This should rewrite
   the ACL file in ``/var/lib/dms/master-config``
   
4. Create a zone, and check that you can AXFR it. Delete it once the check has
   been performed.

::

             # zone_tool create_zone test.blam
             # dig +noall +answer -t AXFR test.blam. @localhost
             test.blam. 86400 IN SOA ns1.someorg.org. soa.someorg.org.
              2012032200 7200 7200 604800 86400
             test.blam. 86400 IN NS ns1.someorg.org.
             test.blam. 86400 IN NS ns2.someorg.org.
             test.blam. 86400 IN SOA ns1.someorg.org. soa.someorg.org.
              2012032200 7200 7200 604800 86400
             zone_tool delete_zone test.blam

This zone may take about 10 minutes to turn up. Try typing ``show_configsm``
at the ``zone_tool`` prompt. That will show the next time the ConfigSM will
cycle, allowing the zone to be published.

Enabling net24dmd at boot
=========================

Copy ``etc/debian/init/dmsdmd.init`` to ``/etc/init.d/dmsdmd``, and copy
``etc/debian/init/dmsdmd.default`` to ``/etc/default/dmsdmd``, and run
``insserv /etc/init.d/net24dmd``.

::

 #   cp etc/debian/init/dmsdmd.init /etc/init.d/dmsdmd
 #   chmod 755 /etc/init.d/dmsdmd
 #   cp etc/debian/init/dmsdmd.default /etc/default/dmsdmd
 #   insserv /etc/init.d/dmsdmd

Edit /etc/default/dmsdmd to enable dmsdmd on boot::

       # defaults file for dmsdmd

       # start dmsdmd from init.d script?
       # only allowed values are "true", and "false"
       DMSDMD_ENABLE=true

Cron Jobs
=========

Just create a cron job to run ``zone_tool vacuum_all`` daily, It does not have to
be done as root, though that is probably the easiest.

WSGI Setup
==========

Put the following into ``/etc/apache2/sites-available/wsgi.someorg.org``, and
``a2ensite`` it.

::

        <VirtualHost *:80>

            ServerName wsgi-ext.internal.anathoth.net
            ServerAdmin root@anathoth.net

            DocumentRoot /usr/share/dms/www/documents

            LogLevel Info
            ErrorLog "/var/log/apache2/wsgi-ext.internal.anathoth.net-error.log"
            CustomLog "/var/log/apache2/wsgi-ext.internal.anathoth.net-access.log" common

            WSGIDaemonProcess dmsdms user=dmsdms group=dmsdms display-name=%{GROUP} python-path=/usr/share/dms
            WSGIProcessGroup dmsdms

            <Directory /usr/share/dms/www/documents>
            Order allow,deny
            Allow from all
            </Directory>

            <Directory /usr/share/dms/www/wsgi-scripts>
            # Make each WSGI script run in its own Python interpreter
            WSGIApplicationGroup %{RESOURCE}
            Order allow,deny
            #Allow from all
            Allow from none
            </Directory>

            <Location />
            Order allow,deny
            Allow from none
            </Location>

            WSGIScriptAlias /admin_dms /etc/dms/wsgi-scripts/admin_dms.wsgi

            <Location /admin_dms>
            AuthType Basic
            AuthName "Admin DMS"
            AuthUserFile /etc/apache2/htpasswd-dms
            Require user admin-dms
            </Location>


            WSGIScriptAlias /1stdomains_dms /etc/dms/wsgi-scripts/1stdomains_dms.wsgi

            <Location /1stdomains_dms>
            AuthType Basic
            AuthName "1stDomains DMS"
            AuthUserFile /etc/apache2/htpasswd-dms
            Require user 1stdomains-dms
            </Location>

            WSGIScriptAlias /helpdesk_dms /etc/dms/wsgi-scripts/helpdesk_dms.wsgi

            <Location /dms_dms>
            AuthType Basic
            AuthName "1stDomains DMS"
            AuthUserFile /etc/apache2/htpasswd-dms
            Require user dms-dms
            </Location>

        </VirtualHost>

Reload apache2 with::
       # service apache2 reload

Create WSGI accounts, and mind that you record the passwords for later::

       #   htpasswd -c /etc/apache2/htpasswd-dms admin-dms
       #   htpasswd /etc/apache2/htpasswd-dms net24-dms
       #   htpasswd /etc/apache2/htpasswd-dms 1stdomains-dms
       #   chown root:www-data /etc/apache2/htpasswd-dms
       #   chmod 640 /etc/apache2/htpasswd-dms

Check that it works:

       # curl -X POST -H 'Content-Type: application/json' -u admin-dms -d
       "@testing/test.jsonrpc" \
       http://dns-master1.grantma-imac/admin_dms

It should spew a lot of JSON content.

Rsyslog
=======

Create the file ``/etc/rsyslog.d/00network``::

       # provides UDP syslog reception
       $ModLoad imudp
       $UDPServerRun 514

       # provides TCP syslog reception
       $ModLoad imtcp
       $InputTCPServerRun 514

       # Sample Clients
       #$AllowedSender UDP,         [2001:470:c:110e::2]
       #$AllowedSender TCP,         [2001:470:c:110e::2]
       #$AllowedSender UDP,         [2001:470:66:23::2]
       #$AllowedSender TCP,         [2001:470:66:23::2]

and ``/etc/rsyslog.d/pgsql.conf``, setting the database password for rsyslog::

       ### Configuration file for rsyslog-pgsql
       ### Changes are preserved

       $ModLoad ompgsql
       # local7.* /var/log/local7.log
       local7.* :ompgsql:localhost,dms,rsyslog,ScrapyBee

Restart ``rsyslog``, and check ``/var/log/syslog`` for error messages. Also
do::

       # ps axc | grep rsyslogd
       20736   0 S        0:00.01 rsyslogd
       # lsof -p 20736

and you should see a connection listed to postgresql. Check ``/var/log/syslog``
for postgresql error messages.

Master Server Bind Logging Setup

Add the following to /etc/namedb or /etc/bind as logging.conf, and include it::

       // Logging
       logging {
               channel master_server {
                       // Sends log messages to master server.
                       syslog local7;
                       severity info;
               };
               // Lots of notifies bounce around, giving heaps of refused messages
               // that are basically noise
               category notify {null;};
               // Both below are default bind options. Here for 'normality'
               category default { master_server; default_syslog; default_debug; };
               category unmatched { null; };
       };




Restart named and check the system events table in the dms database. Log messages should start appearing in it.

Master Server Firewall Setup
============================

IPsec SPD is not stateful, and for 2 way traffic, it is easier just to set it
up to allow all traffic in both directions. System IP filtering on the DMS
master server should be used to protect the master server. It is possible to
detect IPSEC traffic in iptables,  and filter that incoming traffic statefully.

Here is a Sample iptables set up for Linux. Notice the INPUT rule diverting all
incoming IPSEC traffic into the ``ipsec-in`` rule, which ends in a ``log``
chain that DROPs disallowed traffic. There are also a couple of rules for local
system admin traffic as one of the slaves is a internal host in this example.
The latter is not typical of a large scale setup.

::

      # Completed on Sun Mar 4 16:30:11 2012
      # Generated by ip6tables-save v1.4.12.2 on Sun Mar 4 16:30:11 2012
      *filter
      :INPUT ACCEPT [66:5920]
      :FORWARD ACCEPT [0:0]
      :OUTPUT ACCEPT [33:3448]
      :ipsec-in - [0:0]
      :log - [0:0]
      -A INPUT -m policy --dir in --pol ipsec -j ipsec-in
      -A ipsec-in -m state --state RELATED,ESTABLISHED -j ACCEPT
      -A ipsec-in -p udp -m udp --sport 500 --dport 500 -j ACCEPT
      -A ipsec-in -p ipv6-icmp -m icmp6 --icmpv6-type 129 -j ACCEPT
      -A ipsec-in -p udp -m state --state NEW -m udp --dport 53 -j ACCEPT
      -A ipsec-in -p udp -m state --state NEW -m udp --dport 514 -j ACCEPT
      -A ipsec-in -p tcp -m state --state NEW -m tcp --dport 53 -j ACCEPT
      -A ipsec-in -p tcp -m tcp --dport 53 -m state --state NEW -m frag --fragid
      0 --fragfirst -j ACCEPT
      -A ipsec-in -s fd14:828:ba69::/48 -p tcp -m tcp --dport 22 -m state --state
      NEW -j ACCEPT
      -A ipsec-in -s fd14:828:ba69::/48 -p tcp -m tcp --dport 80 -m state --state
      NEW -j ACCEPT
      -A ipsec-in -j log
      -A log -m limit --limit 3/sec -j LOG --log-prefix "Def log: - "
      --log-tcp-options --log-ip-options
      -A log -p icmp -j DROP
      -A log -j REJECT --reject-with icmp6-port-unreachable
      COMMIT
      # Completed on Sun Mar 4 16:30:11 2012

The above (and a FreeBSD IPFW2 example - IPv6 IPSEC did not work0 are in the
``etc/firewall`` directory of the ``dms`` git archive.







***************************
Administration Procedures
***************************

Adding a DNS Slave to DMS
=========================

Please refer to the Debian Install Documentation, :ref:`Setting-up-a-Slave-Server`

Break Fix Scenarios
===================

Log and Configuration Files
---------------------------

The following are detailed elsewhere in the documentation

 ======================================    ==================================================
 :file:`/var/log/dms/dmsdmd.log\*`         :command:`dmsdmd` logs

 :file:`/var/log/local7.log`               DMS named logs

 :file:`/var/log/syslog`                   Basically everything

 :file:`/etc/dms/dms.conf`                 :command:`dmsdmd`, WSGI and :command:`zone_tool` configuration file

 :file:`/etc/dms`                          Various passwords, templates and things
 ======================================    ==================================================

See :ref:`Named.conf and Zone Templating<>` for more details.

Checking DMS Status
-------------------

#) Check that :command:`named`, :command:`postgres`, and :command:`dmsdmd` are running on the master.
#) Using :command:`zone_tool show_dms_status` on master server::

       zone_tool > show_dms_status

       show_master_status:

                   MASTER_SERVER:         dms-akl

                   NAMED master configuration state:

                   hold_sg:               HOLD_SG_NONE
                   hold_sg_name:          None
                   hold_start:            Wed Nov 7 16:52:36 2012
                   hold_stop:             Wed Nov 7 17:02:36 2012
                   replica_sg_name:       vygr-replica
                   state:                 HOLD

       show_replica_sg:
               sg_name:                      vygr-replica
               config_dir:                   /etc/net24/server-config-templates
               master_address:               2406:1e00:1001:1::2
               master_alt_address:           2406:3e00:1001:1::2
               replica_sg:                   True
               zone_count:                   37

                   Replica SG named status:
                   dms-chc                             2406:3e00:1001:1::2

                            OK

        ls_server:
        dms-akl                       Wed Nov 7 16:52:46 2012                OK
                2406:1e00:1001:1::2                      None
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-chc                       Wed Nov 7 16:52:46 2012                OK
                2406:3e00:1001:1::2                      210.5.48.242
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-s1-akl                    Wed Nov 7 16:31:04 2012                RETRY
                2406:1e00:1001:2::2                      103.4.136.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
                retry_msg:
                   Server 'dms-s1-akl': SOA query - timeout waiting for
                   response, retrying
        dms-s1-chc                    Wed Nov 7 16:52:46 2012                OK
                2406:3e00:1001:2::2                      210.5.48.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss

        list_pending_events:
        ServerSMConfigure         dms-s1-akl                   Wed Nov   7 16:57:22
        2012
        ServerSMCheckServer       dms-chc                      Wed Nov   7 16:53:55
        2012
        ServerSMCheckServer       dms-akl                      Wed Nov   7 16:55:46
        2012
        ServerSMCheckServer       dms-s1-chc                   Wed Nov   7 16:57:06
        2012
        MasterSMHoldTimeout                                    Wed Nov   7 17:02:36
        2012

        zone_tool >

    * Check Master server name, that machine is actually the master.
    * Check master state, ``HOLD`` means named reconfigured in the last 10
      minutes.
    * All servers shown at bottom should be in ``OK`` or ``CONFIG`` states,
      staying in ``RETRY`` or ``BROKEN`` means server may not be contactable.
      ``RETRY`` or ``BROKEN`` states should also have a ``retry_msg:`` field
      giving the associated log message.
    * :command:`list_pending_events` shows events that have to be processed.
    * Any events that are scheduled in the past may indicate :command:`dmsdmd` having
      serious problems.

Failing Over as Master Server has Burned (or Subject to EQC Claim)
------------------------------------------------------------------

On the Replica::

      dms-chc: -root- [~]
      # dms_promote_replica
      + perl -pe s/^#(\s*local7.* :ompgsql:\S+,dms,rsyslog,.*$)/\1/ -i
      /etc/rsyslog.d/pgsql.conf
      + set +x
      [ ok ] Stopping enhanced syslogd: rsyslogd.
      [ ok ] Starting enhanced syslogd: rsyslogd.
      + perl -pe s/^NET24DMD_ENABLE=.*$/NET24DMD_ENABLE=true/ -i
      /etc/default/net24dmd
      + perl -pe s/^OPTIONS=.*$/OPTIONS="-u bind"/ -i /etc/default/bind9
      + set +x
      [....] Stopping domain name service...: bind9waiting for pid 8744 to die
      . ok
      [ ok ] Starting domain name service...: bind9.
      [ ok ] Starting net24dmd: net24dmd.
      + zone_tool write_rndc_conf
      + zone_tool reconfig_all
      + perl -pe s/^#+(.*zone_tool vacuum_all)$/\1/ -i /etc/cron.d/dms-core
      + do_dms_wsgi
      + return 0
      + perl -pe s/^(\s*exit\s+0.*$)/#\1/ -i /etc/default/apache2
      + set +x
      [ ok ] Starting web server: apache2.

      dms-chc: -root- [~]
      #

Wait till servers started, and then use :command:`zone_tool show_dms_status` to
check that everything becomes OK. This may take 15 minutes. The section about
:command:`ls_pending_events` will give scheduled times for servers to become
configured.

::

      dms-chc: -root- [~]
      # zone_tool show_dms_status

      show_master_status:

        MASTER_SERVER:      dms-chc

        NAMED master configuration state:

        hold_sg:            HOLD_SG_NONE
        hold_sg_name:       None
        hold_start:         Fri Nov 9 08:30:49 2012
        hold_stop:          Fri Nov 9 08:40:49 2012
        replica_sg_name:    vygr-replica
        state:              HOLD

        show_replica_sg:
                sg_name:              vygr-replica
                config_dir:           /etc/net24/server-config-templates
                master_address:       2406:1e00:1001:1::2
                master_alt_address:   2406:3e00:1001:1::2
                replica_sg:           True
                zone_count:           37

                Replica SG named status:
                dms-akl                         2406:1e00:1001:1::2

                        RETRY

        ls_server:
        dms-akl                       Fri Nov 9 08:23:08 2012                  RETRY
                2406:1e00:1001:1::2                      None
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
                retry_msg:
                   Server 'dms-akl': SOA query - timeout waiting for response,
                   retrying
        dms-chc                       Fri Nov 9 08:30:58 2012                  OK
                2406:3e00:1001:1::2                      210.5.48.242
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-s1-akl                    Fri Nov 9 08:30:58 2012                  OK
                2406:1e00:1001:2::2                      103.4.136.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-s1-chc                    Fri Nov 9 08:30:58 2012                  OK
                2406:3e00:1001:2::2                      210.5.48.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss

        list_pending_events:
        ServerSMCheckServer        dms-chc                        Fri Nov   9 08:39:53
        2012
        MasterSMHoldTimeout                                       Fri Nov   9 08:40:49
        2012
        ServerSMCheckServer        dms-s1-chc                     Fri Nov   9 08:40:08
        2012
        ServerSMCheckServer        dms-s1-akl                     Fri Nov   9 08:36:01
        2012
        ServerSMConfigure          dms-akl                        Fri Nov   9 08:50:17
        2012


      dms-chc: -root- [~]
      #

A new replica will need to be installed as per :ref:`DMS Master Server
Install<DMS-Master-Server-Install>`

Stuck Zone not Propagating
--------------------------

::

      zone_tool > show_zonesm wham-blam.org
              name:            wham-blam.org.
              alt_sg_name:     None
              auto_dnssec:     False
              ctime:           Thu Aug 23 10:51:14 2012
              deleted_start:   None
              edit_lock:       True
              edit_lock_token: None
              inc_updates:     False
              lock_state:      EDIT_UNLOCK
              locked_at:       None
              locked_by:       None
              mtime:           Thu Aug 23 10:51:14 2012
              nsec3:           True
              reference:       nutty-nutty@ANATHOTH-NET
              sg_name:         anathoth-internal
              soa_serial:      2012091400
              state:           UNCONFIG
              use_apex_ns:     True
              zi_candidate_id: 102880
              zi_id:           102880
              zone_id:         101448
              zone_type:       DynDNSZoneSM

                 zi_id:                  102880
                 change_by:              grantma@shalom-ext.internal.anathoth.net/Admin
                 ctime:                  Fri Sep 14 10:55:59 2012
                 mtime:                  Fri Sep 14 11:12:10 2012
                 ptime:                  Fri Sep 14 11:12:10 2012
                 soa_expire:             7d
                 soa_minimum:            600
                 soa_mname:              ns1.internal.anathoth.net.
                 soa_refresh:            24h
                 soa_retry:              900
                 soa_rname:              matthewgrant5.gmail.com.
                 soa_serial:             2012091400
                 soa_ttl:                None
                 zone_id:                101448
                 zone_ttl:               24h

Maybe as above. Can be caused by:

      * Failed events (manually failed or otherwise, Events queue deleted in
        DB, permissions problems as follows)

      * Permissions problems on the master server on the
        :file:`/var/lib/bind/dynamic` directory - should be::

            # ls -ld /var/lib/bind/dynamic/
            drwxrwsr-x 2 bind dmsdmd 487424 Nov                9 08:47 /var/lib/bind/dynamic/

Do a :command:`reset_zonesm wham-blam.org`, (noting y/N and :abbr:`DNSSEC`
:abbr:`RRSIGs` being destroyed)::


      zone_tool > reset_zonesm wham-blam.org.
      ***   WARNING - doing this destroys DNSSEC RRSIG data.
      ***   Do really you wish to do this?
              --y/[N]> y
      zone_tool > 

And check again::

      zone_tool > show_zonesm wham-blam.org
              name:            wham-blam.org.
              alt_sg_name:     None
              auto_dnssec:     False
              ctime:           Thu Aug 23 10:51:14 2012
              deleted_start:   None
              edit_lock:       True
              edit_lock_token: None
              inc_updates:     False
              lock_state:      EDIT_UNLOCK
              locked_at:       None
              locked_by:       None
              mtime:           Thu Aug 23 10:51:14 2012
              nsec3:           True
              reference:       nutty-nutty@ANATHOTH-NET
              sg_name:         anathoth-internal
              soa_serial:      2012091400
              state:           RESET
              use_apex_ns:     True
              zi_candidate_id: 102880
              zi_id:           102880
              zone_id:         101448
              zone_type:       DynDNSZoneSM

                zi_id:                 102880
                change_by:             grantma@shalom-ext.internal.anathoth.net/Admin
                ctime:                 Fri Sep 14 10:55:59 2012
                mtime:                 Fri Sep 14 11:12:10 2012
                ptime:                 Fri Sep 14 11:12:10 2012
                soa_expire:            7d
                soa_minimum:           600
                soa_mname:             ns1.internal.anathoth.net.
                soa_refresh:           24h
                soa_retry:             900
                soa_rname:             matthewgrant5.gmail.com.
                soa_serial:            2012091400
                soa_ttl:               None
                zone_id:               101448
                zone_ttl:              24h

And then use :command:`show_zonesm` to check that zone state goes to
``PUBLISHED`` within 15 minutes. :command:`ls_pending_events` may also be
useful, as it will show the events to do with the zone being published.

::

       show_zonesm wham-blam.org
               name:             wham-blam.org.
               alt_sg_name:      None
               auto_dnssec:      False
               ctime:            Thu Aug 23 10:51:14 2012
               deleted_start:    None
               edit_lock:        True
               edit_lock_token: None
               inc_updates:      False
               lock_state:       EDIT_UNLOCK
               locked_at:        None
               locked_by:        None
               mtime:            Thu Aug 23 10:51:14 2012
               nsec3:            True
               reference:        nutty-nutty@ANATHOTH-NET
               sg_name:          anathoth-internal
               soa_serial:       2012091400
               state:            RESET
               use_apex_ns:      True
               zi_candidate_id: 102880
               zi_id:            102880
               zone_id:          101448
               zone_type:        DynDNSZoneSM

               zi_id:           102880
               change_by:       grantma@shalom-ext.internal.anathoth.net/Admin
               ctime:           Fri Sep 14 10:55:59 2012
               mtime:           Fri Sep 14 11:12:10 2012
               ptime:           Fri Sep 14 11:12:10 2012
               soa_expire:      7d
               soa_minimum:     600
               soa_mname:       ns1.internal.anathoth.net.
               soa_refresh:     24h
               soa_retry:       900
               soa_rname:       matthewgrant5.gmail.com.
               soa_serial:      2012091400
               soa_ttl:         None
               zone_id:         101448
               zone_ttl:        24h
       zone_tool > ls_pending_events
       ServerSMCheckServer       shalom                       Fri Nov 9 08:50:35
       2012
       ServerSMCheckServer       shalom-ext                   Fri Nov 9 08:50:40
       2012
       ServerSMCheckServer       shalom-dr                    Fri Nov 9 08:50:46
       2012
       ServerSMCheckServer       dns-slave1                   Fri Nov 9 08:50:53
       2012
       ServerSMConfigure         en-gedi-auth                 Fri Nov 9 08:55:31
       2012

       ZoneSMConfig              wham-blam.org.              Fri Nov   9 08:47:07
       2012
       MasterSMHoldTimeout                                   Fri Nov   9 08:56:52
       2012
       ServerSMCheckServer       dns-slave0                  Fri Nov   9 08:54:29
       2012
       zone_tool > show_zonesm wham-blam.org
               name:            wham-blam.org.
               alt_sg_name:     None
               auto_dnssec:     False
               ctime:           Thu Aug 23 10:51:14 2012
               deleted_start:   None
               edit_lock:       True
               edit_lock_token: None
               inc_updates:     False
               lock_state:      EDIT_UNLOCK
               locked_at:       None
               locked_by:       None
               mtime:           Thu Aug 23 10:51:14 2012
               nsec3:           True
               reference:       nutty-nutty@ANATHOTH-NET
               sg_name:         anathoth-internal
               soa_serial:      2012091400
               state:           UNCONFIG
               use_apex_ns:     True
               zi_candidate_id: 102880
               zi_id:           102880
               zone_id:         101448
               zone_type:       DynDNSZoneSM

               zi_id:           102880
               change_by:       grantma@shalom-ext.internal.anathoth.net/Admin
               ctime:           Fri Sep 14 10:55:59 2012
               mtime:           Fri Sep 14 11:12:10 2012
               ptime:           Fri Sep 14 11:12:10 2012
               soa_expire:      7d
               soa_minimum:     600
               soa_mname:       ns1.internal.anathoth.net.
               soa_refresh:     24h
               soa_retry:       900
               soa_rname:       matthewgrant5.gmail.com.
               soa_serial:      2012091400
               soa_ttl:         None
               zone_id:         101448
               zone_ttl:        24h
       zone_tool > ls_pending_events
       ServerSMCheckServer       shalom                       Fri Nov 9 08:50:35
       2012
       ServerSMCheckServer       shalom-ext                   Fri Nov 9 08:50:40
       2012
       ServerSMCheckServer       shalom-dr                    Fri Nov 9 08:50:46
       2012
       ServerSMCheckServer       dns-slave1                   Fri Nov 9 08:50:53

       2012
       ServerSMConfigure         en-gedi-auth                 Fri Nov   9 08:55:31
       2012
       MasterSMHoldTimeout                                    Fri Nov   9 08:56:52
       2012
       ServerSMCheckServer       dns-slave0                   Fri Nov   9 08:54:29
       2012
       ZoneSMReconfigUpdate      wham-blam.org.               Fri Nov   9 08:57:10
       2012
       zone_tool > ls_pending_events
       ServerSMCheckServer       shalom-ext                   Fri Nov   9 09:00:25
       2012
       ServerSMCheckServer       shalom-dr                    Fri Nov   9 09:00:44
       2012
       ServerSMCheckServer       dns-slave0                   Fri Nov   9 09:01:25
       2012
       ServerSMCheckServer       dns-slave1                   Fri Nov   9 09:02:11
       2012
       ServerSMConfigure         en-gedi-auth                 Fri Nov   9 09:06:15
       2012
       MasterSMHoldTimeout                                    Fri Nov   9 09:06:57
       2012
       ServerSMCheckServer       shalom                       Fri Nov   9 09:05:11
       2012
       zone_tool > show_zonesm wham-blam.org
               name:            wham-blam.org.
               alt_sg_name:     None
               auto_dnssec:     False
               ctime:           Thu Aug 23 10:51:14 2012
               deleted_start:   None
               edit_lock:       True
               edit_lock_token: None
               inc_updates:     False
               lock_state:      EDIT_UNLOCK
               locked_at:       None
               locked_by:       None
               mtime:           Thu Aug 23 10:51:14 2012
               nsec3:           True
               reference:       nutty-nutty@ANATHOTH-NET
               sg_name:         anathoth-internal
               soa_serial:      2012091400
               state:           PUBLISHED
               use_apex_ns:     True
               zi_candidate_id: 102880
               zi_id:           102880
               zone_id:         101448
               zone_type:       DynDNSZoneSM

               zi_id:           102880
               change_by:       grantma@shalom-ext.internal.anathoth.net/Admin
               ctime:           Fri Sep 14 10:55:59 2012
               mtime:           Fri Nov 9 08:57:13 2012
               ptime:           Fri Nov 9 08:57:13 2012

       soa_expire:    7d
       soa_minimum:   600
       soa_mname:     ns1.internal.anathoth.net.
       soa_refresh:   24h
       soa_retry:     900
       soa_rname:     matthewgrant5.gmail.com.
       soa_serial:    2012091400
       soa_ttl:       None
       zone_id:       101448
       zone_ttl:                24h
       zone_tool >

MasterSM Stuck, New Zones not Being Created
-------------------------------------------

Can be caused by:

      * Failed ``MasterSMHoldTimeout`` events (manually failed or otherwise,
        Events queue deleted in DB etc)

      * Permissions problems on the master server on the
        :file:`/etc/bind/master-config directory` - Should be ``2755
        dmsdmd:bind``::

            shalom-ext: -grantma- [~]
            $ ls -ld /etc/bind/master-config
            drwxr-sr-x 2 net24dmd bind 4096 Nov          9 08:56 /etc/bind/master-config

This shows up in :command:`zone_tool show_dms_status`::


      zone_tool > show_dms_status

      show_master_status:

                MASTER_SERVER:            dms-akl

                NAMED master configuration state:

                hold_sg:                  HOLD_SG_NONE
                hold_sg_name:             None
                hold_start:               Wed Nov 7 16:52:36 2012
                hold_stop:                Wed Nov 7 17:02:36 2012
                replica_sg_name:          vygr-replica
                state:                    HOLD

      show_replica_sg:
              sg_name:                       vygr-replica
              config_dir:                    /etc/net24/server-config-templates
              master_address:                2406:1e00:1001:1::2
              master_alt_address:            2406:3e00:1001:1::2
              replica_sg:                    True
              zone_count:                    37

                Replica SG named status:
                dms-chc                                2406:3e00:1001:1::2

                           OK

      ls_server:
        dms-akl                      Wed Nov 7 16:52:46 2012                 OK
              2406:1e00:1001:1::2                     None
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-chc                       Wed Nov 7 16:52:46 2012                OK
                2406:3e00:1001:1::2                      210.5.48.242
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dms-s1-akl                    Wed Nov 7 16:31:04 2012                RETRY
                2406:1e00:1001:2::2                      103.4.136.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
                retry_msg:
                   Server 'dms-s1-akl': SOA query - timeout waiting for
                   response, retrying
        dms-s1-chc                    Wed Nov 7 16:52:46 2012                OK
                2406:3e00:1001:2::2                      210.5.48.226
                ping: 5 packets transmitted, 5 received, 0.00% packet loss

        list_pending_events:
        ServerSMConfigure         dms-s1-akl                   Wed Nov   7 16:57:22
        2012
        ServerSMCheckServer       dms-chc                      Wed Nov   7 16:53:55
        2012
        ServerSMCheckServer       dms-akl                      Wed Nov   7 16:55:46
        2012
        ServerSMCheckServer       dms-s1-chc                   Wed Nov   7 16:57:06
        2012


        zone_tool > exit

        dms-akl: -root- [~]
        # date
        Wed Nov      7 16:54:42 NZDT 2012

Key things to look for:

       * master status section shows ``hold_start`` and ``hold_stop`` being in the past

       * there is no ``MasterSMHoldTimeout`` event

.. note::
            The MasterSM state machine forward posts the MasterSMHoldTimeout event when entering the
            HOLD state. If it does not get created or disappears or fails due to unforeseen events with
            outages etc, the MasterSM will end up stuck as above.

The fix is to do :command:`zone_tool reset_master`. This will reset the ``MasterSM`` state machine.

Stuck ServerSM
--------------

Just like the ``Master`` state machine getting stuck because of a missing
``MasterSMHoldTimeout event``, Server :abbr:`SMs` can end up being stuck in the
``CONFIG``, ``RETRY`` or ``BROKEN`` states due to missing events. There will be
missing ``ServerSMConfigure`` events for the server in the
:command:`ls_pending_events` output::

        zone_tool > show_dms_status
        show_master_status:
                MASTER_SERVER:      shalom-ext
                NAMED master configuration state:
                hold_sg:            HOLD_SG_NONE
                hold_sg_name:       None
                hold_start:         None
                hold_stop:          None
                replica_sg_name:    anathoth-replica
                state:              READY
        show_replica_sg:
                sg_name:              anathoth-replica
                config_dir:           /etc/bind/anathoth-master
                master_address:       2001:470:f012:2::2
                master_alt_address: 2001:470:f012:2::3
                replica_sg:           True
                zone_count:           14
                Replica SG named status:
                shalom-dr                      2001:470:f012:2::3
                         OK
        ls_server:
        dns-slave0                    Fri Nov 9 09:56:48 2012                  OK
                2001:470:c:110e::2                        111.65.238.10
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        dns-slave1                    Fri Nov 9 09:56:38 2012                  OK
                2001:470:66:23::2                         111.65.238.11
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        en-gedi-auth                  Thu Nov 8 18:01:07 2012                  RETRY
                fd14:828:ba69:6:5054:ff:fe39:54f9         172.31.12.2
                ping: 5 packets transmitted, 0 received, 100.00% packet loss
                retry_msg:
                   Server 'en-gedi-auth': failed to rsync include files,
                   Command '['rsync', '--quiet', '-av', '--password-file',
                   '/etc/net24/rsync-dnsconf-password', '/var/lib/net24/dms-sg
                   /anathoth-internal/',
                   'dnsconf@[fd14:828:ba69:6:5054:ff:fe39:54f9]::dnsconf/']'
                   returned non-zero exit status 10, rsync: failed to connect
                   to fd14:828:ba69:6:5054:ff:fe39:54f9
                   (fd14:828:ba69:6:5054:ff:fe39:54f9): Connection timed out
                   (110), rsync error: error in socket IO (code 10) at
                   clientserver.c(122) [sender=3.0.9]
        shalom                        Fri Nov 9 09:56:19 2012                  OK
                fd14:828:ba69:1:21c:f0ff:fefa:f3c0        192.168.110.1
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        shalom-dr                     Fri Nov 9 09:56:56 2012                  OK
                2001:470:f012:2::3                        172.31.10.4
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        shalom-ext                    Fri Nov 9 09:58:21 2012                  OK
                2001:470:f012:2::2                        172.31.10.2
                ping: 5 packets transmitted, 5 received, 0.00% packet loss
        list_pending_events:
        ServerSMCheckServer        shalom                         Fri Nov 9 10:01:43   2012
        ServerSMCheckServer        dns-slave1                     Fri Nov 9 10:01:55   2012
        ServerSMCheckServer        dns-slave0                     Fri Nov 9 10:03:17   2012
        ServerSMCheckServer        shalom-dr                      Fri Nov 9 10:05:25   2012
        ServerSMCheckServer        shalom-ext                     Fri Nov 9 10:04:49   2012
        zone_tool >

.. note::

         Above, the ``ls_server`` section of ``show_dms_status`` displays the
         reason for going to ``RETRY`` or ``BROKEN`` in the displayed
         ``retry_msg`` field.

The fix, :command:`reset_server` the server, and use :command:`ls_pending_events` to check an
``ServerSMConfigure`` event is created::


      zone_tool > reset_server en-gedi-auth
      zone_tool > ls_pending_events
      ServerSMCheckServer       shalom                                  Fri   Nov   9   12:11:17   2012
      ServerSMCheckServer       shalom-ext                              Fri   Nov   9   12:11:47   2012
      ServerSMCheckServer       en-gedi-auth                            Fri   Nov   9   12:14:57   2012
      ServerSMCheckServer       dns-slave0                              Fri   Nov   9   12:18:02   2012
      ServerSMCheckServer       shalom-dr                               Fri   Nov   9   12:15:09   2012
      ServerSMCheckServer       dns-slave1                              Fri   Nov   9   12:19:08   2012
      ServerSMConfigure         en-gedi-auth                            Fri   Nov   9   12:10:39   2012
      zone_tool >

Wait until the scheduled time posted for ``ServerSMConfigure``, and then do a
:command:`zone_tool show_dms_status` to make sure everything is going::

      zone_tool > show_dms_status
      show_master_status:
              MASTER_SERVER:      shalom-ext
              NAMED master configuration state:
              hold_sg:            HOLD_SG_NONE
              hold_sg_name:       None
              hold_start:         None
              hold_stop:          None
              replica_sg_name:    anathoth-replica
              state:              READY
      show_replica_sg:
              sg_name:              anathoth-replica
              config_dir:           /etc/bind/anathoth-master
              master_address:       2001:470:f012:2::2
              master_alt_address: 2001:470:f012:2::3
              replica_sg:           True
              zone_count:           14
              Replica SG named status:
              shalom-dr                      2001:470:f012:2::3
                       OK
      ls_server:
      dns-slave0                    Fri Nov 9 12:08:29 2012                  OK
              2001:470:c:110e::2                        111.65.238.10
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      dns-slave1                    Fri Nov 9 12:10:19 2012                  OK
              2001:470:66:23::2                         111.65.238.11
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      en-gedi-auth                  Fri Nov 9 12:10:43 2012                  OK
              fd14:828:ba69:6:5054:ff:fe39:54f9         172.31.12.2
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      shalom                        Fri Nov 9 12:11:19 2012                  OK
              fd14:828:ba69:1:21c:f0ff:fefa:f3c0        192.168.110.1
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      shalom-dr                     Fri Nov 9 12:09:44 2012                  OK
              2001:470:f012:2::3                        172.31.10.4
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      shalom-ext                    Fri Nov 9 12:11:47 2012                  OK
              2001:470:f012:2::2                        172.31.10.2
              ping: 5 packets transmitted, 5 received, 0.00% packet loss
      list_pending_events:
      ServerSMCheckServer        en-gedi-auth                   Fri Nov 9 12:14:57   2012
      ServerSMCheckServer        dns-slave0                     Fri Nov 9 12:18:02   2012
      ServerSMCheckServer        shalom-dr                      Fri Nov 9 12:15:09   2012
      ServerSMCheckServer        dns-slave1                     Fri Nov 9 12:19:08   2012
      ServerSMCheckServer        shalom                         Fri Nov 9 12:17:44   2012
      ServerSMCheckServer        shalom-ext                     Fri Nov 9 12:17:31   2012
      zone_tool >

Rebuilding named data from database
-----------------------------------

The named dynamic data in :file:`/var/lib/bind/dynamic` is corrupt, or missing

    #. Stop :command:`named` and :command:`dmsdmd`::

           root@dms3-master:~# service bind9 stop
           [....] Stopping domain name service...: bind9waiting for pid 15462 to die
           . ok
           root@dms3-master:~# service net24dmd stop
           [ ok ] Stopping net24dmd: net24dmd.

    #. Check :file:`/var/lib/dms/master_config` and :file:`/var/lib/bind/dynamic` permissions.
           :file:`/var/lib/dms/master-config`, should be ``2755 dmsdmd:bind``::

                   root@dms3-master:~# ls -ld /var/lib/dms/master-config/
                   drwxr-sr-x 2 dmsdmd bind 4096 Nov 9 12:39 /var/lib/dms/master-config/
                   root@dms3-master:~#

             :file:`/var/lib/bind/dynamic`, should be ``2775 bind:dmsdmd``::


                   root@dms3-master:~# ls -ld /var/lib/bind/dynamic
                   drwxrwsr-x 2 bind dmsdmd 1683456 Nov 9 12:39 /var/lib/bind/dynamic
                   root@dms3-master:~#



    #. Clear any files from :file:`/var/lib/bind/dynamic` if needed::

               root@dms3-master:~# rm -rf /var/lib/bind/dynamic/*
               root@dms3-master:~#

    #. Run the restore process which recreates :file:`/etc/bind/master-config/` contents, and recreates contents of
       :file:`/var/lib/bind/dynamic`. This may take some time. 40000 zones takes 20 - 30 minutes.

        ::

               root@dms3-master:~# zone_tool restore_named_db
               ***   WARNING - doing this destroys DNSSEC RRSIG data. It is a last
                     resort in DR recovery.
               ***   Do really you wish to do this?
                --y/[N]> y

    #. Start :command:`named` and :command:`dmsdmd`::

               root@dms3-master:~# service dmsdmd start
               [ ok ] Starting dmsdmd: dmsdmd.
               root@dms3-master:~# service bind9 start
               [ ok ] Starting domain name service...: bind9.
               root@dms3-master:~#

Failed Master, Replica /etc not up to date
------------------------------------------

The master and DR replica have the :command:`etckeeper` git archive mirrored
every 4 hours to the alternate server.  See :ref:`etckeeper and /etc on Replica
and Master Servers <>`

Recovering DB from Backup
-------------------------

:file:`/etc/cron.d/dms-core` does daily FULL :command:`pg_dumpall` to
:file:`/var/backups/postresql-9.1-dms.sql.gz`, on replica and master, which are
rotated for 7 days.

To recover::

      # cd /var/backups
      # gunzip -c postregresql-9.1-dms.sql.gz | psql -U pgsql

There will be lots of :abbr:`SQL` output. The dump also contains DB user passwords, and
:abbr:`ACL`/permissions information, along with DB details for the whole PostgresQL
'dms' cluster.

Regenerating :file:`ds/` DS material directory from Private Keys
----------------------------------------------------------------

Use the :command:`dns-recreateds` command to recreate a domains :abbr:`DNSSEC`
:abbr:`DS` material. The :file:`/var/lib/bind/keys` directory is rsynced to the
:abbr:`DR` replica by the master server :command:`dmsdmd` daemon. Use a '*'
argument to regenerate all :abbr:`DS` material.

::

      shalom-ext: -root- [/var/lib/bind/keys]
      # dns-recreateds anathoth.net
      + dnssec-dsfromkey -2 /var/lib/bind/keys/Kanathoth.net.+007+57318.key
      + set +x
      shalom-ext: -root- [/var/lib/bind/keys]
      #

IPSEC not going
---------------

These examples are between DNS slave server dns-slave1 and master shalom-ext,
using :command:`racoon`, via :command:`racoon-tool` in Debian Wheezy.

.. note::

   The ICMPv6 setup is specific to this Debian Wheezy :command:`racoon` setup.
   However, the test techniques are also applicable to usewith Strongswan and
   other IPSEC software.

Diagnosis
^^^^^^^^^

:command:`Ping6` server from master and vice-versa to check unencrypted network
level. (Transport mode encryption does not encrypt ICMPv6). Use the
:command:`zone_tool ls_server -v` command to get the DMS configured IPv6
addresses of both servers.

::

      shalom-ext: -grantma- [~/dms]
      $ zone_tool ls_server -v dns-slave1
      dns-slave1 Mon Nov 12 13:57:20 2012 OK
       2001:470:66:23::2 111.65.238.11

      shalom-ext: -grantma- [~/dms]
      $ zone_tool ls_server -v shalom-ext
      shalom-ext                    Mon Nov 12 13:59:29 2012                           OK
              2001:470:f012:2::2                       172.31.10.2
      shalom-ext: -grantma- [~/dms]
      $ ping6 2001:470:66:23::2
      PING 2001:470:66:23::2(2001:470:66:23::2) 56 data bytes
      64 bytes from 2001:470:66:23::2: icmp_seq=1 ttl=58 time=312 ms
      64 bytes from 2001:470:66:23::2: icmp_seq=2 ttl=58 time=310 ms
      64 bytes from 2001:470:66:23::2: icmp_seq=3 ttl=58 time=310 ms
      ^C
      --- 2001:470:66:23::2 ping statistics ---
      3 packets transmitted, 3 received, 0% packet loss, time 2003ms
      rtt min/avg/max/mdev = 310.646/311.293/312.518/0.866 ms
      shalom-ext: -grantma- [~/dms]
      $

Telnet domain TCP ports both ways, and rsync out to slave server
from master. This checks that IPSEC encryption is running.

From shalom-ext::

       shalom-ext: -grantma- [~/dms]
       $ telnet 2001:470:66:23::2 53
       Trying 2001:470:66:23::2...
       Connected to 2001:470:66:23::2.
       Escape character is '^]'.
       ^]c
       telnet> c
       Connection closed.
       shalom-ext: -grantma- [~/dms]
       $ telnet 2001:470:66:23::2 rsync
       Trying 2001:470:66:23::2...
       Connected to 2001:470:66:23::2.
       Escape character is '^]'.
       @RSYNCD: 30.0
       ^]c
       telnet> c
       Connection closed.
       shalom-ext: -grantma- [~/dms]
       $

From dns-slave1::

       grantma@dns-slave1:~$ telnet 2001:470:f012:2::2 53
       Trying 2001:470:f012:2::2...
       Connected to 2001:470:f012:2::2.
       Escape character is '^]'.
       ^]c
       telnet> c
       Connection closed.
       grantma@dns-slave1:~$

If the DNS server is a DR replica, telnet the rsync port the other way also.

Recovery
^^^^^^^^

For :command:`racoon` and :command:`strongswan`, if things are not working
restart the IPSEC connection at both ends:

.. note::

   For Strongswan, use the :command:`ipsec up/down <connection-name>`.
   :command:`ipsec status [<connection-name>]` can be used to list all
   connections, and query about status.

:command:`racoon` shalom-ext master::

       shalom-ext: -root- [/home/grantma/dms]
       # racoon-tool vlist
       shalom-dr
       dns-slave1
       %anonymous
       shalom-ext
       shalom
       dns-slave0
       en-gedi-auth
       shalom-ext: -root- [/home/grantma/dms]
       # racoon-tool vreload dns-slave1
       Reloading VPN dns-slave1...The result of line 2: No entry.
       The result of line 5: No entry.
       done.
       shalom-ext: -root- [/home/grantma/dms]
       #

:command:`racoon` dns-slave1::

       root@dns-slave1:/home/grantma# racoon-tool vlist
       shalom-dr
       %anonymous
       shalom-ext
       root@dns-slave1:/home/grantma# racoon-tool vreload shalom-ext
       Reloading VPN shalom-ext...The result of line 2: No entry.
       The result of line 5: No entry.
       done.
       root@dns-slave1:/home/grantma#


.. note::
   
        Wait 10 minutes for IPSEC replay timing to expire. Then retry the telnet steps above.


If IPSEC still will not work:

For :command:`racoon`, Use :command:`racoon-tool restart` on both ends. For
strongswan, use :command:`ipsec restart` on both ends.

shalom-ext::

       shalom-ext: -root- [/home/grantma/dms]
       # racoon-tool restart
       Stopping IKE (ISAKMP/Oakley) server: racoon.
       Flushing SAD and SPD...
       SAD and SPD flushed.
       Unloading IPSEC/crypto modules...
       IPSEC/crypto modules unloaded.
       Loading IPSEC/crypto modules...
       IPSEC/crypto modules loaded.
       Flushing SAD and SPD...
       SAD and SPD flushed.
       Loading SAD and SPD...
       SAD and SPD loaded.
       Configuring racoon...done.
       Starting IKE (ISAKMP/Oakley) server: racoon.
       shalom-ext: -root- [/home/grantma/dms]
       #

dns-slave1::

       root@dns-slave1:/home/grantma# racoon-tool restart
       Stopping IKE (ISAKMP/Oakley) server: racoon.
       Flushing SAD and SPD...
       SAD and SPD flushed.
       Unloading IPSEC/crypto modules...
       IPSEC/crypto modules unloaded.
       Loading IPSEC/crypto modules...
       IPSEC/crypto modules loaded.
       Flushing SAD and SPD...
       SAD and SPD flushed.
       Loading SAD and SPD...
       SAD and SPD loaded.
       Configuring racoon...done.
       Starting IKE (ISAKMP/Oakley) server: racoon.
       root@dns-slave1:/home/grantma#

.. note::

              Wait 10 minutes for IPSEC replay timing to expire. Then retry the telnet steps above.

.. _DMS-Master-Server-Install:

DMS Master Server Install
=========================

Base Operating System: Debian Wheezy or later.

Create :file:`/etc/apt/apt.conf.d/00local.conf`::

        // No point in installing a lot of fat on VM servers
        APT::Install-Recommends "0";
        APT::Install-Suggests "0";

Create :file:`/etc/apt/sources.list.d/00local.conf`::

        deb http://deb-repo.devel.net.nz/debian/ wheezy main
        deb-src http://deb-repo.devel.net.nz/debian/ wheezy main

Install these packages::

        # apt-get install cron-apt screen tree procps psmisc sysstat sudo lsof open-vm-tools open-vm-dkms dms

If using ``netscript-2.4`` instead of ``ifupdown`` to properly install it because of cyclic boot
dependencies (I will look into this when have some spare time, and log an RC
Debian bug)::

        # dpkg --force --purge ifupdown
        # apt-get -f install

Further, for ``netscript-2.4``,  edit :file:`/etc/netscript/network.conf` to configure
static addressing. Look for ``IF_AUTO``, set ``eth0_IPADDR``, and further down
comment out ``eth_start`` and ``eth_stop`` functions to turn
off :abbr:`DHCP`. 

.. note::

   For most setups, ``netscript-ipfilter`` is a suitable package for managing
   Linux filtering rules without replacing ``ifupdown``.

``Netscript-2.4`` and ``netscript-ipfilter`` manage :command:`iptables` and
:command:`ip6tables` via :command:`iptables-save`/:command:`iptables-restore`,
and keeps a cyclic history which you can change back to if your filter changes
go wrong via :command:`netscript ipfilter/ip6filter save/usebackup`.

Then::

        # aptitude update
        # aptitude upgrade

shell.tar.gz
------------

.. note::

      This is just a personal Debian prompt thing of mine. You might say I get
      too personal...
      
To fix shell prompt for larger terminals on master server makes typing in long
zone_tool commands at shell a lot clearer::

        # tar -C / -xzf shell.tar.gz

Replaces :file:`/etc/skel` shell and :file:`/root` dot files with single line feed to force use of file in :file:`/etc`

Then edit :file:`/etc/environment.sh` to turn off various things like ``umask 00002`` for user id less than 1000.

Completing DMS Setup
--------------------
      
Then follow :ref:`Debian Install <Debian-Install>` documentation.




**********************
Frequent Procedures
**********************

Various frequent procedures are listed here. They are typical of the day to
day management of zones with DMS.

Creating and Copying Zones
==========================

Zones are created using the ``create_zone`` command::

       zone_tool > create_zone test1.com
       zone_tool > show_zone test1.com
       $TTL 1h
       $ORIGIN test1.com.

       ;
       ;   Zone:          test1.com.
       ;   Reference:     anathoth
       ;   change_by:     grantma@shalom-ext.internal.anathoth.net/Admin
       ;   zi_id:         103187
       ;   zi_ctime:      Wed Oct 17 13:19:15 2012
       ;   zi_mtime:      Wed Oct 17 13:19:15 2012
       ;


       ;| Apex resource records for test1.com.
       ;!REF:anathoth
       @                       IN      SOA                                ( ns1.anathoth.net. ;Master
       NS
                                                                          matthewgrant5.gmail.com.
       ;RP email
                                                                          2012101700         ;Serial
       yyyymmddnn
                                                                          86400              ;Refresh
                                                                          900                ;Retry
                                                                          604800             ;Expire
                                                                          3600
       ;Minimum/Ncache
                                                                          )
                                         IN         NS                    ns3.anathoth.net.
                                         IN         NS                    ns2.anathoth.net.
                                         IN         NS                    ns1.anathoth.net.


       zone_tool > create_zone test1.com
       ***   Zone 'test1.com.' already exists.
       zone_tool >

When a zone is just created, only the Apex records are filled in thus achieving
the result of just technically parking the domain if it is then registered with
the registry service (in New Zealand that is typically ENOM or the NZRS).

They can also be created from any given ZI by using the copy_zone command::

      zone_tool > help copy_zone
              Copy a zone:

                 copy_zone [-g <ssg-name>] [-i] [ -r reference] [-z zi_id]
                                   <src-domain-name> <domain-name> [zone-option] ...
                 where   -g <ssg-name>: specify an SSG name other than default_ssg
                         -i:            set inc_updates flag on the new zone
                         -r reference: set reference
                         -z zi_id:      set zi_id used for copy source
                         zone-option:   use_apex_ns|auto_dnssec|edit_lock|nsec3
                                         |inc_updates
                                                 up to 5 times

      zone_tool > copy_zone test1.com bad-thing.org
      zone_tool > show_zone bad-thing.org
      $TTL 24h
      $ORIGIN bad-thing.org.

      ;
      ;   Zone:          bad-thing.org.
      ;   Reference:     anathoth
      ;   change_by:     grantma@shalom-ext.internal.anathoth.net/Admin
      ;   zi_id:         102602
      ;   zi_ctime:      Thu Aug 23 14:54:07 2012
      ;   zi_mtime:      Thu Aug 23 14:54:07 2012
      ;


      ;| Apex resource records for bad-thing.org.
      ;!REF:anathoth
      @                       IN      SOA                            ( ns1.anathoth.net. ;Master
      NS
                                                                     matthewgrant5.gmail.com.
      ;RP email
                                                                     2012082300       ;Serial
      yyyymmddnn
                                                                     600              ;Refresh
                                                                     600              ;Retry
                                                                     604800           ;Expire
                                                                     600
      ;Minimum/Ncache
                                                                     )
                                      IN        NS                   ns3.anathoth.net.
                                      IN        NS                   ns2.anathoth.net.
                                      IN        NS                   ns1.anathoth.net.

ZIs can also be copied from one zone to another by using the ``copy_zi``
command.  This command will not result in the copied ZI being published unless
the zone is refreshed to use it.

Deleting and Undeleting Zones
=============================

Deleting a Zone
---------------

The command for deleting a zone is ``delete_zone``::

       zone_tool > ls bad-thing.org
       bad-thing.org.
       zone_tool > delete_zone bad-thing.org.
       ***   Zone 'bad-thing.net.' not present.
       zone_tool > delete_zone bad-thing.org.
       zone_tool > ls bad-thing.org.
       ***   Zones: bad-thing.org. - not present.

Undeleting a Zone
-----------------

The ``ls_deleted`` command can be used in conjunction with the
``undelete_zone`` command. The ``undelete_zone`` command only takes a
``zone_id`` argument, as there are likely to be multiple deleted zones with the
same name. The ``show_zone_byid`` command can be used to display the deleted
zone.

::

      zone_tool > ls_deleted bad-thing.*
      bad-thing.org.                    101449                      anathoth
      zone_tool > show_zone_byid 101449
      $TTL 24h
      $ORIGIN bad-thing.org.

      ;
      ;   Zone:          bad-thing.org.
      ;   Reference:     anathoth
      ;   change_by:     grantma@shalom-ext.internal.anathoth.net/Admin
      ;   zi_id:         102602
      ;   zi_ctime:      Thu Aug 23 14:54:07 2012
      ;   zi_mtime:      Wed Aug 29 17:10:15 2012
      ;   zi_ptime:      Wed Aug 29 17:10:15 2012
      ;


      ;| Apex resource records for bad-thing.org.
      ;!REF:anathoth
      @                       IN      SOA                             ( ns1.anathoth.net. ;Master
      NS
                                                                      matthewgrant5.gmail.com.
      ;RP email
                                                                      2012082300        ;Serial
      yyyymmddnn
                                                                      600               ;Refresh
                                                                      600               ;Retry
                                                                      604800            ;Expire
                                                                      600
      ;Minimum/Ncache
                                                                      )
                                      IN         NS                   ns3.anathoth.net.
                                      IN         NS                   ns2.anathoth.net.
                                      IN         NS                   ns1.anathoth.net.


      zone_tool > undelete_zone 101449
      zone_tool > ls bad-thing.*
      bad-thing.org.
      zone_tool >


.. note::
   Deleted zones will have their ZIs pared down to what was the published ZI after 90 days by the
   ``vacuum_all`` command, which is croned to run daily.


.. _editing-a-zone:

Editing a Zone
==============

Use the ``edit_zone <domain-name> [zone-instance]`` command. If you are using
the default ``vim-nox`` editor, it will drop you into a syntax highlighted
editing session.

In ``/usr/share/vim/vimcurrent/debian.vim`` ``vim`` has been set up for::

  set nocompatible " Use Vim defaults instead of 100% vi compatibility
  set backspace=indent,eol,start " more powerful backspacing

Which means Insert mode behaves like a normal editor. Arrow keys do not finish
insert mode session. Backspace and delete delete across line ends with a
logical sense as to directionality when in insert mode etc. (Whew! Standard
``vi`` - !@#$%@$%&$%^*@#$%^ - can't find spanner to resolve insertion into
works trajectory)

At a minimum you still have to know about ``:w`` to save, and ``:q`` to quit
and save.  ``ESC`` is also useful to cancel something if you think you have
pressed something wrong, and to exit insert mode back to visual command mode.
Pressing ``u`` in visual mode will undo the last change, with multiple undo for
recent change history.

  ============================    =======================================================
  Vim keys                        Action
  ============================    =======================================================
 
  ESC                             cancel current thing, exit Insert mode. Dive for this
                                  key if you want to back out of what ever you are not
                                  sure you have just started (in visual mode). Press
                                  multiple times just to reassure yourself operation is
                                  canceled, even though once is all you need to do
                                  95% of the time. This should 'unstick' any vi.
                                  REMEMBER THIS! (vi safety rule number 1!)

  i                               Go to insert mode from visual

  :w                              In visual mode, save file

  :e!                             Revert all changes until last save

  :q                              quit

  :q!                             Forced quit if you have changed something

  :wq                             save file and quit vi

  /<regexp>                       search forwards

  ?<regexp>                       search backwards

  n                               search again in search direction

  N                               search again in reverse search direction

  dd                              delete current line

  gg                              go to start of file

  G                               go to end of file

  d$                              delete from cursor to end of line

  V                               select current line and then use arrows to select block

  v                               Select from cursor posN and then use arrows to select
                                  block

  d                               Delete, then press locational key of where to delete to
                                  (^,$,G,gg)

  ^                               Beginning of line

  $                               End of line

  :s/<regexp>/<replacement>/gc    Search and replace with confirmation. Use with v or V
                                  selection to apply to block. g suffix means replace
                                  multiple times on one line, rather than first occurrence,
                                  c means confirm

  :%                              Apply following command across whole file.
                                  ':%s/<regexp>/<replacement>/' very useful

  p                               Paste last deletion

  y                               Copy 'yy' copy current line, y$ y^ as you would expect.

  2yy                             Copy current line and one following

  2dd                             Well, work this one out...

  2p                              Paste twice (paste one line 2 times etc)
  ============================    =======================================================


::

      zone_tool > edit_zone 192.168.110/24

      $TTL 24h
      $ORIGIN 110.168.192.in-addr.arpa.

      ;
      ;   Zone:        110.168.192.in-addr.arpa.
      ;   Reference:   anathoth
      ;   change_by:   grantma@shalom-ext.internal.anathoth.net/Admin
      ;   zi_id:       102584
      ;   zi_ctime:    Sun Aug 19 20:10:16 2012
      ;   zi_mtime:    Sun Aug 19 20:10:16 2012
      ;   zi_ptime:    Sun Aug 19 20:10:16 2012
      ;


      ;| Apex resource records for 110.168.192.in-addr.arpa.
      ;!REF:anathoth
      @                       IN      SOA             (
      ns1.internal.anathoth.net. ;Master NS
                                                      matthewgrant5.gmail.com.
      ;RP email

                                                 2012081900    ;Serial yyyymmddnn
                                                 600           ;Refresh
                                                 600           ;Retry
                                                 604800        ;Expire
                                                 600           ;Minimum/Ncache
                                                 )
                        IN      NS               ns2.internal.anathoth.net.
                        IN      NS               ns1.internal.anathoth.net.


      ;!LOCKPTR
      1                       IN       PTR      shalom.internal.anathoth.net.
      ;!REF:anathoth
      149                     IN       PTR      something-here.failover.internal.anathoth.net.
      ;!REF:anathoth
      16                      IN       PTR      openwrt.internal.anathoth.net.
      ;!LOCKPTR REF:anathoth
      2                       IN       PTR      shalom-auth.internal.anathoth.net.
      ;!LOCKPTR REF:anathoth
      20                      IN       PTR      phone-800.internal.anathoth.net.
      230                     IN       PTR      ballywack.anathoth.net.
      ;!LOCKPTR REF:anathoth
      254                     IN       PTR      shalom-fw.internal.anathoth.net.
      ;!REF:anathoth
      3                       IN       PTR      sid-dev.internal.anathoth.net.
      ;!REF:anathoth
      4                       IN       PTR      joy.internal.anathoth.net.
      ;!REF:anathoth
      5                       IN       PTR      sid-test.internal.anathoth.net.
      ;!REF:anathoth
      69                      IN       PTR      phone-802.internal.anathoth.net.
      ;!REF:anathoth
      96                      IN       PTR      openwrt.internal.anathoth.net.

      ***   Do you wish to Abort, Change, Diff, or Update the zone
            '110.168.192.in-addr.arpa.'?
      --[U]/a/c/d> d
      @@ -47,7 +47,7 @@
      5                       IN      PTR       sid-test.internal.anathoth.net.
      ;!REF:anathoth
      69                      IN      PTR       phone-802.internal.anathoth.net.
      -;!LOCKPTR REF:anathoth
      +;!REF:anathoth
      96                      IN      PTR       openwrt.internal.anathoth.net.

      --[U]/a/c/d>

      zone_tool >

DMS Zone File Format
--------------------

The DMS zone file format builds on the format described in RFCs 1034 and 1035
by the use of 2 character comment tags. In the example above note the Apex RR
group started by the ``;|`` RR croup comment, with the block finished by a blank
line. Individual RR record comments start with ``;#`` on the line just before the
record. Both types of comment can be multi line. An new RR Group can be
started by giving a comment starting with ``;|``, with the RR Group comment
naming the RR Group. RR Groups tend to be sorted alphabetically, except that
the Apex group containing the SOA and NS records is at the top of the zone
file, with the unlabeled default RR Group last of all. RR flag comments also
exist, mostly to control auto reverse PTR functionality, and to disable any
individual RR.

 =====================================    =====================================
 DMS comment                              Description
 =====================================    =====================================
 ;|                                       RR Group comment
 ;#                                       Individual RR comment
 ;!                                       RR flag comment
 ;!LOCKPTR                                Lock the PTR record preventing
                                          any auto update.
 ;!REF:0000@DNSPROVIDER-NZ                PTR RR reference. Any changes coming
                                          from a zone 'owned' by the given
                                          reference are allowed to change the
                                          record.  The ';!REF' on the SOA
                                          declares the ownership of the zone.
 ;!FORCEREV                               One shot force reverse update of PTR
                                          from A or AAAA record unless it is
                                          locked.
 ;!TRACKREV                               Track reverse update of PTR from A or
                                          AAAA unless it is locked.
 ;!DISABLE                                Disable the RR and remove it from 
                                          published zone.
 ;!RROP: ADD, DELETE, UPDATE_RRTYPE       ``zone_tool update_rrs`` incremental 
                                          update operation. See ``zone_tool``
                                          ``help update_rrs`` for all the details.
                                          'Wildcard' arguments can be given to
                                          DELETE operation.
 =====================================    =====================================

Note that multiple ``;!`` RR flags are all given on one line before the RR.

Auto-reverse PTR record management
----------------------------------

The DMS system can do this, and it checks every A and AAAA record on ZI
submission to do auto reverse if it is configured for the reverse zones the DMS
system holds.

The reference of the source zone has to match the reference of the reverse
zone, or the reference on a PTR record to effect a change, or the source of the
update has to be a user interface with the 'Admin' sectag. Given the former
conditions, if a PTR record does not exist, one is created. An existing PTR
record is only updated if the FORCEREV RR flag is given, and the RR is not
locked by a LOCKPTR RR flag.  BTW, the ``inc_updates`` flag MUST be set on a
reverse zone for auto updating to operate on it.

The update mechanism uses a network database table to choose the most specific
(by CIDR netmask) existing reverse zone to apply the update to. This is also
the smarts behind the CIDR network block/IP address -> reverse zone domain
resolution in ``zone_tool``.

Edit Locking
------------

Zones may have ``edit_lock`` flag set, which means timed edit locking is
enforced on the zone. The lock has an activity time out, and ``edit_zone`` will
give a lock failure with the ``locked_by`` string for the zone if it is locked.
The lock can be cleared with ``cancel_edit_zone`` or ``clear_edit_lock``, which
will ask for the zone name and the lock token that is returned with the lock
failure error message.

::

       shalom-ext: -grantma- [~]
       $ zone_tool edit_zone anathoth.net
       ***   Event ZoneSMEdit(885379) failed - ZoneEditLocked: Zone
             'anathoth.net.' is locked with token '885378', held by 'grantma
             @shalom-ext.internal.anathoth.net/Admin'.

       shalom-ext: -grantma- [~]
       $ zone_tool
       Welcome to the zone_tool program.                Type help or ? to list commands.

       zone_tool > clear_edit_lock anathoth.net 885378
       zone_tool > edit_zone anathoth.net
       ***   File '/tmp/zone_tool-mtjo4s.zone'
           unchanged after editing - exiting.
       zone_tool >

Enabling and Disabling Zones
============================

Disabling a Zone
----------------

This completely removes the zone from the DNS servers, while still holding it
in the database. The ``show_zonesm <domain-name>`` command is used to display
the zone state, though you could also use ``ls -v <domain-name>`` The
``zone_tool`` commands are ``enable_zone`` and ``disable_zone``.

``ls_pending_events`` can be used to display what is waiting in the DMS event
queue. Note the 10 minute delay between updating the named.conf files enforced
by the DMS ConfigSM state machine.

For example have a look at the following screen capture::

       zone_tool > disable_zone bad-thing.org
       zone_tool > show_zonesm bad-thing.org
               name:            bad-thing.org.
               alt_sg_name:     None
               auto_dnssec:     False

        ctime:             Thu Aug 23 14:54:07 2012
        deleted_start:     None
        edit_lock:         True
        edit_lock_token:   None
        inc_updates:       False
        lock_state:        EDIT_UNLOCK
        locked_by:         None
        mtime:             Thu Aug 23 15:07:07 2012
        nsec3:             True
        reference:         anathoth
        soa_serial:        2012082300
        sg_name:           anathoth-external
        state:             DISABLED
        use_apex_ns:       True
        zi_candidate_id:   102602
        zi_id:             102602
        zone_id:           101449
        zone_type:         DynDNSZoneSM

        zi_id:             102602
        change_by:         grantma@shalom-ext.internal.anathoth.net/Admin
        ctime:             Thu Aug 23 14:54:07 2012
        mtime:             Thu Aug 23 14:54:26 2012
        ptime:             Thu Aug 23 14:54:26 2012
        soa_expire:        7d
        soa_minimum:       600
        soa_mname:         ns1.anathoth.net.
        soa_refresh:       600
        soa_retry:         600
        soa_rname:         matthewgrant5.gmail.com.
        soa_serial:        2012082300
        soa_ttl:           None
        zone_id:           101449
        zone_ttl:          24h
        zone_tool >

        shalom-ext: -grantma- [~/dms-2011]
        $ dig -t AXFR bad-thing.org @::1

       ; <<>> DiG 9.8.1-P1 <<>> -t AXFR bad-thing.org @::1
       ;; global options: +cmd
       ; Transfer failed.

Enabling A Zone
---------------

::

  zone_tool > enable_zone bad-thing.org
  zone_tool > show_zonesm bad-thing.org
      name:            bad-thing.org.
      alt_sg_name:     None
      auto_dnssec:     False
      ctime:           Thu Aug 23 14:54:07 2012
      deleted_start:   None
      edit_lock:       True
      edit_lock_token: None
      inc_updates:     False

      lock_state:        EDIT_UNLOCK
      locked_by:         None
      mtime:             Thu Aug 23 15:08:58 2012
      nsec3:             True
      reference:         anathoth
      soa_serial:        2012082300
      sg_name:           anathoth-external
      state:             UNCONFIG
      use_apex_ns:       True
      zi_candidate_id:   102602
      zi_id:             102602
      zone_id:           101449
      zone_type:         DynDNSZoneSM

      zi_id:             102602
      change_by:         grantma@shalom-ext.internal.anathoth.net/Admin
      ctime:             Thu Aug 23 14:54:07 2012
      mtime:             Thu Aug 23 14:54:26 2012
      ptime:             Thu Aug 23 14:54:26 2012
      soa_expire:        7d
      soa_minimum:       600
      soa_mname:         ns1.anathoth.net.
      soa_refresh:       600
      soa_retry:         600
      soa_rname:         matthewgrant5.gmail.com.
      soa_serial:        2012082300
      soa_ttl:           None
      zone_id:           101449
      zone_ttl:          24h
  .
  .
  .

  zone_tool > ls_pending_events
  ConfigSMHoldTimeout                                    Thu Aug 23 15:17:09 2012
  ZoneSMReconfigUpdate     bad-thing.org.                Thu Aug 23 15:17:27 2012
  zone_tool > ls -v bad-thing.org
  bad-thing.org.                   2012082300   UNCONFIG       anathoth
  zone_tool >
  .
  .
  .
  shalom-ext: -grantma- [~/dms-2011]
  $ dig -t AXFR bad-thing.org @::1

  ; <<>> DiG 9.8.1-P1 <<>> -t AXFR bad-thing.org @::1
  ;; global options: +cmd
  bad-thing.org. 86400 IN SOA ns1.anathoth.net. matthewgrant5.gmail.com. 2012082300 600 600 604800 600
  bad-thing.org. 86400 IN NS ns1.anathoth.net.
  bad-thing.org. 86400 IN NS ns2.anathoth.net.
  bad-thing.org. 86400 IN NS ns3.anathoth.net.
  bad-thing.org. 86400 IN SOA ns1.anathoth.net. matthewgrant5.gmail.com. 2012082300 600 600 604800 600
  ;; Query time: 0 msec
  ;; SERVER: ::1#53(::1)
  ;; WHEN: Thu Aug 23 15:18:56 2012
  ;; XFR size: 5 records (messages 1, bytes 192)
  
  zone_tool > ls -v bad-thing.org
  bad-thing.org.                               2012082300        PUBLISHED           anathoth
  zone_tool >

Refreshing and Resetting a Zone
===============================

Refreshing a Zone
-----------------

This causes a refresh of the zone against the master DMS server. If there are
any differences, they are resolved.

::

      zone_tool > refresh_zone bad-thing.org
      zone_tool > ls_zi bad-thing.org
              *102602                2012082300   Thu Aug 23 14:54:07 2012
      zone_tool > show_zonesm bad-thing.org
              name:            bad-thing.org.
              alt_sg_name:     None
              auto_dnssec:     False
              ctime:           Thu Aug 23 14:54:07 2012
              deleted_start:   None
              edit_lock:       True
              edit_lock_token: None
              inc_updates:     False
              lock_state:      EDIT_UNLOCK
              locked_by:       None
              mtime:           Thu Aug 30 09:11:45 2012
              nsec3:           True
              reference:       anathoth
              soa_serial:      2012082300
              sg_name:         anathoth-external
              state:           PUBLISHED
              use_apex_ns:     True
              zi_candidate_id: 102602
              zi_id:           102602
              zone_id:         101449
              zone_type:       DynDNSZoneSM

              zi_id:                   102602
              change_by:               grantma@shalom-ext.internal.anathoth.net/Admin
              ctime:                   Thu Aug 23 14:54:07 2012
              mtime:                   Thu Aug 30 09:25:44 2012
              ptime:                   Thu Aug 30 09:25:44 2012
              soa_expire:              7d
              soa_minimum:             600
              soa_mname:               ns1.anathoth.net.
              soa_refresh:             600
              soa_retry:               600
              soa_rname:               matthewgrant5.gmail.com.
              soa_serial:              2012082300
              soa_ttl:                 None
              zone_id:                 101449
              zone_ttl:                24h
      zone_tool >

Resetting a Zone
----------------

This withdraws the zone completely from the DNS servers, and reconfigures it
through out the DNS servers. During the 15 minutes that this takes, the zone
will NOT be served. The main use of this instruction is if a zone's state
machine is 'stuck' and not PUBLISHED. A yes/no confirmation is asked before
doing it. BE CAREFUL!

::

      zone_tool > reset_zonesm bad-thing.org
      ***   WARNING - doing this destroys DNSSEC RRSIG data.
      ***   Do really you wish to do this?
       --y/[N]> y
      zone_tool > show_zonesm bad-thing.org
              name:            bad-thing.org.
              alt_sg_name:     None
              auto_dnssec:     False
              ctime:           Thu Aug 23 14:54:07 2012
              deleted_start:   None
              edit_lock:       True
              edit_lock_token: None
              inc_updates:     False
              lock_state:      EDIT_UNLOCK
              locked_by:       None
              mtime:           Thu Aug 30 09:11:45 2012
              nsec3:           True
              reference:       anathoth
              soa_serial:      2012082300
              sg_name:         anathoth-external
              state:           RESET
              use_apex_ns:     True
              zi_candidate_id: 102602
              zi_id:           102602
              zone_id:         101449
              zone_type:       DynDNSZoneSM

              zi_id:                   102602
              change_by:               grantma@shalom-ext.internal.anathoth.net/Admin
              ctime:                   Thu Aug 23 14:54:07 2012
              mtime:                   Thu Aug 30 09:25:44 2012
              ptime:                   Thu Aug 30 09:25:44 2012
              soa_expire:              7d
              soa_minimum:             600
              soa_mname:               ns1.anathoth.net.
              soa_refresh:             600
              soa_retry:               600
              soa_rname:               matthewgrant5.gmail.com.
              soa_serial:              2012082300
              soa_ttl:                 None
              zone_id:                 101449
              zone_ttl:                24h
      zone_tool >

The DMS zone_tool Session
=========================

For help desk, ``ssh`` to dms-server.someorg.org with your DMS system login
name. For help desk accounts, you will be dropped into a restricted
``zone_tool`` shell, which should have all the commands you need to do day to
day zone management.

The default editor in the shell is ``vim`` with zone file syntax highlighting.
Invalid syntax will usually be will be highlighted in red as soon as you type
it. ``Vim`` is set up to allow normal cursor navigation with arrow keys in a
friendly 'Insert' mode, and other niceties, as detailed in :ref:`editing-a-zone`.
``Nano`` is also available, but it won't be so helpful when editing.

To exit the shell, use Ctrl-D, exit or quit as you would with a normal \*nix
terminal session.

.. note::

   Operations that cause an amount of down time, or may result in irreversible or really large
   changes in zone_tool have a confirmation question before proceeding. Be careful.


Viewing Zones (and a lot more about them)
=========================================

.. toctree::

Listing Zones
-------------

You can use the ``ls`` command for this. It can take multiple wild cards, ``?`` and ``*``. Other things that are useful are the
customer reference. These take the form ``account_id@DNSPROVIDER-NZ`` and ``account_id@SOMEORG-NZ``

Examples:

Plain ``ls`` - Returns everything::

       zone_tool > ls
       110.168.192.in-addr.arpa.
       2.1.0.f.0.7.4.0.1.0.0.2.ip6.arpa.
       31.172.in-addr.arpa.
       9.6.a.b.8.2.8.0.4.1.d.f.ip6.arpa.
       anathoth.net.
       anathoth.org.
       blam.com.
       blamo.net.
       failover.internal.anathoth.net.
       internal.anathoth.net.
       loo.org.
       test1.com.
       test2.com.
       wilma.org.

Wildcard ``ls``::


       zone_tool > ls anathoth*
       anathoth.net.
       anathoth.org.


``ls`` with reference using ``-r`` switch::


       zone_tool > ls -r 0000@DNSPROVIDER-NZ
       110.168.192.in-addr.arpa.
       2.1.0.f.0.7.4.0.1.0.0.2.ip6.arpa.
       31.172.in-addr.arpa.
       9.6.a.b.8.2.8.0.4.1.d.f.ip6.arpa.
       blam.com.
       blamo.net.
       failover.internal.anathoth.net.
       internal.anathoth.net.
       loo.org.
       test1.com.
       test2.com.
       wilma.org.

Verbose ``ls`` with reference::

       zone_tool > ls -v -r 0000@DNSPROVIDER-NZ
       110.168.192.in-addr.arpa.        2012081900                 PUBLISHED           anathoth
       2.1.0.f.0.7.4.0.1.0.0.2.ip6.arpa. 2012052300                 PUBLISHED           anathoth
       31.172.in-addr.arpa.             2012071301                 PUBLISHED           anathoth
       9.6.a.b.8.2.8.0.4.1.d.f.ip6.arpa. 2012081900                 PUBLISHED           anathoth
       blam.com.                        2012081600                 PUBLISHED           anathoth
       blamo.net.                       2012080902                 PUBLISHED           anathoth
       failover.internal.anathoth.net. 2012081601                  PUBLISHED           anathoth
       internal.anathoth.net.           2012081900                 PUBLISHED           anathoth
       loo.org.                         2012081602                 PUBLISHED           anathoth
       test1.com.                       2012081601                 PUBLISHED           anathoth
       test2.com.                       2012081602                 PUBLISHED           anathoth
       wilma.org.                       2012081602                 PUBLISHED           anathoth
       zone_tool >

Listing Deleted Zones
---------------------

Use the ``ls_deleted command``. It can use wild cards and reference as per the
``ls`` command. The second column displayed is the ``zone_id``, which you use
to undelete a zone. Raison d'etre: With DNS Provider, knowing how people use
computers when they 'know'/think something goes a bit loopy, they will spring
for deleting a zone, and recreating it, most likely multiple times. Thus there
are likely to be multiple deleted zones for the same domain name, hence the use
of ``zone_id`` for undelete.

::

       zone_tool > help ls_deleted

                  List deleted zones/domains (+ wildcards):

                  ls_deleted [-v] [-r reference] [-g sg_name] [domain-name]
                                  [domain-name] ...

                  where:     domain-name           domain name with * or ? wildcards as needed
                             reference             reference
                             sg_name               server group name
                             -v                    verbose output

       zone_tool > ls_deleted
       blamo.wham.                                   101374            anathoth
       blamo.wham.                                   101375            anathoth
       toady.anathoth.net.                           101407            anathoth
       zone_tool >




Showing a Zone
--------------

Use the ``show_zone`` command. By default just displays the published Zone
Instance (ZI)::

       zone_tool > show_zone anathoth.net
       $TTL 24h
       $ORIGIN anathoth.net.

       ;
       ;   Zone:          anathoth.net.
       ;   change_by:     hd-test@shalom-ext.internal.anathoth.net/Admin
       ;   zi_id:         102592
       ;   zi_ctime:      Mon Aug 20 11:07:49 2012
       ;   zi_mtime:      Mon Aug 20 11:12:07 2012
       ;   zi_ptime:      Mon Aug 20 11:12:07 2012
       ;


       ;|
       ;| Apex resource records for anathoth.net.
       ;|
       @                       IN      SOA            ( ns1                        ;Master NS
                                                        matthewgrant5.gmail.com.   ;RP email
                                                        2012082000                 ;Serial  yyyymmddnn
                                                        600                        ;Refresh
                                                        600          ;Retry
                                                        604800       ;Expire
                                                        600          ;Minimum/Ncache
                                                        )
                                 IN     NS              ns3
                                 IN     NS              ns2
                                 IN     NS              ns1


        ;| Hosts
        shalom-dr               IN      AAAA            2001:470:f012:2::3
                                IN      SSHFP           1 1 07bfdd14b4be97dbe282573eecd5bc6b062a92b1
        shalom-ext              IN      AAAA            2001:470:f012:2::2
                                IN      SSHFP           1 1 073b3198599c59a3c2a9db8c209a2097ea46aa09
        shalom-fw               IN      AAAA            2001:470:c:2e6::2
        shalom-svc              IN      AAAA            2001:470:f012:2::1


        ;| Internal zone lacing
        internal                IN      DS              18174 7 2 c42492db9def5ca9403d26f175247dfe86d913da4bedfc7d629f5e57d6669feb
                                IN      NS              ns1.internal
                                IN      NS              ns2.internal
        ns1.internal            IN      AAAA            fd14:828:ba69:1:21c:f0ff:fefa:f3c0
        ns2.internal            IN      AAAA            fd14:828:ba69:2::2


        ;| Name server records
        ns1                      IN     A               203.79.116.183
                                 IN     AAAA            2001:470:f012:2::2
        ns2                      IN     A               111.65.238.10
                                 IN     AAAA            2001:470:c:110e::2
        ns3                      IN     A               111.65.238.11
                                 IN     AAAA            2001:470:66:23::2


        ;| Web site Urls
        @                        IN     A               203.79.116.183
                                 IN     AAAA            2001:470:f012:2::2
                                 IN     TXT             "Some hash"
        www                      IN     CNAME           @

        zone_tool >

Use ``ls_zi <domain-name>`` to display all the ZIs in the DB for a zone::


       ls_zi anathoth.net
                102012                         2012042702         Mon   Feb   27   10:06:28   2012
                102100                         2012050800         Tue   May    8   14:19:17   2012
                102104                         2012050801         Tue   May    8   14:22:25   2012
                102106                         2012050802         Tue   May    8   14:29:02   2012
                102108                         2012050803         Tue   May    8   14:34:17   2012
                102133                         2012050900         Wed   May    9   09:23:04   2012
                102136                         2012050901         Wed   May    9   09:24:14   2012
                102152                         2012050902         Wed   May    9   12:55:11   2012
                102155                         2012050903         Wed   May    9   12:56:27   2012
                102156                         2012050904         Wed   May    9   12:56:46   2012
                102159                         2012051000         Thu   May   10   10:07:52   2012
                102162                         2012051012         Thu   May   10   10:09:04   2012
                102164                         2012051013         Thu   May   10   13:31:06   2012
                102167                         2012051013         Thu   May   10   16:13:56   2012
                102171                         2012051014         Thu   May   10   16:45:33   2012
                102187                         2012052100         Mon   May   21   11:43:57   2012
                102189                         2012052300         Wed   May   23   11:47:01   2012
                102199                         2012052400         Thu   May   24   15:23:05   2012
                102201                         2012052401         Thu   May   24   15:24:18   2012
                102261                         2012072500         Tue   Jul    3   12:05:29   2012
                102468                         2012072600         Thu   Jul   26   12:13:53   2012
                102585                         2012082000         Mon   Aug   20   10:26:27   2012
                102588                         2012082000         Mon   Aug   20   10:27:36   2012
                102589                         2012082000         Mon   Aug   20   10:41:26   2012
               *102592                         2012082000         Mon   Aug   20   11:07:49   2012

The published ZI is asterisked.

``Show_zone`` can also take a ZI as the second argument::

        zone_tool > show_zone anathoth.net 102585
        $TTL 24h
        $ORIGIN anathoth.net.

        ;
        ;   Zone:          anathoth.net.
        ;   change_by:     grantma@shalom-ext.internal.anathoth.net/Admin
        ;   zi_id:         102585
        ;   zi_ctime:      Mon Aug 20 10:26:27 2012
        ;   zi_mtime:      Mon Aug 20 10:26:28 2012
        ;   zi_ptime:      Mon Aug 20 10:26:28 2012
        ;


        ;|
        ;| Apex resource records for anathoth.net.
        ;|
        @                       IN      SOA                                ( ns1          ;Master NS
                                                                           matthewgrant5.gmail.com.
        ;RP email
                                                                           2012082000        ;Serial
        yyyymmddnn
                                                                           600               ;Refresh
                                                                           600               ;Retry
                                                                           604800            ;Expire
                                                                           600
        ;Minimum/Ncache
                                                                           )
                                         IN         NS                     ns3
                                         IN         NS                     ns2
                                         IN         NS                     ns1
        .
        .
        .

Power Tricks
------------

zi-id
^^^^^

Anywhere a ZI id can be entered, you can use the ``^---`` and ``^++` notation.
``^`` is the published ZI, ``^-`` the ZI previous to the published ZI, ``^+2``
the ZI 2 ahead of the current published ZI, ``@2d`` the ZI that was published 2
days ago, ``1/4`` the ZI that was published on the 1st of April, 2/3/1010 the
ZI published as of the 2nd March 1010. The ``zi_id`` is also used with the
``diff_zone`` and ``diff_zones`` commands.

domain-name
^^^^^^^^^^^

In the case of reverse zones, the domain name can be the exact network block in
CIDR notation when creating a zone, deleting a zone, enabling/disabling/setting
a zone. An IP number can be given with ``show_zone``, ``edit_zone``, and
``lszi``, and the corresponding closest reverse zone will be shown/edited. This
is for ease of use when working with IP addresses and network diagnosis. The IP
number can be pasted into the terminal.

Differencing ZIs and Zones
--------------------------

Differences between the ZIs in a zone can be taken by using the
``diff_zone_zi`` command. The first ``zi_id`` parameter is the former ZI, and
the 2nd the latter ZI. By default the 2nd ZI is the currently published ZI.

All ``diff`` output is in unified format, and if the system is set up properly,
difference lines are colorized in the ``zone_tool`` pager.

Dates can also take a 4 digit year, ISO date format, with hh:mm after a comma.
(ie 3/5/2012,13:45) If a time is not given with a date, it is taken as being at
midnight on the date, the start of the day, 00:00. This is in line with the
international date time standards used for time zones.

Times in hh:mm can also be used as a ``zi_id``.

.. note::

            Zone SOA serial numbers for a ZI 'float'. They are updated if a ZI
            for a zone is republished, of if an update is made to the zone apex
            records, of if the ZI for the zone is refreshed resulting in it
            publication. The SOA serial for a ZI is worked out via an RFC
            compliant 'bargaining' process with named when named is updated
            with the ZI via dynamic differencing from dmsdmd. A current serial
            number of 'YYYYMMDDnn' format is the first 'offer' if the named
            zone SOA serial is before the current day.

            The best thing when looking for a SOA serial number for a zone is
            to give it as a ``zi_id`` date.

Differencing between ZI at 1/5 (1st May) of current year and published for zone ``anathoth.net.``::

      zone_tool > diff_zone_zi anathoth.net 1/5
      @@ -6,7 +6,7 @@
       ;|
       @                       IN      SOA                               ( ns1          ;Master NS
                                                                         matthewgrant5.gmail.com.      ;RP email
      -                                                                  2012042702       ;Serial      yyyymmddnn
      +                                                                  2012082000       ;Serial      yyyymmddnn
                                                                         600              ;Refresh
                                                                         600              ;Retry
                                                                         604800           ;Expire
      @@ -18,7 +18,10 @@


        ;| Hosts
      +shalom-dr               IN      AAAA                              2001:470:f012:2::3
      +                        IN      SSHFP                             1 1 07bfdd14b4be97dbe282573eecd5bc6b062a92b1
        shalom-ext             IN      AAAA                              2001:470:f012:2::2
      +                        IN      SSHFP                             1 1 073b3198599c59a3c2a9db8c209a2097ea46aa09
        shalom-fw              IN      AAAA                              2001:470:c:2e6::2
        shalom-svc             IN      AAAA                              2001:470:f012:2::1

      @@ -43,6 +46,7 @@
       ;| Web site Urls
       @                                IN         A                     203.79.116.183
                                        IN         AAAA                  2001:470:f012:2::2
      +                                 IN         TXT                   "Some hash"
        www                             IN         CNAME                 @

      zone_tool >

Differencing between ZI 65 days ago and published for zone ``anathoth.net.``
Note that the 2 days ago, no difference, produces no output. Other time
specifiers are ``s`` for seconds, ``m`` for minutes, ``h`` for hours. Months is
not available as Python standard lib datetime.timedelta class does not support
it (months varying in length?).

::

      zone_tool > diff_zone_zi anathoth.net @2d ^
      zone_tool > diff_zone_zi anathoth.net @25d ^
      @@ -6,7 +6,7 @@
       ;|
       @                       IN      SOA                              ( ns1          ;Master NS
                                                                        matthewgrant5.gmail.com. ;RP email
      -                                                                 2012072600       ;Serial yyyymmddnn
      +                                                                 2012082000       ;Serial yyyymmddnn
                                                                        600              ;Refresh
                                                                        600              ;Retry
                                                                        604800           ;Expire
      zone_tool >

Differencing between ``anathoth.net`` on 2/4/2012,14:04 and the ZI 4 previous to the current published one (could also
be given as ``^----``)::

      diff_zone_zi anathoth.net 3/4/2012,14:04 ^-4
      @@ -6,7 +6,7 @@
       ;|
       @                       IN      SOA                              ( ns1          ;Master NS
                                                                        matthewgrant5.gmail.com.      ;RP email
      -                                                                 2012042702        ;Serial yyyymmddnn
      +                                                                 2012072600        ;Serial yyyymmddnn
                                                                        600               ;Refresh
                                                                        600               ;Retry
                                                                        604800            ;Expire
      @@ -18,7 +18,10 @@


        ;| Hosts
      +shalom-dr               IN      AAAA                             2001:470:f012:2::3
      +                        IN      SSHFP                            1 1 07bfdd14b4be97dbe282573eecd5bc6b062a92b1
        shalom-ext             IN      AAAA                             2001:470:f012:2::2
      +                        IN      SSHFP                            1 1 073b3198599c59a3c2a9db8c209a2097ea46aa09
        shalom-fw              IN      AAAA                             2001:470:c:2e6::2
        shalom-svc             IN      AAAA                             2001:470:f012:2::1

      @@ -43,6 +46,7 @@
       ;| Web site Urls
       @                                IN         A                    203.79.116.183
                                        IN         AAAA                 2001:470:f012:2::2
      +                                 IN         TXT                  "Some hash"
        www                             IN         CNAME                @


      zone_tool >


.. note::
           
        The ``zi_id`` date format arguments can be used with ``show_zone`` and
        ``edit_zone`` instead of a straight ``zi_id``. So you can workflow
        using command line history. ``edit_zone`` will take the specified ZI ID
        as the source to change, and make it the published ZI on completion
        (you can also abort, and also diff your edit before updating).


Differencing Zones
------------------

The ``diff_zones`` command can be used to show the difference between 2 zones.
This is useful if the latter zone was created from the other . The ``zi_id``
arguments are given in the order of the zone names.

To show it works::

      zone_tool > diff_zones anathoth.net anathoth.net ^-- ^
      @@ -3,11 +3,11 @@

       ;
       ;   Zone:        anathoth.net.
      -;   change_by:   grantma@shalom-ext.internal.anathoth.net/Admin
      -;   zi_id:       102588
      -;   zi_ctime:    Mon Aug 20 10:27:36 2012
      -;   zi_mtime:    Mon Aug 20 10:27:38 2012
      -;   zi_ptime:    Mon Aug 20 10:27:38 2012
      +;   change_by:   hd-test@shalom-ext.internal.anathoth.net/Admin
      +;   zi_id:       102592
      +;   zi_ctime:    Mon Aug 20 11:07:49 2012
      +;   zi_mtime:    Mon Aug 20 11:12:07 2012
      +;   zi_ptime:    Mon Aug 20 11:12:07 2012
       ;

And of course::

      zone_tool > ls_zi anathoth.net
               102012                2012042702   Mon Feb 27 10:06:28    2012
               102100                2012050800   Tue May 8 14:19:17     2012
               102104                2012050801   Tue May 8 14:22:25     2012
               102106                2012050802   Tue May 8 14:29:02     2012
               102108                2012050803   Tue May 8 14:34:17     2012
               102133                2012050900   Wed May 9 09:23:04     2012
               102136                2012050901   Wed May 9 09:24:14     2012
               102152                2012050902   Wed May 9 12:55:11     2012
               102155                2012050903   Wed May 9 12:56:27     2012
               102156                2012050904   Wed May 9 12:56:46     2012
               102159                2012051000   Thu May 10 10:07:52    2012
               102162                2012051012   Thu May 10 10:09:04    2012
               102164                2012051013   Thu May 10 13:31:06    2012
               102167                2012051013   Thu May 10 16:13:56    2012
               102171                2012051014   Thu May 10 16:45:33    2012
               102187                2012052100   Mon May 21 11:43:57    2012
               102189                2012052300   Wed May 23 11:47:01    2012
               102199                2012052400   Thu May 24 15:23:05    2012
               102201                2012052401   Thu May 24 15:24:18    2012
               102261                2012072500   Tue Jul 3 12:05:29     2012
               102468                2012072600   Thu Jul 26 12:13:53    2012
               102585                2012082000   Mon Aug 20 10:26:27    2012
               102588                2012082000   Mon Aug 20 10:27:36    2012
               102589                2012082000   Mon Aug 20 10:41:26    2012
              *102592                2012082000   Mon Aug 20 11:07:49    2012
      zone_tool > copy_zone -z 102592 anathoth.net wham-blam.org
      zone_tool > edit_zone wham-blam.org
      ***   Do you wish to Abort, Change, Diff, or Update the zone
      'wham-blam.org.'?
      --[U]/a/c/d>
      zone_tool > diff_zones anathoth.net wham-blam.org ^-- ^
      @@ -1,33 +1,35 @@
       $TTL 24h
      -$ORIGIN anathoth.net.
      +$ORIGIN wham-blam.org.

       ;
      -;   Zone:        anathoth.net.
      +;   Zone:        wham-blam.org.
      +;   Reference:   anathoth
       ;   change_by:   grantma@shalom-ext.internal.anathoth.net/Admin
      -;   zi_id:       102588
      -;   zi_ctime:    Mon Aug 20 10:27:36 2012
      -;   zi_mtime:    Mon Aug 20 10:27:38 2012
      -;   zi_ptime:    Mon Aug 20 10:27:38 2012
      +;   zi_id:       102598
      +;   zi_ctime:    Thu Aug 23 10:52:16 2012
      +;   zi_mtime:    Thu Aug 23 10:52:18 2012
      +;   zi_ptime:    Thu Aug 23 10:52:18 2012
       ;


      -;|
      -;| Apex resource records for anathoth.net.
      -;|
      -@                       IN      SOA                ( ns1            ;Master NS
      +;| Apex resource records for wham-blam.org.
      +;!REF:anathoth
      +@                       IN      SOA                ( ns1.anathoth.net.      ;Master NS
                                                          matthewgrant5.gmail.com. ;RP email
      +                                                   2012082000     ;Serial  yyyymmddnn
      -                                                   2012082301     ;Serial  yyyymmddnn
                                                          600            ;Refresh
                                                          600            ;Retry
                                                          604800         ;Expire
                                                          600
      ;Minimum/Ncache
                                                          )
      1.                           IN      NS              ns3
      2.                           IN      NS              ns2
      3.                           IN      NS              ns1
      4.                           IN      NS              ns3.anathoth.net.
      5.                           IN      NS              ns2.anathoth.net.
      6.                           IN      NS              ns1.anathoth.net.


        ;| Hosts

      +bingo                   IN      AAAA      ::1
      -                        IN      TXT       "Samson was here"
        shalom-dr              IN      AAAA      2001:470:f012:2::3
                               IN      SSHFP     1 1
      07bfdd14b4be97dbe282573eecd5bc6b062a92b1
       shalom-ext              IN      AAAA      2001:470:f012:2::2

       zone_tool >


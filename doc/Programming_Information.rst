
.. default-domain:: py

.. _Programming-Information:

***********************
Programming Information
***********************

.. note::

   This document will be updated as the DMS protocol is implemented.

Dmsdmd Communications Protocol
==============================

The Python plug in protocol is WSGI, very similar to Fast CGI, and the wire
communications is JSON RPC over http/https

The server to be tightly coded to a standard so it behaves reasonably. Clients
won't have to be so fussy, but should not request anything they are not coded
to deal with! Comprehensive error processing by the client is encouraged.

The protocol will be JSON-RPC over HTTP 1.1+. This will enable the processing
of multiple requests over the same TCP connection. TCP connections to the
server will be cacheable, and can be held open up to a limit set on the server.
Multiple POSTs over the connection are allowed, and multiple RPC requests can
be submitted within a POST request, with the id: set to a UUID string generated
as per RFC 4122.

`JSON/RPC 2.0 specification
<http://www.simple-is-better.org/json-rpc/jsonrpc20.html>`_ will be used.
`JSON <http://www.json.org>`_ `RFC 4627 <http://www.ietf.org/rfc/rfc4627>`_ will
be used as the data format.

`JSON-RPC over HTTP
<http://www.simple-is-better.org/json-rpc/jsonrpc20-over-http.html>`_ will be
used to access the server, with the limitation being that HTTP POST shall be
used, not GET with its encoded URL.... (blech!). Batch mode requests will also
be implemented.

Authentication will be via HTTP Basic authentication, with the deployed
implementation using HTTPS for integrity.  Privileged access stratification
will be achieved by accessing different Python WSGI scripts at different URLs.
Initially 2 different levels of access will be provided:

#. Customer for Reseller and ISP customer front ends,
#. HelpDesk for normal administrative work on the DNS.

Comprehensive administrative functionality will be available via the zone-tool
command line UI on the Master DNS server.

Error Information
-----------------

Errors shall be python exceptions translated to JSON-RPC errors. The 'data'
section will contain relevant exception attributes, along with an error
message. There will different classes of error, dependent on the operation
being performed.

Errors to do with Zone Instance submission will return RR Group and RRS index
information into the ZI structure sent in the request.

Please not that zones outside the client role are treated as if they do not
exist unless otherwise noted.

Please see :ref:`DMS-Errors` for a full listing.

.. _Editing-Cycle:

Editing Cycle
-------------

Please note that an edit cycle starts with the ``edit_zone`` call below, and is finished with an ``update_zone`` call. When
edit locking is enabled for the zone (typically only hel pdesk, admin, and special customers) the ``tickle_editlock`` (keep
a locked editing session live, called on receiving any data from web browser) and 'cancel_edit_zone' (to cancel edit
session) calls should be used.

.. _Incremental-Updates:

Incremental Updates
-------------------

The ``update_rrs`` call is to be used for incremental updates. The ``update_type`` is a unique ID identifying the operation
type, of which only one per zone can be queued at a time. Each update call eventually generates a new ZI
incorporating the changes after the call returns. When the call is made, a forward-looking check is made with the
current (or candidate) ZI to make sure the changes to be made are consistent.

This mechanism is only for the simple consistent changes required for adding/removing a Web site to a domain,
adding/removing mail MX records for adding Web hosting or Mail to a domain.

.. note::
   
   The error checking is forward looking and would probably fail to produce a
   published zone for complex change sets. It is NOT for making general editing
   changes such as these to the zone. Use the i:ref:`Editing-Cycle` above for user UI
   editing sessions, not this.

.. _JSON-RPC-Calls:



JSON RPC Calls
==============

Errors are exceptions in dms.exceptions, as listed :ref:`below <DMS-Errors>`

.. _rpccall_list_zone:

list_zone()
-----------

**list_zone(names, [reference], [include_deleted], [toggle_deleted], [include_disabled])**

.. program:: list_zone

.. option:: names
  
   array of wildcard-names

.. option:: reference
  
   customer ID or other ID meta data
 
.. option:: include_deleted

   boolean true/false whether to include deleted domains in listing

.. option:: toggle_deleted

   boolean true/false list only deleted domains

.. option:: include_disabled

   boolean true/false include disabled domains, defaults to true

To list domains. Many wild carded domains can be specified. Response will
either be the list of domain names, or an empty list as domains cannot be
found. Customer facing DMIs will be set up so that a :exc:`~dms.exceptions.ZoneSearchPatternError`
exception will be thrown if list_zone is called with no names, or names set to
``*``, without reference being given.

.._rpccall_list_zi:

list_zi()

**list_zi(name)**

.. program:: list_zi

.. option::  name
  
   domain to list

List all zis for a domain. Returns just the base zone_sm object, and the list
of zis ``all_zis``. The published zi is the ``zi`` in the ``zone_sm`` object, and its
full structure is returned, Each zi is accompanied by its ctime and mtime. The
output is shown below in :ref:`rpccall_show_zone`.

.. _rpccall_show_zone:

show_zone()
-----------

**show_zone(name, [zi_id])**

.. _rpccall_show_zone_text:

show_zone_text()
----------------

**show_zone_text(name, [zi_id], [all_rrs])**

.. program:: show_zone

.. option:: name 
   
   domain to show.

.. option:: zi_id 
   
   optional zone instance

.. option:: all_rrs 
   
   optional NOT showing of Apex RRs. Only for show_zone_text

Like the previous operation, except that the full zi returned can be given.

:ref:`rpccall_show_zone_text` returns a zone file text blob, JSON encoded. Note that this means new line, tab, etc are encoded
as '\n', '\t' not as a control characters.

Sample JSON dump of output of show_zone. Note that "sectags" sub-array only shows up in Admin DMS client
RPC interface::

       {    'all_zis': [          {
                               'ctime': 'Mon Mar 5 14:11:25 2012',
                               'mtime': 'Mon Mar 5 14:46:21 2012',
                               'ptime': 'Mon Mar 5 14:46:21 2012',
                               'zi_id': 45,
                               'zone_id': 32}],
           'alt_sg_name': null,
           'auto_dnssec': false,
           'ctime': 'Mon Mar 5 14:11:25 2012',
           'deleted_start': null,
           'edit_lock': false,
           'edit_lock_token': null,
           'inc_updates': false,
           'lock_state': 'EDIT_UNLOCK',
           'mtime': 'Mon Mar 5 14:11:25 2012',
           'name': 'anathoth.net.',
           'nsec3': false,
           'reference': 'net24',
           'sectags': [{'sectag_label': 'Admin'}],
           'soa_serial': 2012030500,
           'sg_name': 'net24-one',
           'state': 'PUBLISHED',
           'use_apex_ns': true,
           'zi': {   'ctime': 'Mon Mar 5 14:11:25 2012',
                     'mtime': 'Mon Mar 5 14:46:21 2012',
                     'ptime': 'Mon Mar 5 14:46:21 2012',
                     'rr_groups': [    {    'comment': 'Apex resource records for anathoth.net.',
                                            'rrs': [   {   'class': 'IN',
                                                           'disable': false,
                                                           'label': '@',
                                                           'lock_ptr': false,
                                                           'rdata': 'ns2.anathoth.net.',
                                                           'reference': null,

                                                  'rr_id': 5126,
                                                  'ttl': null,
                                                  'type': 'NS',
                                                  'zi_id': 45},
                                              {   'class': 'IN',
                                                  'disable': false,
                                                  'label': '@',
                                                  'lock_ptr': false,
                                                  'rdata': 'ns1i.anathoth.net.',
                                                   'reference': null,
                                                   'rr_id': 5125,
                                                   'ttl': null,
                                                   'type': 'NS',
                                                   'zi_id': 45},
                                               {   'class': 'IN',
                                                   'disable': false,
                                                   'label': '@',
                                                   'lock_ptr': false,
                                                   'rdata': 'ns1.anathoth.net. soa.net24.net.nz. 2012030500 7200 7200 604800 86400',
                                                   'reference': null,
                                                   'rr_id': 5124,
                                                   'ttl': null,
                                                   'type': 'SOA',
                                                   'zi_id': 45}],
                                    'tag': 'APEX_RRS'}],
              'soa_expire': '7d',
              'soa_minimum': '24h',
              'soa_mname': 'ns1.net24.net.nz.',
              'soa_refresh': '7200',
              'soa_retry': '7200',
              'soa_rname': 'soa.net24.net.nz.',
              'soa_serial': 2012030500,
              'soa_ttl': null,
              'zi_id': 45,
              'zone_id': 32,
              'zone_ttl': '24h'},
          'zi_candidate_id': 45,
          'zi_id': 45,
          'zone_id': 32,
          'zone_type': 'DynDNSZoneSM'}

.. _rpccall_create_zone:

create_zone()
-------------

**create_zone(<name> <reference> <login_id> [zi_data] [sectags] [sg_name] [edit_lock] [auto_dnssec] [nesc3] [inc_updates] )**

.. _rpccall_create_zone_unprivileged:

create_zone()[unpriveleged]
---------------------------

**create_zone(<name> <reference> <login_id>)**

.. _rpccall_copy_zone:

copy_zone()
-----------

**copy_zone(<src_name> <name> <reference> <login_id> [zi_id] [sectags] [sg_name] [edit_lock] [auto_dnssec] [nesc3] [inc_updates]**

.. program:: create_zone

.. option:: src_name
  
   source domain to be copied

.. option:: zi_id
  
   source ZI to be copied

.. option:: name 
 
   domain to be created

.. option:: reference

   reference for domain being created - can be missed, but domain will be owned by default_ref, ie RESELLER-NZ

.. option:: login_id

   DMI login ID. Email address, or numerical login_id

.. option:: zi_data
   
   optional zi_data (for feeding in a template)

.. option:: sg_name
   
   optional sg where zone is to be created Admin DMS only.

.. option:: sectags

   optional list of security tags for new zone. Admin DMS only. Same array/object format as listing above.

.. option::  edit_lock 
  
   optional boolean for turning on edit_lock mode, default false

.. option:: auto_dnssec

   optional boolean for turning on automatic DNSSEC, default false

.. option:: nsec3

   optional boolean for enabling NSEC3 under DNSSEC, default false

.. option:: inc_updates

   optional boolean for enabling incremental updates for zone, default true for basic interface, false for
   help desk and admin interfaces.

.. describe:: Return
  
   Returns true

Errors are returned if a zone already exists. Optional ``zi_data`` in the format above can be feed in for a template.
Please note that Apex SOA and NS records will not be taken. Basic call used by default for reseller websites and ISP DNS front ends

.. _rpccall_enable_zone:

enable_zone()
-------------

**enable_zone(<name>)**

.. program:: enable_zone

.. option:: name
 
   domain to be enabled.

.. describe:: Returns
 
   Returns true

Errors will be returned if the zone does not exist.


.. _rpccall_disable_zone:

disable_zone()
--------------

**disable_zone(<name>)**

.. program:: disable_zone

.. option:: name
 
   domain to be enabled.

.. describe:: Returns
 
   Returns true

Errors will be returned if the zone does not exist.


.. _rpccall_delete_zone:

delete_zone()
-------------

**delete_zone(<name>)**

.. program:: delete_zone

.. option:: name
 
   domain to be enabled.

.. describe:: Returns
 
   Returns true

Errors will be returned if the zone does not exist.

.. _rpccall_set_zone:


set_zone()
----------

**set_zone(<name> [edit_lock] [auto_dnssec] [nsec3] [inc_updates])**

.. program:: set_zone

.. option:: name

   domain to be created

.. option:: edit_lock

   optional boolean for turning on edit_lock mode, default false

.. option:: auto_dnssec

   optional boolean for turning on automatic DNSSEC, default false

.. option:: nsec3 

   optional boolean for enabling NSEC3 under DNSSEC, default false

.. option:: inc_updates

   optional boolean for enabling incremental updates for zone, default true for
   basic interface, false for help desk and admin interfaces.

.. describe:: Returns

   Returns true

Errors are returned if a zone already exists.

.. _rpccall_undelete_zone:


undelete_zone()
---------------

**undelete_zone(<zone_id>)**

.. program:: undelete_zone

.. option:: zone_id

   Id of deleted zone to be undeleted

.. describe:: Returns

   Returns true

Undelete a zone.. This can only be done to a deleted zone, and if there are no active zones with the same name.

.. _rpccall_destroy_zone:


destroy_zone()
--------------

**destroy_zone(<zone_id>)**

.. program:: destroy_zone

.. option:: zone_id

   Id of deleted zone to be destroyed

.. describe:: Returns

   Returns true


Destroy a zone.. This can only be done to a deleted zone.

.. _rpccall_copy_zi:

copy_zi()
---------

**copy_zi(<src_name>, <name>, [zi_id])**

.. program:: copy_zi

.. option:: src_name

   Source zone name

.. option:: name

   destination domain name

.. option:: login_id

   DMI login ID. Email address, or numerical login_id

.. option:: zi_id

   ZI ID to be copied, default published ZI of source zone.

.. describe:: Returns

   Returns true

Copy a ZI from a source zone to another.

.. _rpccall_delete_zi:

delete_zi()
-----------

**delete_zi(<name> <zi_id>)**

.. program:: delete_zi

.. option:: name

   domain name

.. option:: zi_id

   ZI ID

Delete a zi. This can only be done for a ZI that is not currently in use.

.. _rpccall_edit_zone:

edit_zone()
-----------

**edit_zone(<name> <login_id> [zi_id])**

.. program:: edit_zone

.. option:: name

   domain to be edited.

.. option:: zi_id

   optional zone-instance number or Null

.. describe:: Returns

Returns: ``list (zone_zi_data, edit_lock_token)``.

Can be: ``[zi_data, edit_lock_token]`` if edit_lock obtained.

``[zi_data, Null]`` if zone does not have edit locking enabled.

Errors are returned if the zone does not exist, ``zi_id`` is invalid, an
``edit_lock`` is not able to be obtained.

Returns a zone structure, with a list of all zis in database for domain,
accompanied by the zi's date. This structure is the one show above for
:ref:`rpccall_show_zone`.

The zi structure contains all the SOA data. Depending on the value of
``use_apex_ns``, for ``True`` the Apex NS records are supplied, and the
secondary DNS server parameters of the SOA record are set-able. Otherwise, the
Apex NS records are not supplied as they are the global DNS secondary server
settings, and the only editable SOA fields (always editable) are
``soa_minimum``, ``soa_ttl``, and ``zone_ttl``. :program:`Dmsdmd` always
generates the SOA record for a zone from the values in the zi structure, and
automatically calculates the zone SOA serial number based on the algorithm used
in the RFCs(RFC 2316 Sec 3.4.2.2, RFC 1982 Section 3) and conventional serial
number guidelines based on the date, if it is possible.

The ``zi_id`` parameter defaults to the published ZI, and another ZI can be given. The edit lock is an optional
feature zone state machine that can be enabled from zone-tool for domains the are often edited, to prevent
unpredictable updates to published zones (Ie 2 people editing server.isp.net simultaneously, and then one having his
changes wiped out by the later publish action). The edit lock is covered by an inactivity timeout which is reset by the
:ref:`rpccall_tickle_editlock` method.

.. _rpccall_tickle_editlock:

tickle_editlock()
-----------------

**tickle_editlock(<name>, <edit_lock_token>)**

.. program:: tickle_editlock

.. option:: name

   domain being edited

.. option:: edit_lock_token

   edit lock token to be tickled

Notification of UI activity to reset edit lock time out.

.. _rpccall_cancel_edit_zone:

cancel_edit_zone()
------------------

**cancel_edit_zone(<name>, <edit_lock_token>)**

.. program:: cancel_edit_zone

.. option:: name

   domain being edited

.. option:: edit_lock_token

   edit lock token to be canceled

Cancels a locked zone editing session.

.. _rpccall_update_zone:

update_zone()
-------------

**update_zone(<name>, <zi_data>, <login_id>, [edit_lock_token])**

.. program:: update_zone

.. option:: name

   domain to be updated

.. option:: zi_data

   new zi structure to be published.

.. option:: login_id

   DMI login_id. Email format, or numerical string.

.. option:: edit_lock_token

   Must be supplied to finish an edit locked session.

Saves zi_data to database for a zone. Queues a ``ZoneSMEditUpdate``
(``edit_locked`` zone event) or ``ZoneSMUpdate`` event to publish domain with
new zi.

.. _rpccall_show_sectags:

show_sectags()
--------------

**show_sectags()**

List all possible security tags. This command is only available with Admin
level DMS client privilege. Sectags are created and deleted from the one_tool
command line. Each WSGI back end has its privilege assigned by configuring it
with a given security tag.

.. _rpccall_show_zone_sectags:

show_zone_sectags()
-------------------

**show_zone_sectags(<name>)**

.. program:: show_zone_sectags

.. option:: name

   domain to be queried.

List the security attached to the given zone. This command is only available
with Admin level DMS client privilege.

.. _rpccall_add_zone_sectag:

add_zone_sectag()
-----------------

**add_zone_sectag(<name>, <sectag>)**

.. program:: add_zone_sectag

.. option:: name

   domain

.. option:: sectag

   sectag to be added

.. describe:: Returns

   Returns true

Adds a sectag to a zone. Admin Level DMS client privilege only.


.. _rpccall_delete_zone_sectag:

delete_zone_sectag()
--------------------

**delete_zone_sectag(<name>, <sectag>):**

.. program:: delete_zone_sectag

.. option:: name

   domain

.. option:: sectag

   sectag to be deleted

.. describe:: Returns

   Returns true

Deletes a sectag from a zone. Admin Level DMS client privilege only.

.. _rpccall_replace_zone_sectags:

replace_zone_sectags()
----------------------

**replace_zone_sectags(<name>, <sectags>)**

.. program:: replace_zone_sectags

.. option:: name

   domain to be operated on

.. option:: sectags

   list of sectags as per above format in listing.

Completely replaces the zones current sectags with the ones specified in the
list. This command is only available with Admin level DMS client privilege.

Thus you can use :ref:`rpccall_show_sectags` to get all possible sectags,
:ref:`rpccall_show_zone_sectags` to fill out check boxes in a dialogue/list, and then call
:ref:`rpccall_replace_zone_sectags` with all checked values when user clicks <OK>/submits in
Web UI.

.. _rpccall_sign_zone:

sign_zone()
-----------

**sign_zone(<name>)**

.. program:: sign_zone

.. option:: name

   domain to be operated on.

.. describe:: Returns

   Returns true

Resign a DNSSEC zone.

.. _rpccall_load_keys:

load_keys()
-----------

**load_keys(<name>)**

.. program:: load_keys

.. option:: name

   domain to be operated on.

.. describe:: Returns

   Returns true

Load the DNSSEC keys for a zone.

.. _rpccall_refresh_zone:

refresh_zone()
--------------

**refresh_zone(<name>)**

.. program:: refresh_zone

.. option:: name

   domain to be refreshed.

.. describe:: Returns

   Returns true

Refresh/update the contents of a zone from the DB into the DNS. Issues a publish event to zone.

.. _rpccall_reset_zone:

reset_zone()
------------

**reset_zone(<name>)**

.. program:: reset_zone

.. option:: name

   domain to be reset

.. describe:: Returns

   Returns true

Resets the zone state machine. Useful for when :program:`dmsdmd` has an
internal error, or when :program:`named` is mis-configured for write access.

.. _rpccall_refresh_zone_ttl:

refresh_zone_ttl()
------------------

**refresh_zone_ttl(<name> [zone_ttl])**

.. program:: refresh_zone_ttl

.. option:: name

   domain name of zone

.. option:: zone_ttl

   named TTL string

.. describe:: Returns

   Returns true

Refresh a zones TTL, using the global default for zone creation if none given.

.. _rpccall_show_configsm:

show_configsm()
---------------

**show_configsm()**

.. program:: show_configsm

.. describe:: Returns

   Returns true

Show the current status of the master named configuration state machine. Useful as it show when the next rndc
config can happen.

.. _rpccall_create_reference:

create_reference()
------------------

**create_reference(<reference>)**

.. program:: create_reference

.. option:: reference

   entity reference string

.. describe:: Returns

   Returns true

Creates an entity reference string in the DMS for use with a set of zones.

.. _rpccall_delete_reference:

delete_reference()
------------------

**delete_reference(<reference>)**

.. program:: delete_reference

.. option:: reference

   entity reference string

.. describe:: Returns

   Returns true

Deletes an unused entity reference string from the DMS when there are no more zones against it.

.. _rpccall_rename_reference:

rename_reference()
------------------

**rename_reference(<reference> <dst_reference>)**

.. program:: rename_reference

.. option:: reference

   original entity reference string

.. option:: dst_reference

   new entity reference string

.. describe:: Returns

   Returns true

Rename a reference in the DMS. This should check with the user first to see if they really want to do this. I can see
someone like Mike wanting to use this from DMI if the ID in the DMS zone database is wrong, if it is an account ID.

.. _rpccall_list_reference:

list_reference()
----------------

**list_reference([reference-wildcard], [<reference-wildcard], ...)**

.. program:: list_reference

.. option:: reference-wildcard

   reference wildcard string.

.. describe:: Returns

   Returns list of references in JSON.

Lists references. Help desk and admin level functionality.


.. _rpccall_set_zone_reference:

set_zone_reference()
--------------------

**set_zone_reference(<name>, <reference>)**

.. program:: set_zone_reference

.. option:: name

   domain to be operated on

.. option:: reference

   reference to be set on domain

.. describe:: Returns

   Returns true

Change the reference on a domain. Again Admin level only functionality.

.. _rpccall_rr_query_db:

rr_query_db()
-------------

**rr_query_db(<label> [name] [type] [rdata] [zi_id] [show_all])**

.. program:: rr_query_db

.. option:: label

   host name or other DNS label

.. option:: name

   domain to be queried

.. option:: type

   RR type

.. option:: rdata

   RR rdata string

.. option:: zi_id

   ZI ID
 
.. option:: show_all

   boolean rue/false, show all records, including disabled ones.

Query the DB ala the OS libc/libresolv hostname() call. This uses a cross zone DB query looking for any records.
This is Admin level only functionality.

.. _rpccall_update_rrs:

update_rrs()
------------

**update_rrs(<name> <update_data> <update_type> <login_id>)**

.. program:: update_rrs

.. option:: name

   domain being updated

.. option:: update_data

   update data for zone

.. option:: update_type

   client update type

.. option:: login_id

   Email format, or numerical string.

Do incremental updates on a zone. The update data is the same ZI data format as in :ref:`rpccall_create_zone`

Example update file from equiv ``zone_tool update_rrs`` command::

       $ORIGIN       foo.bar.org.
                 $UPDATE_TYPE SpannerReplacement_ShouldBeUUIDperClientOpType

                 ;!RROP:DELETE
                 ns5                   IN    ANY        ""    ; All records for ns5
                 ;!RROP:DELETE
                 ns7                   IN    A          ""    ; All A records for ns2
                 ;!RROP:DELETE
                 ns67                  IN    A          192.168.2.3 ; Specific record

                 ;!RROP:ADD
                 ns99                  IN    TXT        "Does not know Maxwell Smart"
                 ;!RROP:ADD
                 ns99                  IN    AAAA            2002:fac::1

                 ;!RROP:UPDATE_RRTYPE
                 ns99            IN AAAA                ::1



The ZI data RRs are augmented with the ``update_op`` property, which takes the
RROP text values of ``ADD``, ``DELETE``, and ``UPDATE_RRTYPE``. As seen above
the ``DELETE`` ``update_op`` can use RR type ANY, and blank rdata as wildcards.
UPDATE_RRTYPE replaces all records of that type for the DNS zone node
concerned.

The ``update_type`` property is used to make sure that only one ``update_type``
is queued per zone for execution. Each update is a unique transaction for the
zone concerned.

Note that their are separate privilege levels for the Admin, help desk, and
ordinary customer front ends, and these can affect the auto reverse parameters
that can be used in the call, exactly the same as for
:ref:`rpccall_update_zone`/:ref:`rpccall_create_zone` above.

Example of the JSON params object feed to the :ref:`rpccall_update_rrs` call::


       {    'name': 'foo.bar.org.',
            'update_data': {   'rr_groups': [  { 'rrs': [ 
                                                 { 'class': 'IN',
                                                   'disable':  false,
                                                   'force_reverse': false,
                                                   'label': 'ns5.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': null,
                                                   'reference': null,
                                                   'type': 'ANY',
                                                   'update_op': 'DELETE'},
                                                 { 'class': 'IN',
                                                   'disable': false,
                                                   'force_reverse': false,
                                                   'label': 'ns7.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': null,
                                                   'reference': null,
                                                   'type': 'A',
                                                   'update_op': 'DELETE'},
                                                 { 'class': 'IN',
                                                   'disable': false,
                                                   'force_reverse': false,
                                                   'label': 'ns67.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': '192.168.2.3',
                                                   'reference': null,
                                                   'type': 'A',
                                                   'update_op': 'DELETE'}]},
                                              {  'rrs': [ 
                                                 { 'class': 'IN',
                                                   'disable': false,
                                                   'force_reverse': false,
                                                   'label': 'ns99.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': '"Does not know Maxwell Smart"',
                                                   'reference': null,
                                                   'type': 'TXT',
                                                   'update_op': 'ADD'},
                                                 { 'class': 'IN',
                                                   'disable': false,
                                                   'force_reverse': false,
                                                   'label': 'ns99.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': '2002:fac::1',
                                                   'reference': null,
                                                   'type': 'AAAA',
                                                   'update_op': 'ADD'}]},
                                               { 'rrs': [   
                                                 { 'class': 'IN',
                                                   'disable': false,
                                                   'force_reverse': false,
                                                   'label': 'ns99.foo.bar.org.',
                                                   'lock_ptr': false,
                                                   'rdata': '::1',
                                                   'reference': null,
                                                   'type': 'AAAA',
                                                   'update_op': 'UPDATE_RRTYPE'}
                                                   ]}
                                              ]},
            'update_type': 'SpannerReplacement_ShouldBeUUIDperClientOpType'}

.. _rpccall_set_zone_sg:

set_zone_sg()
-------------

**set_zone_sg(<name>, <sg_name>)**

.. program:: set_zone_sg

.. option:: name

   domain to be operated on.

.. option:: sg_name

   sg the zone is being moved to.

.. describe:: Returns

   Returns true

Set the SG a zone is served on. Note that this call at present can only be used
on disabled zones. Admin level only call.

.. _rpccall_set_zone_alt_sg:

set_zone_alt_sg()
-----------------

**set_zone_alt_sg(<name>, <sg_name>)**

.. program:: set_zone_alt_sg

.. option:: name

   domain to be operated on.

.. option:: sg_name

   Alternate sg the zone is being served on.

.. describe:: Returns

   Returns true

Set an additional SG a zone will be served on. Note that this call at present
can only be used on disabled zones.  Note that the SG concerned has to be
refreshed. Admin level only call.

.. _rpccall_list_sg:

list_sg()
---------

**list_sg()**

.. program:: list_sg

.. describe:: Returns

Returns list of SGs in JSON format

List all SGs that are existent on the master DNS server. Admin level only call,
for populating menu drop boxes when creating zones etc.

.. _DMS-Errors:


DMS Errors
==========


.. automodule:: dms.exceptions
   :members:
   :show-inheritance:
   :member-order: = 'bysource'

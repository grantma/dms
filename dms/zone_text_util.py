#!usr/bin/env python3.2
#
# Copyright (c) Net24 Limited, Christchurch, New Zealand 2011-2012
#       and     Voyager Internet Ltd, New Zealand, 2012-2013
#
#    This file is part of py-magcode-core.
#
#    Py-magcode-core is free software: you can redistribute it and/or modify
#    it under the terms of the GNU  General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Py-magcode-core is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU  General Public License for more details.
#
#    You should have received a copy of the GNU  General Public License
#    along with py-magcode-core.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Module for Zone text manipuation utilities
"""

from io import StringIO
from textwrap import TextWrapper
import re

from pyparsing import ParseResults
import dns.name
import dns.ttl

from magcode.core.globals_ import *
from dms.globals_ import *
from dms.dns import RRTYPE_SOA
from dms.dns import RROP_DELETE
from dms.dns import is_inet_hostname
from dms.exceptions import NoPreviousLabelParseError
from dms.exceptions import Not7ValuesSOAParseError
from dms.exceptions import SOASerialMustBeInteger
from dms.exceptions import ZoneHasNoSOARecord
from dms.exceptions import BinaryFileError
from dms.exceptions import ZoneNameUndefined
from dms.exceptions import IncludeNotSupported
from dms.exceptions import GenerateNotSupported
from dms.exceptions import UpdateTypeNotSupported
from dms.exceptions import RropNotSupported
from dms.exceptions import TtlParseError
from dms.exceptions import HostnameParseError
from dms.exceptions import TtlInWrongPlace
from dms.exceptions import BadInitialZoneName
# Zone file parser is in a seperate module to contain symbol mess, and
# to aid in debugging from python3.2 command line.
from dms.zone_parser import zone_parser


rdata_re_null = re.compile(r'^""$|^\\#[ 	]+0$')

class DataToBind(object):
    """
    Objects of this class implement the transform from data to bind file
    output
    """
    
    def __init__(self, file=sys.stdout):
        self.comment_group_leader = settings['comment_group_leader']
        self.comment_rr_leader = settings['comment_rr_leader']
        self.comment_rrflags_leader = settings['comment_rrflags_leader']
        self.group_textwrapper = TextWrapper(
                            initial_indent=self.comment_group_leader + ' ',
                            subsequent_indent=self.comment_group_leader + ' ')
        self.rr_textwrapper = TextWrapper(
                            initial_indent=self.comment_rr_leader + ' ',
                            subsequent_indent=self.comment_rr_leader + ' ')
        self.rrflags_textwrapper = TextWrapper(
                            initial_indent=self.comment_rrflags_leader,
                            subsequent_indent=self.comment_rrflags_leader)
        self.for_bind = False
        self.file = file

    def print_group_comment(self, rr_group):
        if not rr_group.get('comment'):
            return
        comment = rr_group['comment']
        if (comment.find('\n') < 0):
            # If comment does not have any linefeeds, wrap it.
            print(self.group_textwrapper.fill(rr_group['comment']),
                    file=self.file)
            return
        # Print out
        comment = comment.split('\n')[:-1]
        for line in comment:
            print(self.comment_group_leader + ' ' + line, file=self.file)


    def print_rr_comment(self, rr):
        if not rr.get('comment'):
            return
        comment = rr['comment']
        if (comment.find('\n') < 0):
            # If comment does not have any linefeeds, wrap it.
            print(self.rr_textwrapper.fill(comment),
                    file=self.file)
            return
        # Print out
        comment = comment.split('\n')[:-1]
        for line in comment:
            print(self.comment_rr_leader + ' ' + line, file=self.file)

    def print_rrflags_comment(self, rr):
        if (not rr.get('lock_ptr') and not rr.get('disable')
                and not rr.get('reference') and not rr.get('track_reverse')):
            return
        rr_flags_strs = []
        if rr['lock_ptr']:
            rr_flags_strs.append(settings['rr_flag_lockptr'])
        if rr['disable']:
            rr_flags_strs.append(settings['rr_flag_disable'])
        if rr['track_reverse']:
            rr_flags_strs.append(settings['rr_flag_trackrev'])
        if rr['reference']:
            rr_flags_strs.append(settings['rr_flag_ref'] + rr['reference'])
        rr_flags_str = ' '.join(rr_flags_strs)
        print(self.rrflags_textwrapper.fill(rr_flags_str), file=self.file)

    def print_rr(self, rr, label, ttl):
        if (self.for_bind and rr.get('disable') != None and rr['disable']):
            label = ';' + label
        print ('%-15s %-7s %-7s %-15s %s' 
                % (label, ttl, rr['class'], rr['type'], rr['rdata']),
                file=self.file)
    
    def print_soa(self, rr, label, ttl):
        rdata = rr['rdata'].split()
        print ('%-15s %-7s %-7s %-15s ( %-12s ;Master NS' 
                % (label, ttl, rr['class'], rr['type'], rdata[0]),
                file=self.file)
        print ('%-47s %-12s ;RP email' % (' ', rdata[1]), file=self.file)
        print ('%-47s %-12s ;Serial yyyymmddnn' % (' ', rdata[2]),
                file=self.file)
        print ('%-47s %-12s ;Refresh' % (' ', rdata[3]), file=self.file)
        print ('%-47s %-12s ;Retry' % (' ', rdata[4]), file=self.file)
        print ('%-47s %-12s ;Expire' % (' ', rdata[5]), file=self.file)
        print ('%-47s %-12s ;Minimum/Ncache' % (' ', rdata[6]), file=self.file)
        print ('%-47s %-12s' % (' ', ')'), file=self.file)

    def print_rr_group(self, rr_group, sort_reverse=False, reference=None):
        """
        Print an rr_group

        This is a bit of a mess, but it gets the job done.
        """
        
        def sort_rr(rr):
            return(rr['label'], rr['type'], rr['rdata'])
       
        if rr_group.get('comment'):
            self.print_group_comment(rr_group)
        previous_label = ''
        for rr in sorted(rr_group['rrs'], key=sort_rr, reverse=sort_reverse):
            self.print_rr_comment(rr)
            if reference and rr['type'] == RRTYPE_SOA:
                rr['reference'] = reference
            self.print_rrflags_comment(rr)
            ttl = rr['ttl'] if rr.get('ttl') else '    '
            label = rr['label'] if (rr.get('label') != previous_label) \
                                    else '    '
            if rr['type'] == RRTYPE_SOA:
                self.print_soa(rr, label, ttl)
            else:
                self.print_rr(rr, label, ttl)
            previous_label = rr['label']
        print('\n\n', file=self.file, end='')

    def __call__(self, zi_data, name=None, reference=None, for_bind=False,
            file=None, no_info_header=False):
        """
        Construct a bind file as a multi-line string, from
        zi_data
        """
        # if zi_data is blank, get out of here...
        if not zi_data:
            return ''
        # Do file/IO house keeping first
        if not file:
            self.file = StringIO()
            return_string = True
        else:
            self.file = file
            return_string = False
        
        # Save bind_p
        self.for_bind = for_bind

        # Set $TTL and $ORIGIN if given
        print ('$TTL %s' % zi_data['zone_ttl'], file=self.file)
        if name:
            print ('$ORIGIN %s' % name, file=self.file)
        print(file=self.file)

        # Add reference comment if reference given
        zi_id = zi_data.get('zi_id')
        zi_change_by = zi_data.get('change_by')
        zi_ctime = zi_data.get('ctime')
        zi_mtime = zi_data.get('mtime')
        zi_ptime = zi_data.get('ptime')
        if not no_info_header and (reference or name or zi_id):
            # Trailing double line feed for readability
            out = ";\n"
            if name:
                out += "; Zone:       %s\n" % name
            if reference:
                out += "; Reference:  %s\n" % reference
            if zi_change_by:
                out += "; change_by:  %s\n" % zi_change_by
            if zi_id:
                out += "; zi_id:      %s\n" % zi_id
            if zi_ctime:
                out += "; zi_ctime:   %s\n" % zi_ctime
            if zi_mtime:
                out += "; zi_mtime:   %s\n" % zi_mtime
            if zi_ptime:
                out += "; zi_ptime:   %s\n" % zi_ptime
            out += ";\n\n"
            print(out, file=self.file)

        # Index rr_groups, for printing
        rr_groups = {}
        flimflam_gid = '' 
        for rr_group in zi_data['rr_groups']:
            group_tag = rr_group.get('tag')
            group_comment = rr_group.get('comment')
            if group_tag == settings['apex_rr_tag']:
                group_id = group_tag
            elif group_comment:
                group_id = group_comment
            elif group_tag:
                group_id = group_tag
            else:
                group_id = str(flimflam_gid)
                if flimflam_gid == '':
                    flimflam_gid = 0
                flimflam_gid += 1
            rr_groups[group_id] = rr_group
        
        # Print Apex Records if there are any
        rr_group = rr_groups.get(settings['apex_rr_tag'])
        if rr_group:
            self.print_rr_group(rr_group, sort_reverse=True, 
                    reference=reference)
            del rr_groups[settings['apex_rr_tag']]

        # Print the rest, followed by default group
        default_group = rr_groups.pop('', None)
        for rr_group in sorted(rr_groups):
            self.print_rr_group(rr_groups[rr_group])
        if default_group:
            self.print_rr_group(default_group)

        # clean up
        if return_string:
            result = self.file.getvalue()
            self.file.close()
            return result

def data_to_bind(zi_data, name=None, file=None, 
        for_bind=False, reference=None, no_info_header=False):
    """
    Translate data to bind file output
    """
    transform = DataToBind()
    return transform(zi_data, name=name, file=file, 
                for_bind=for_bind, reference=reference, 
                no_info_header=no_info_header)

def _validate_pyparsing_hostname(name, data, text):
    try:
        thing = dns.name.from_text(text)
    except Exception as exc:
        raise HostnameParseError(name, data, text, str(exc))
    if not is_inet_hostname(text):
        raise HostnameParseError(name, data, text, None)
    if not text.endswith('.'):
        raise HostnameParseError(name, data, text, "must end with '.'.")

def _validate_pyparsing_ttl(name, data, text):
    """
    Validate a ttl value
    """
    if len(text) > 20:
        raise TtlParseError(name, data, text, "longer than 20 chars.")
    try:
        thing = dns.ttl.from_text(text)
    except Exception as exc:
        raise TtlParseError(name, data, text, str(exc))

def bind_to_data(bind_file, name=None, use_origin_as_name=False, 
                    update_mode=False):
    """
    Construct zi_data, taking a bind file as input.  Can be a string, 
    or file handle.
    """
    def validate_initial_name():
        if not name:
            return
        if isinstance(bind_file, StringIO):
            input_thing = 'StringIO object'
        elif file_name:
            input_thing = file_name
        else:
            input_thing = ('FD %s' % str(bind_file.fileno()))
        try:
            thing = dns.name.from_text(name)
        except Exception as exc:
            raise BadInitialZoneName(input_thing, name, str(exc))
        if not is_inet_hostname(name):
            raise BadInitialZoneName(input_thing, name, None)
        if not name.endswith('.'):
            raise BadInitialZoneName(input_thing, name, "must end with '.'.")

    def check_name_defined():
        if not name:
            if isinstance(bind_file, StringIO):
                raise ZoneNameUndefined('StringIO object')
            elif file_name:
                raise ZoneNameUndefined(file_name)
            else:
                raise ZoneNameUndefined('FD %s' % str(bind_file.fileno()))

    file_name = None
    if isinstance(bind_file, str):
        file_name = bind_file
        # Open file
        # Check that file is not 'binary'
        bfile = open(file_name, mode='rb')
        bs = bfile.read(256)
        bfile.close()
        try:
            if not bs.decode().replace('\n', ' ')\
                    .replace('\t', ' ').isprintable():
                raise BinaryFileError(bind_file) 
        except UnicodeError:
                raise BinaryFileError(bind_file) 

        bind_file = open(file_name, mode='rt')

    # Check Initial name and if it is garbage do something appropriate
    try:
        validate_initial_name()
    except BadInitialZoneName as exc:
        if not use_origin_as_name:
            if file_name:
                bind_file.close()
            raise exc
        name = None

    # Feed through pyparsing to get back a parse result we can traverse
    # Error Exceptions handled at higher level for error processing
    try:
        zone_parse = zone_parser.parseFile(bind_file, parseAll=True)
    finally:
        if file_name:
            bind_file.close()

    # Turn parse result into a JSON zi data structure
    zi_data = {'rr_groups':[], }
    # List of all rrs for sorting out Apex and SOA data at end
    # of loop
    rr_list = []
    # Loop data variables
    in_rr_group = False
    comment_rr = None
    comment_rrflags = None
    update_type = None
    zone_reference = None
    comment_group = None
    previous_label = None
    origin = name if name else None
    ttl_seen = False
    ttl = None
    in_rr_prologue = True
    rr_group = {'rrs':[]}
    for thing in zone_parse:
        if (isinstance(thing, dict)
                and thing['type'] == '$ORIGIN'):
            _validate_pyparsing_hostname(name, thing, thing['origin'])
            origin = thing['origin']
            continue

        if (isinstance(thing, dict)
                and thing['type'] == '$TTL'):
            if ttl_seen:
                raise TtlInWrongPlace(name, thing, file_name)
            _validate_pyparsing_ttl(name, thing, thing['ttl'])
            ttl_seen = True
            zi_data['zone_ttl'] = thing['ttl']
            continue

        if (isinstance(thing, dict)
                and thing['type'] == '$INCLUDE'):
            raise IncludeNotSupported(name, thing)

        if (isinstance(thing, dict)
                and thing['type'] == '$GENERATE'):
            raise GenerateNotSupported(name, thing)

        if (isinstance(thing, dict)
                and thing['type'] == '$UPDATE_TYPE'):
            if not update_mode:
                raise UpdateTypeNotSupported(name, thing)
            update_type = thing['update_type']

        if (isinstance(thing, dict) 
                and thing['type'] == 'comment_rr'):
            #Process an  RR comment
            comment_rr = thing
            comment_rr.pop('comment_type', None)
            continue
        
        if (isinstance(thing, dict) 
                and thing['type'] == 'comment_rrflags'):
            #Process rr_flags
            comment_rrflags = thing
            comment_rrflags.pop('comment_type', None)
            continue

        if (isinstance(thing, dict)
                and thing['type'] == 'comment_group'):
            #Process a group comment
            comment_group = thing
            comment_group.pop('comment_type', None)
            if not in_rr_group:
                # Start New RR Group from previous blank lines
                in_rr_group = True
                rr_group.update(comment_group)
            else:
                # Start new RR_Group
                zi_data['rr_groups'].append(rr_group)
                rr_group = {'rrs':[]}
                rr_group.update(comment_group)
            continue

        if isinstance(thing, ParseResults):
            # $TTL should have happened by now
            ttl_seen = True
            if in_rr_prologue:
                in_rr_prologue = False
                # if no name, should have seen $ORIGIN by now
                if origin and use_origin_as_name:
                    name = origin
                check_name_defined()

            # Start process RRs
            if not in_rr_group:
                in_rr_group = True
            # Process an RR
            rr = {}
            # Have to break down to keys we accept  - security
            # Sort out RR label - if none, use last seen value of label
            rr['label'] = thing.get('label')
            if not rr['label']:
                if not previous_label:
                    # This should not happen!
                    # This error is feature specific to the parser design,
                    # and should be raised here
                    raise NoPreviousLabelParseError(domain=name)
                rr['label'] = previous_label
            else:
                previous_label = rr['label']

            # Apply $ORIGIN to label.  This will be relativized when 
            # actual RR object is created.
            if origin and not rr['label'].endswith('.'):
                if rr['label'] == '@':
                    rr['label'] = origin
                else:
                    rr['label'] = '.'.join((rr['label'],origin))

            # Add preceding rr_flags and comment_rr to RR
            if comment_rr:
                rr.update(comment_rr)
                comment_rr = None

            # Decode rr_flags
            rr['lock_ptr'] = False
            rr['disable'] = False 
            rr['force_reverse'] = False 
            rr['track_reverse'] = False 
            rr['reference'] = None 
            rr['update_op'] = None
            if comment_rrflags:
                rr_flags = comment_rrflags['rr_flags'].strip()
                if rr_flags.find(settings['rr_flag_forcerev']) >= 0:
                    rr['force_reverse'] = True 
                if rr_flags.find(settings['rr_flag_trackrev']) >= 0:
                    rr['track_reverse'] = True 
                if rr_flags.find(settings['rr_flag_lockptr']) >= 0 :
                    rr['lock_ptr'] = True 
                if rr_flags.find(settings['rr_flag_disable']) >= 0 :
                    rr['disable'] = True 
                rr_flags = rr_flags.split()
                for rr_flag in rr_flags:
                    if not (rr_flag.find(settings['rr_flag_ref']) >= 0):
                        continue
                    reference = rr_flag[len(settings['rr_flag_ref']):]
                    if (thing.get('type') and thing['type'] == RRTYPE_SOA
                            and not rr['disable']):
                        zone_reference = reference
                        break
                    rr['reference'] = reference
                    break
                for rr_flag in rr_flags:
                    if not (rr_flag.find(settings['rr_flag_rrop']) >= 0):
                        continue
                    update_op = rr_flag[len(settings['rr_flag_rrop']):]
                    if not update_mode:
                        raise RropNotSupported(name, comment_rrflags)
                    rr['update_op'] = update_op
                    break
                comment_rrflags = None
            
            # Unpack and decode rdata from pyparsing
            # This gives us the file location and output line showing position
            # for any rdata exceptions we throw later in 
            # dms.database.resource_record.data_to_rr()
            if thing.get('rdata'):
                rdata = thing['rdata']
                if isinstance(rdata, dict):
                    rr['rdata'] = rdata.get('rdata')
                    rr['rdata_pyparsing'] = rdata.get('pyparsing')
                else:
                    rr[rdata] = rdata
                if rr['update_op'] == RROP_DELETE:
                    # For delete update_op, transliterate rdata strings
                    if rdata_re_null.search(rr['rdata']):
                        rr['rdata'] = None
                        

            # Do type, class, and ttl
            for key in ('type', 'class', 'ttl'):
                if thing.get(key):
                    rr[key] = thing[key]
            # Add rr to rr_group and rr_list
            rr_group['rrs'].append(rr)
            rr_list.append(rr) 
            continue

        if thing == '\n':
            # Process a blank line
            if in_rr_group:
                in_rr_group = False
                # Add rr_group to list of rr_groups
                zi_data['rr_groups'].append(rr_group)
                rr_group = {'rrs':[]}
            continue

        # We don't care bout this 'thing'
        continue
    else:
        # clean up - if this is not done, not ending in a blank line will
        # lose records....
        if in_rr_group:
             # Add rr_group to list of rr_groups
             zi_data['rr_groups'].append(rr_group)
        
    # Fill in zi_data fields from SOA. Use first SOA found.  Will check
    # for duplicate SOA further in, as that may be recieved from DMI/DMS
    rr_soas = [rr for rr in rr_list if rr['type'] == RRTYPE_SOA]
    if not rr_soas:
        # Leave early as this might just be a zone file being loaded for
        # a use_apex_ns zone, in which case this does not matter
        check_name_defined()
        return (zi_data, name, update_type, zone_reference)
    rr_soa = rr_soas.pop(0)
    # Determine zone name if use_origin_as_name is set, by looking at SOA
    # record label
    if use_origin_as_name:
        if rr_soa['label'][-1] == '.':
            name = rr_soa['label']

    check_name_defined()
    
    zi_data['soa_ttl'] = rr_soa.get('ttl')
    # Parse SOA Rdata
    soa_rdata = rr_soa['rdata'].split()
    num_values = len(soa_rdata)
    if (num_values != 7):
        raise Not7ValuesSOAParseError(name,
                rr_soa)
    error_info = ''
    try:
        zi_data['soa_serial'] = int(soa_rdata[2])
    except ValueError as exc:
        error_info = str(exc)
    if error_info:
        raise SOASerialMustBeInteger(name,
                rr_soa)
    zi_data['soa_mname'] = soa_rdata[0]
    zi_data['soa_rname'] = soa_rdata[1]
    zi_data['soa_refresh'] = soa_rdata[3]
    zi_data['soa_retry'] = soa_rdata[4]
    zi_data['soa_expire'] = soa_rdata[5]
    zi_data['soa_minimum'] = soa_rdata[6]

    return (zi_data, name, update_type, zone_reference)









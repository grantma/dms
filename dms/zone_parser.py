#!/usr/bin/env python3.2
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
Zone parser pyparsing sandpit module!

Broken out like this for interactive test and debug.
See test section at end of file.

$ORIGIN even though parsed is only for documentation purposes, and $INCLUDE
is not processed in the following. $TTL feeds into the zone_ttl setting for a 
zone.
"""

import re
import sys

from pyparsing import *
import dns.name

from magcode.core.globals_ import *
from dms.globals_ import *
from dms.database.resource_record import rrtype_map


# Comment leader settings
comment_group_leader = settings['comment_group_leader']
comment_rr_leader = settings['comment_rr_leader']
comment_rrflags_leader = settings['comment_rrflags_leader']
comment_anti_regexp = settings['comment_anti_regexp']
rr_flag_lockptr = settings['rr_flag_lockptr']
rr_flag_forcerev = settings['rr_flag_forcerev']
rr_flag_disable = settings['rr_flag_disable']
rr_flag_ref = settings['rr_flag_ref']
rr_flag_rrop = settings['rr_flag_rrop']
rr_flag_trackrev = settings['rr_flag_trackrev']

# global data
previous_label = None
zone_parser_testing = False

def set_test_mode():
    global zone_parser_testing
    zone_parser_testing = True

# Turn of linefeed \n is whitespace as much as possible as zone files are line
# oriented, and turning off \n in pyparsing class data default whitespace 
# in base class will affect parsing of key files elsewhere in program...
# 
# Zone files as per RFC 1034/1035 use the absence of a owner/label
# (blank whitespace) in an RR record to say that the line is addtional 
# record for the last owner/label
# The label/owner and 'blank' have to be hard against the start of line!...


# Parsing exceptions for label, class, type

class ParseLabelException(ParseBaseException):
    """
    If dnspython can't decode this label, throw a stringy!
    """
    pass

class ParseClassException(ParseBaseException):
    """
    If ain't IN, swear to all the dogs in town!
    """
    pass

class ParseTypeException(ParseBaseException):
    """
    If we don't support this RR type, throw another stringy!
    """
    pass

class ParseNoPreviousLabelException(ParseBaseException):
    """
    No previous label found, lets throw a wangy!
    """
    pass

class SetWhitespace(object):
    def __init__(self, whitespacechars):
        self.whitespacechars = whitespacechars
                     
    def __call__(self,pyparsing_expr):
        pyparsing_expr.setWhitespaceChars(self.whitespacechars)
        return pyparsing_expr

# Wrapper calls to make \n not whitespace...
lo = SetWhitespace(' \t\r')
noWS = SetWhitespace('')

rdatachars = alphanums + '/' + '+' + '=' + '.' + ':' + '@' + '-' + '$' + "\\" + '!' + '#' + '%' + '^' + '&' + '*' + '_' + '|' + '{' + '}' + '[' + ']' + "'" + ',' + '?' 
labelchars = alphanums + '.' + '-' +'_' + '*' + '@'
zonechars = alphanums + '.' + '-' +'_'
refchars = alphanums + '.' + '-' + '_' +'@'
rropchars = alphanums + '_'
updatetypechars = alphanums + '_' + '.' + '-'
ttlchars = nums + 'wWdDhHmMsS'
blank = White(ws=' \t')
whiteline = lo(Suppress(lo(blank + LineEnd())))
nullline = LineEnd()
endofdoc = (StringEnd() | (LineEnd()+StringEnd()))
o_paren = Suppress((Literal('(')))
c_paren = Suppress((Literal(')')))
lo_line_end = lo(Suppress(LineEnd()))
lo_line_start = lo(Suppress(LineStart()))
comment_blank_line = lo(Literal(';') + LineEnd())
comment_line = lo(lo(Regex(comment_anti_regexp)) + restOfLine + LineEnd())
comment = lo(Suppress(lo(comment_blank_line|comment_line)))

# Comment text line
comment_txt_ln = noWS(Regex(r'[\S \t]+'))
comment_txt_ln.setParseAction(lambda tokens : tokens[0])
comment_spc = noWS(Suppress(noWS(Literal(' '))))

def crr_parse_action(tokens):
    if not tokens:
        return
    result =  {'comment': '\n'.join(tokens) + '\n'}
    result['type'] = 'comment_rr'
    return result
comment_rr_start = noWS(Suppress(noWS(Combine(comment_rr_leader))))
comment_rr_ln = lo(comment_rr_start + comment_spc + comment_txt_ln + lo_line_end)
comment_rr_blank = lo(comment_rr_start + lo_line_end)
comment_rr_blank.setParseAction(lambda tokens : '')
comment_rr = lo(OneOrMore(lo(comment_rr_ln|comment_rr_blank)))
comment_rr.setParseAction(crr_parse_action)


rrflags_re_start = re.compile('^' + comment_rrflags_leader)
def rrflags_start_fail(s, loc, expr, err):
    if rrflags_re_start.search(s[loc:]):
        # This is a HACK, but it saves stuffing around here. 
        msg = ('Expected "%s|%s|%s|%s|%s<reference>|%s<update-op>"' 
                % (rr_flag_lockptr, rr_flag_forcerev, rr_flag_trackrev, 
                    rr_flag_disable, rr_flag_ref, rr_flag_rrop))
        raise ParseFatalException(err.pstr, err.loc, msg, err.parserElement)
    else:
        raise err
def crrf_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {'rr_flags': ' '.join(tokens)}
    result['type'] = 'comment_rrflags'
    result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    return result
def crrfr_parse_action(tokens):
    if not tokens:
        return
    return ''.join(tokens)
comment_rrflags_start = noWS(LineStart()) + noWS(Suppress(lo(Combine(comment_rrflags_leader))))
comment_rrflags_LOCKPTR = lo(Combine(rr_flag_lockptr))
comment_rrflags_FORCEREV = lo(Combine(rr_flag_forcerev))
comment_rrflags_TRACKREV = lo(Combine(rr_flag_trackrev))
comment_rrflags_DISABLE = lo(Combine(rr_flag_disable))
comment_rrflags_REF = lo(And([noWS(Combine(rr_flag_ref)), noWS(Word(refchars))]))
comment_rrflags_REF.setParseAction(crrfr_parse_action)
comment_rrflags_RROP = lo(And([noWS(Combine(rr_flag_rrop)), noWS(Word(rropchars))]))
comment_rrflags_RROP.setParseAction(crrfr_parse_action)
comment_rrflags_flags = lo(OneOrMore(lo(comment_rrflags_LOCKPTR|comment_rrflags_FORCEREV|comment_rrflags_TRACKREV|comment_rrflags_DISABLE|comment_rrflags_REF|comment_rrflags_RROP)))
comment_rrflags = comment_rrflags_start + comment_rrflags_flags + lo_line_end
comment_rrflags.setParseAction(crrf_parse_action)
comment_rrflags.setFailAction(rrflags_start_fail)

def rdata_fail_action(s, loc, expr, err):
    # Deal with no Rdata
    if (s[loc] == '\n' or s[loc:err.loc-1].strip() == ''):
        msg = 'Expected RDATA'
        raise ParseFatalException(err.pstr, err.loc-1, msg)
    raise err
def rdata_parse_action(s, loc, tokens):
    if zone_parser_testing:
        return ' '.join(tokens)
    rdata = {}
    rdata['rdata'] = ' '.join(tokens)
    rdata['pyparsing'] = {'s': s, 'loc': loc}
    return rdata
rdata_end = LineEnd()
rdata_comment = lo(lo(Literal(';')) + lo(restOfLine))
rdata_word = lo(Or([dblQuotedString, lo(Word(rdatachars))]))
rdata_word_ml = dblQuotedString | Word(rdatachars)
rdata_1l = lo(And([lo(OneOrMore(rdata_word)), lo(Suppress(rdata_end))]))
rdata_ml = lo(And([lo(ZeroOrMore(rdata_word)), lo(o_paren + OneOrMore(rdata_word_ml) + c_paren), lo(ZeroOrMore(rdata_word)), lo(Suppress(rdata_end))]))
rdata = lo(Or([rdata_ml, rdata_1l]))
rdata.setParseAction(rdata_parse_action)
rdata.setFailAction(rdata_fail_action)


# Both of the following are to make parsing fail fatally in an RR, as they are
# uniquely identified by starting with '^blob.dot.com' or '^<blank>IN'
rr_re_label = re.compile('^[\-a-zA-Z0-9\._@]+\s+')
rr_re_blank = re.compile('^\s+')
def rr_lbl_fail(s, loc, expr, err):
    if rr_re_label.search(s[loc:]):
        raise ParseFatalException(err.pstr, err.loc, err.msg, err.parserElement)
    else:
        raise err
def rr_lbl_parse_action(s, loc, tokens):
    global previous_label
    previous_label = tokens[0][0]
    return tokens
def rr_cont_fail(s, loc, expr, err):
    if rr_re_blank.search(s[loc:]):
        raise ParseFatalException(err.pstr, err.loc, err.msg, err.parserElement)
    else:
        raise err
def rr_cont_parse_action(s, loc, tokens):
    if not previous_label:
        raise ParseNoPreviousLabelException(s, loc, 
                "No previous label in file")
    return tokens
def rr_label_parse_action(s, loc, tokens):
    try:
        thing = dns.name.from_text(tokens[0], None)
    except:
        raise ParseLabelException(s, loc, 'Invalid DNS Label')
    if (tokens[0].find('@') >= 0 and len(tokens[0]) != 1):
        raise ParseLabelException(s, loc, 'Invalid DNS Label')
    if (tokens[0].find('-') == 0):
        raise ParseLabelException(s, loc, 'Invalid DNS Label')
    if (tokens[0].find('.-') >= 0):
        raise ParseLabelException(s, loc, 'Invalid DNS Label')
    return tokens
def rr_type_parse_action(s, loc, tokens):
    if not tokens[0].upper() in rrtype_map.keys():
        raise ParseTypeException(s, loc, "Unsupported RR type '%s'" % tokens[0])
    return str(tokens[0])
def rr_class_parse_action(s, loc, tokens):
    if tokens[0].upper() != 'IN':
        raise ParseTypeException(s, loc, "Unsupported RR class '%s'" % tokens[0])
    return str(tokens[0])
rr_label = noWS(Word(labelchars))
rr_label.setParseAction(rr_label_parse_action)
rr_type = lo(noWS(Word(alphanums)) + FollowedBy(blank))
rr_type.setParseAction(rr_type_parse_action)
rr_class = lo(noWS(lo(CaselessLiteral('IN')|CaselessLiteral('HS')|CaselessLiteral('CH'))) + FollowedBy(blank))
rr_class.setParseAction(rr_class_parse_action)
rr_ttl = lo(noWS(Regex(r'([0-9]+[wWdDhHmMsS]?){1,7}')) + FollowedBy(blank))
rr_ttl.setParseAction(lambda tokens : str(tokens[0]))
rr_lbl = (Group(noWS(LineStart()) + lo(rr_label.setResultsName('label') + lo(Optional(lo(rr_ttl.setResultsName('ttl') + rr_class.setResultsName('class'))|lo(rr_class.setResultsName('class') + rr_ttl.setResultsName('ttl'))|rr_ttl.setResultsName('ttl')|rr_class.setResultsName('class'))) + rr_type.setResultsName('type') + rdata.setResultsName('rdata').ignore(rdata_comment))))
rr_lbl.setFailAction(rr_lbl_fail)
rr_lbl.setParseAction(rr_lbl_parse_action)
# Had to leave lo() of the following And to let 'blank' be recognised
rr_cont = Group(noWS(LineStart()) + blank.setResultsName('blank') + lo(Optional(lo(rr_ttl.setResultsName('ttl') + rr_class.setResultsName('class'))|lo(rr_class.setResultsName('class') + rr_ttl.setResultsName('ttl'))|rr_ttl.setResultsName('ttl')|rr_class.setResultsName('class'))) + rr_type.setResultsName('type') + rdata.setResultsName('rdata').ignore(rdata_comment))
rr_cont.setFailAction(rr_cont_fail)
rr_cont.setParseAction(rr_cont_parse_action)

def cg_parse_action(tokens):
    if not tokens:
        return
    result =  {'comment': '\n'.join(tokens) + '\n'}
    result['type'] = 'comment_group'
    return result
comment_group_start = noWS(Suppress(noWS(Combine(comment_group_leader))))
comment_group_ln = lo(comment_group_start + comment_spc + comment_txt_ln + lo_line_end)
comment_group_blank = lo(comment_group_start + lo_line_end)
comment_group_blank.setParseAction(lambda tokens : '')
comment_group = lo(OneOrMore(lo(comment_group_ln|comment_group_blank)))
comment_group.setParseAction(cg_parse_action)

directive_comment = noWS(Regex(r';[\S \t]*'))
directive_line_end = lo(Suppress(LineEnd())).ignore(directive_comment)

def origin_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {'origin': tokens[0][0]}
    result['type'] = result['directive'] = '$ORIGIN'
    if not zone_parser_testing:
        result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    return result
origin = Group(lo(Suppress(lo(Combine('$ORIGIN')))) + lo(Word(zonechars)) + directive_line_end)
origin.setParseAction(origin_parse_action)

def dollar_ttl_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {'ttl': tokens[0][0]}
    result['type'] = result['directive'] = '$TTL'
    if not zone_parser_testing:
        result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    return result
dollar_ttl = Group(lo(Suppress(lo(Combine('$TTL')))) + lo(Word(ttlchars)) + directive_line_end)
dollar_ttl.setParseAction(dollar_ttl_parse_action)

def dollar_include_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {'filename': tokens[0][0]}
    if len(tokens[0]) > 1:
        result['origin'] = tokens[0][1]
    result['type'] = result['directive'] = '$INCLUDE'
    if not zone_parser_testing:
        result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    return result
dollar_include = Group(lo(Suppress(lo(Combine('$INCLUDE')))) + lo(Word(printables)) +lo(Optional(lo(Word(zonechars)))) + directive_line_end)
dollar_include.setParseAction(dollar_include_parse_action)

def dollar_generate_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {}
    result['type'] = result['directive'] = '$GENERATE'
    if not zone_parser_testing:
        result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    result['text'] = tokens[0][0]
    return result
dollar_generate = Group(lo(Suppress(lo(Combine('$GENERATE')))) + comment_spc +comment_txt_ln + directive_line_end)
dollar_generate.setParseAction(dollar_generate_parse_action)

def dollar_update_type_parse_action(s, loc, tokens):
    if not tokens:
        return
    result = {}
    result['type'] = result['directive'] = '$UPDATE_TYPE'
    if not zone_parser_testing:
        result['rdata_pyparsing'] = {'s': s, 'loc': loc}
    result['update_type'] = tokens[0][0]
    return result
dollar_update_type = Group(lo(Suppress(lo(Combine('$UPDATE_TYPE')))) + lo(Word(updatetypechars)) + directive_line_end)
dollar_update_type.setParseAction(dollar_update_type_parse_action)

zone_parser = OneOrMore(origin|dollar_ttl|dollar_include|dollar_generate|dollar_update_type|comment_rr|comment_group|comment_rrflags|nullline|rr_lbl|rr_cont).ignore(comment)

# Uncommenting this makes debug painful..... we only 
#
# from dms.zone_parser import zone_parser
#
# into where this grammar definition is used, and ignore all else.
# __all__ = ('zone_parser', )


# Test by using:    from dms.zone_parser import *
#                   set_test_mode()
#                   zone_parser.parseString(<test-string>, parseAll=True)
# where zone_parser can be replaced by other grammar elements
def init_test():
    set_test_mode()

def do_all_tests(start=''):
    for k in test.keys():
        if (str(k) < str(start)):
            continue
        do_test(k)
        input('>>> Press <Enter>')

def do_test(n):
        print( 'test[%s] data:\n' % str(n) + test[n])
        try: 
            print('Parse Output:\n' + repr(zone_parser.parseString(test[n],
                                            parseAll=True)))
        except ParseBaseException as exc:
            print(str(exc))

rdata_test = {}
rdata_test[1] = "16 anathoth.net.\n"
rdata_test[2] = "ns1.anathoth.net. root.anathoth.net (\n 2011060900\n 600 600\n600 600\n )\n"
rdata_test[3] = '16 anathoth.net. "Something curly \" is here"\n'

test = {}
test[1] = "host IN A 192.168.23.4\n  IN MX 16 anathoth.net.\n IN A 192.168.34.56\n"
test[2] = "host IN A 192.168.23.4\n  IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n"
test[3] = "host IN A 192.168.23.4\n  IN SOA ns1.anathoth.net. root.anathoth.net. (\n 2011060800\n 600\n ) 600 600 600\n IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n"
test[4] = "host IN A 192.168.23.4\n  IN SOA ns1.anathoth.net. root.anathoth.net. (\n 2011060800\n 600\n  600 600 600 )    \n IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n\nhost3 IN A 192.168.45.6\n"
test[5] = "host IN A 192.168.23.4\n  IN SOA ns1.anathoth.net. root.anathoth.net. (\n 2011060800\n 600\n 600 600 600 );another comment\n IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n\nhost3 600 A 192.168.45.6; another comment \n"
test[6] = ";# RR Comment 1\nhost IN A 192.168.23.4\n;# RRComment 3\n  IN SOA ns1.anathoth.net. root.anathoth.net. (\n 2011060800\n 600\n 600 600 600 );another comment\n;# Stupid MX Record!\n IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n\nhost3 600 A 192.168.45.6; another comment \n"
test[7] = ";# RR Comment 1\nhost IN A 192.168.23.4\n;# RRComment 3\n  IN SOA ns1.anathoth.net. root.anathoth.net. (\n 2011060800\n 600\n 600 600 600 );another comment\n;# Stupid MX Record!\n IN MX 16 anathoth.net.\nhost2 IN A 192.168.34.56\n\n;|\n;| Test RR Group Comment\n;|\nhost3 600 A 192.168.45.6; another comment \n"
test[8] = ';|\n;| Test RR Group Comment\n;|\nhost3 600 A 192.168.45.6; another comment \n'
test[9] = ';|\n;|\n;| Test RR Group Comment\n;|\nhost3 600 A 192.168.45.6; another comment \n'
test[10] = ';| Some Silly Stuff\n;|\n;| Test RR Group Comment\n;|\nhost3 600 A 192.168.45.6; another comment \n'

test[11] = ';#\n;# Test RR Comment\n;#\nhost3 600 A 192.168.45.6; another comment \n'
test['11a'] = ';#\n;# Test RR Comment\n;# \nhost3 600 A 192.168.45.6; another comment \n'
test[12] = ';|\n;|\n;| Test RR Comment\n;# \nhost3 600 A 192.168.45.6; another comment \n'
test[13] = ';# Some Silly Stuff\n;#   Blah\n;# Test RR Comment\n;#    \nhost3 600 A 192.168.45.6; another comment \n'
test['13a'] = ';# Some Silly Stuff\n;#\n;# Test RR Comment\n;#\nhost3 600 A 192.168.45.6; another comment \n'
#
test[14] = '''

$TTL 99999
$ORIGIN anathoth.net.

; This is a comment
;|
;| Apex records for anathoth.net.
;|
@                          IN  SOA         ( ns1          ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1
                           IN  NS          ns2

; This is a comment

   


;| Group Comment
;# Website Ip Address
@                          IN  A           203.79.116.183
ns1                        IN  A           203.79.116.183
ns2                        IN  A           210.5.55.246

;| Group Comment
;# Website Ip Address
@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

;| Group Comment
;|
;#
@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

'''

test['14a'] = '''

$TTL 99999
$ORIGIN anathoth.net.

;|
;| Apex records for anathoth.net.
;|
@                          IN  SOA         ( ns1          ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1
                           IN  NS          ns2

; This is a comment

   


;| Group Comment
;# Website Ip Address
@                          IN  A           203.79.116.183
ns1                        IN  A           203.79.116.183
ns2                        IN  A           210.5.55.246

;| Group Comment
;# Website Ip Address
@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

;| Group Comment
;|
;#
@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

@                          IN  A           203.79.116.183
host1                        IN  A           203.79.116.183
host2                        IN  A           210.5.55.246

'''
test[15] = """
$TTL 600
$ORIGIN anathoth.net.

;|
;| Apex resource records for anathoth.net. I need a new pair of
;| binoculars for cyber-space dancing!!!
;|
@         2*3                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1.anathoth.net.
                           IN  NS          ns2.anathoth.net.
                           IN  NS          ns3.anathoth.net.


;# Website Ip Address
@                          IN  A           203.79.116.183
host                       IN  A           210.5.55.246
ns1                        IN  A           203.79.116.183
;# This is the 2nd name server. It is NOT running.
ns2                        IN  A           210.5.55.246

"""

test[16] = """@         2*3                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )    \n"""

test[17] = """
$TTL 600
$ORIGIN anathoth.net.

;|
;| Apex resource records for anathoth.net. I need a new pair of
;| binoculars for cyber-space dancing!!!
;|
@         23                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1.anathoth.net.
                           IN  NS          ns2.anathoth.net.
                           IN  NS          ns3.anathoth.net.

*

;# Website Ip Address
@                          IN  A           203.79.116.183
host                       IN  A           210.5.55.246
ns1                        IN  A           203.79.116.183
;#3 This is the 2nd name server. It is NOT running.
ns2                        IN  A           210.5.55.246

"""
test[18] = """
$TTL 600
$ORIGIN anathoth.net.

;|
;| Apex resource records for anathoth.net. I need a new pair of
;| binoculars for cyber-space dancing!!!
;|
@         23                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1.anathoth.net.
                           IN  NS          ns2.anathoth.net.
                           IN  NS          ns3.anathoth.net.


;# Website Ip Address
@                          IN  A           203.79.116.183
host                       IN  A           210.5.55.246
ns1                        IN  A           203.79.116.183
;# This is the 2nd name server. It is NOT running.
ns2                        I*N  A           210.5.55.246

"""
test[19] = """
$TTL 600
$ORIGIN anathoth.net.

;|
;| Apex resource records for anathoth.net. I need a new pair of
;| binoculars for cyber-space dancing!!!
;|
@         23                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )           
                           IN  NS          ns1.anathoth.net.
                           IN  NS          ns2.anathoth.net.
                           IN  NS          ns3.anathoth.net.


;# Website Ip Address
@                           IN  A           203.79.116.183
;!LOCKPTR
host                       IN  A           210.5.55.246
ns1                        IN  A           203.79.116.183
;# This is the 2nd name server. It is NOT running.
;!FORCEREV DISABLE REF:Anathoth65     
ns2                        IN  A           210.5.55.246
;!TRACKREV DISABLE REF:Anathoth65     
ns3                        IN  A           210.5.55.247
;!RROP:DELETE     
host12                        IN  ANY       ""

"""
test[20] = """;!BLAH
@         23                 IN  SOA         ( ns1.anathoth.net. ;Master NS
                                             matthewgrant5.gmail.com. ;RP email
                                             2011052603   ;Serial yyyymmddnn
                                             86400        ;Refresh
                                             3600         ;Retry
                                             604800       ;Expire
                                             600          ;Minimum/Ncache
                                             )    \n"""

test[21] = """esxi-bay11.c7000-2-b3           IN      A       172.16.15.33

; ==========================================================
; san infrastructure
; ==========================================================
spa.cx4-120                     IN      A       172.16.8.2
spb.cx4-120                     IN      A       172.16.8.3
;
cx4-120                         IN      A       172.16.8.2
                                IN      A       172.16.8.3
;
vnxe                            IN      A       172.16.8.4
nas.vnxe                        IN      A       172.16.1.2

"""

test[22] = """esxi-bay11.c7000-2-b3           IN      A       172.16.15.33

; ==========================================================
; san infrastructure
; ==========================================================
spa.cx4-120                     IN      A       172.16.8.2
spb.cx4-120                     IN      A       172.16.8.3

;
cx4-120                         IN      A       172.16.8.2
                                IN      A       172.16.8.3
;
vnxe                            IN      A       172.16.8.4
nas.vnxe                        IN      A       172.16.1.2

"""

test[23] = """esxi-bay11.c7000-2-b3           IN      A       172.16.15.33

; ==========================================================
; san infrastructure
; ==========================================================
spa.cx4-120                     IN      A       172.16.8.2
spb.cx4-120                     IN      A       172.16.8.3

;

cx4-120                         IN      A       172.16.8.2
                                IN      A       172.16.8.3
;

vnxe                            IN      A       172.16.8.4
nas.vnxe                        IN      A       172.16.1.2

"""
test[24] = """;
vnxe                            IN      A       172.16.8.4
"""
test[25] = """; -----------------------
; external mail relay servers    
; -----------------------
emr.mail                IN      A       210.5.49.130

; -----------------------
; directory services
; -----------------------
; load balancing address
ldap.dir                IN 300  A       210.5.49.18
                        IN 300  A       210.5.49.19
; offical server names
master.dir              IN 300  A       210.5.49.18
replica.dir             IN 300  A       210.5.49.19

; -----------------------
; isx manager
; -----------------------
manager                 IN      A       210.5.49.2
"""
test[26] = """; -----------------------
; external mail relay servers    
; -----------------------
emr.mail                IN      A       210.5.49.130

; -----------------------
; directory services
; -----------------------
; load balancing address
ldap.dir                300  IN A       210.5.49.18
                        300  IN A       210.5.49.19
; offical server names
master.dir              300  IN A       210.5.49.18
replica.dir             300  IN A       210.5.49.19

; -----------------------
; isx manager
; -----------------------
manager                 IN      A       210.5.49.2
"""

test[28] = """$TTL 24h;
; BIND version named 8.2.2-P5 Fri Mar 17 00:16:04 NZDT 2000
; BIND version root@isx-1.foo.bar.net.nz:/root/bind.8.2.2-P5/src/bin/named
; zone 'foo.bar-test21332.co.nz'   first transfer
; from 210.55.4.13:53 (local 210.55.4.10) using AXFR at Sun Dec 24 00:45:45 2000
$ORIGIN co.nz.
foo.bar-test21332 3600    IN      SOA     drs.registerdirect.net.nz. hostmaster.registerdirect.net.nz. (
                2000122401 3600 900 604800 3600 )
        3600    IN      NS      ns1.blah.net.NZ.
        3600    IN      NS      ns2.blah.net.NZ.
        3600    IN      A       210.55.4.14
        3600    IN      MX      10 mta.blah.net.NZ.
$ORIGIN foo.bar-test21332.CO.NZ.
www     3600    IN      CNAME   foo.bar-test21332.CO.NZ.

$INCLUDE /etc/passwd

$INCLUDE /etc/passwd thing.thing.

$GENERATE blah blah blah

$UPDATE_TYPE OxyPoxyBANG12
"""

test[29] = """internal.anathoth.net. IN DS 18174 7 2 C42492DB9DEF5CA9403D26F175247DFE86D913DA4BEDFC7D629F5E57 D6669FEB
"""

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
Implements a named.conf/bind configuration file parsing grammar

Algorithm from example PyParsing Grammar by Seo Sanghyeon:

http://pyparsing.wikispaces.com/WhosUsingPyparsing#BIND_named_conf

"""
from pyparsing import Forward
from pyparsing import Empty
from pyparsing import Word
from pyparsing import alphanums
from pyparsing import quotedString
from pyparsing import Group
from pyparsing import ZeroOrMore
from pyparsing import Optional
from pyparsing import OneOrMore
from pyparsing import cStyleComment
from pyparsing import restOfLine
from pyparsing import LineEnd
from pyparsing import Literal
from pyparsing import Suppress

# named.conf parser
key_toplevel = Forward()
value = Word(alphanums + "-_.:*!/") | quotedString
semi_colon = Suppress(Literal(';'))
o_curly = Suppress(Literal('{'))
c_curly = Suppress(Literal('}'))
simple = Group(value + ZeroOrMore(value) + semi_colon)
statement = Group(value + ZeroOrMore(value) + o_curly + Optional(key_toplevel) + c_curly + semi_colon)
key_toplevel << OneOrMore(simple | statement)
 
key_parser = key_toplevel
key_parser.ignore(cStyleComment)
key_parser.ignore(Empty() + LineEnd())
key_parser.ignore("#" + restOfLine + LineEnd())
key_parser.ignore("//" + restOfLine + LineEnd())

def get_keys(file_name):

    result = {}
    key_file = open(file_name).read()
    tokens = key_parser.parseString(key_file)
    for statement in list(tokens):
        if (statement[0] != 'key'):
            continue
        key_name = statement[1].strip('"')
        result[key_name] = {}
        for item in statement[2:]:
            if (item[0] == 'algorithm'):
                result[key_name]['algorithm'] = item[1]
            if (item[0] == 'secret'):
                result[key_name]['secret'] = item[1].strip('"')
    return result


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
Template cache module
"""

_cache = {}

def read_template(filename):
    """
    Reads in a configuration template, and stores it.
    """
    template = _cache.get(filename)
    if template:
        return template
    template_file = open(filename)
    template = template_file.readlines()
    template_file.close()
    template = ''.join(template)
    _cache[filename] = template
    return template

def clear_template_cache():
    """
    Clear the template cache by emptying it!
    """
    global _cache
    # Simple as and brutal
    _cache = {}



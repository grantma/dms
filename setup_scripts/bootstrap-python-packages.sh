#!/bin/sh
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

# Blow up on any errors
set -e

PYTHON_VERSION=`python3 -V | perl -pe 's/^\S+\s+([0-9]+\.[0-9]+)\.[0-9]+$/\1/'`
OS=`uname`
[ "$OS" = "Linux" ] && LINUX_DIST=`cat /etc/issue | cut -d ' ' -f 1`
if [ "$OS" = "FreeBSD" ]; then
	PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_VERSION}/site-packages"
elif [ "$OS" = "Linux" -a "$LINUX_DIST" = "Debian" ]; then
	PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_VERSION}/dist-packages"
elif [ "$OS" = "Linux" -a "$LINUX_DIST" = "Ubuntu" ]; then
	PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_VERSION}/dist-packages"
elif [ "$OS" = "Linux" -a "$LINUX_DIST" = "CentOS" ]; then
	PYTHON_SITE_PACKAGES="/usr/lib/python${PYTHON_VERSION}/dist-packages"
elif [ "$OS" = "Linux" -a "$LINUX_DIST" = "Redhat" ]; then
	PYTHON_SITE_PACKAGES="/usr/lib/python${PYTHON_VERSION}/dist-packages"
else
	# Hopefully everything else is like this
	PYTHON_SITE_PACKAGES="/usr/local/lib/python${PYTHON_VERSION}/dist-packages"
fi

PIP3_BIN="pip3"
PIP3_ARGS="--compile --target $PYTHON_SITE_PACKAGES"
PIP3_INSTALL="$PIP3_BIN install $PIP3_ARGS"
PYTHON_GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"
PYTHON_MODULE_TEST='pip3 show'

qt () { "$@" >/dev/null 2>&1 ; }

clean_site_packages () {
	(cd  $PYTHON_SITE_PACKAGES; rm -rf `ls -1 | grep -v 'README'`)
}

install_if_not_there () {
	for P in "$@"; do
		if ! qt $PYTHON_MODULE_TEST $P; then
			$PIP3_INSTALL $P;
		fi
	done
}

install_python_pip3 () {
	local SCRATCH="scratch-$$"

	if qt type pip3 ; then
		# Later python 3s come with pip and setuptools as part
		# of standard distribution
		install_if_not_there setuptools wheel
		return 0
	fi
	
	mkdir $SCRATCH
	(cd $SCRATCH && curl -O "$PYTHON_GET_PIP_URL")
	(cd $SCRATCH && "python${PYTHON_VERSION}" get-pip.py)
	if [ -f /usr/local/bin/pip ]; then
		mv /usr/local/bin/pip /usr/local/bin/pip3
	fi
	rm -rf $SCRATCH
}


install_python_sqlalchemy () {
	install_if_not_there psycopg2 sqlalchemy
	#install_if_not_there py-postgresql sqlalchemy
}

install_python_setproctitle () {
	install_if_not_there setproctitle
}

install_python_winpdb () {
	install_if_not_there winpdb
}

install_python_pyparsing () {
	install_if_not_there pyparsing
}

install_python_psutil () {
	install_if_not_there psutil
}

install_python_dnspython () {
	install_if_not_there dnspython
}

install_magcode_core () {
	install_if_not_there magcode-core
}

clean_site_packages
install_python_pip3
install_python_sqlalchemy
install_python_setproctitle
install_python_winpdb
install_python_pyparsing
install_python_dnspython
install_python_psutil
install_magcode_core


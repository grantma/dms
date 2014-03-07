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

PYTHON_VERSION=3.3
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
PYTHON_SETUPTOOLS_VERSION="1.4.1"
PYTHON_SETUPTOOLS_NAME="setuptools-${PYTHON_SETUPTOOLS_VERSION}"
PYTHON_SETUPTOOLS_TARGZ="${PYTHON_SETUPTOOLS_NAME}.tar.gz"
PYTHON_SETUPTOOLS_URL="https://pypi.python.org/packages/source/s/setuptools/${PYTHON_SETUPTOOLS_TARGZ}"

clean_site_packages () {
	(cd  $PYTHON_SITE_PACKAGES; rm -rf `ls -1 | grep -v 'README'`)
}

install_python_setuptools () {
	local SCRATCH="scratch-$$"
	mkdir $SCRATCH
	(cd $SCRATCH && curl -O "$PYTHON_SETUPTOOLS_URL" && tar xzf $PYTHON_SETUPTOOLS_TARGZ)
	(cd $SCRATCH/$PYTHON_SETUPTOOLS_NAME && "python${PYTHON_VERSION}" ./setup.py install)
	rm -rf $SCRATCH
}


install_python_sqlalchemy () {
	easy_install-${PYTHON_VERSION} psycopg2 sqlalchemy
	#easy_install-${PYTHON_VERSION} py-postgresql sqlalchemy
}

install_python_setproctitle () {
	easy_install-${PYTHON_VERSION} setproctitle
}

install_python_winpdb () {
	easy_install-${PYTHON_VERSION} winpdb
}

install_python_pyparsing () {
	easy_install-${PYTHON_VERSION} pyparsing
}

install_python_psutil () {
	easy_install-${PYTHON_VERSION} psutil
}

install_python_dnspython3 () {
	easy_install-${PYTHON_VERSION} dnspython3

}

install_magcode_core () {
	easy_install-${PYTHON_VERSION} magcode-core
}

clean_site_packages
install_python_setuptools
install_python_sqlalchemy
install_python_setproctitle
install_python_winpdb
install_python_pyparsing
install_python_dnspython3
install_python_psutil
install_magcode_core


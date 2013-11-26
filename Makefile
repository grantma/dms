#!/usr/bin/env make
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
DESTDIR =

#
# Installation Makefile for DMS
#
# This is rough! FIXME!

OSNAME := $(shell uname -s)
ETCDIR := /etc
DAEMONUSER := dmsdmd
DAEMONGROUP := dmsdmd
DMSGROUP := dms
CONFSUBDIRS :=  master-config-templates config-templates server-config-templates \
	server-admin-config
CONFFILES = dms.conf rsync-dnsconf-password rsync-dnssec-password pgpassfile \
	    dr-settings.sh
MASTERINCFILES = master-server-acl.conf master-config.conf
WSGISCRIPTS = admin_dms.wsgi helpdesk_dms.wsgi value_reseller_dms.wsgi \
	      hosted_dms.wsgi
LISTZONEWSGISCRIPTS = list_zone.wsgi
ifeq ($(OSNAME), Linux)
	PREFIX=/usr/local
	CONFDIR=$(DESTDIR)$(ETCDIR)/dms
	SYSCTLDIR=$(DESTDIR)$(ETCDIR)/sysctl.d
	NAMEDCONFDIR=$(DESTDIR)$(ETCDIR)/bind/master-config
	NAMEDSERVERCONFDIR=$(DESTDIR)$(ETCDIR)/bind/rsync-config
	NAMEDDATADIR=$(DESTDIR)/var/lib/bind
	NAMEDDYNAMICDIR=$(DESTDIR)/var/lib/bind/dynamic
	NAMEDKEYDIR=$(DESTDIR)/var/lib/bind/keys
	NAMEDSLAVEDIR=$(DESTDIR)/var/cache/bind/slave
	NAMEDSLAVELNDATA=../../cache/bind/slave
	NAMEDSLAVELN=$(DESTDIR)/var/lib/bind/slave
	NAMEDMASTERLNDATA=/etc/bind/master
	NAMEDMASTERLN=$(DESTDIR)/var/lib/bind/master
	NAMEDMASTERDIR=$(DESTDIR)$(ETCDIR)/bind/master
	VARCONFDIR=$(DESTDIR)/var/lib/dms
	LOGDIR=$(DESTDIR)/var/log/dms
	RUNDIR=$(DESTDIR)/run/dms
	BACKUPDIR=$(DESTDIR)/var/backups
	PYTHON_INTERPRETER ?= /usr/bin/python3
	PYTHON_SETUP_OPTS = --install-layout=deb
	PGUSER=postgres
	PGGROUP=postgres
else ifeq ($(OSNAME), FreeBSD)
	PREFIX = /usr/local
	CONFDIR = $(DESTDIR)$(PREFIX)$(ETCDIR)/dms
	NAMEDCONFDIR=$(DESTDIR)$(ETCDIR)/namedb/master-config
	NAMEDSERVERCONFDIR=$(DESTDIR)$(ETCDIR)/namedb/rsync-config
	NAMEDDYNAMICDIR=$(DESTDIR)$(ETCDIR)/namedb/dynamic
	NAMEDKEYDIR=$(DESTDIR)$(ETCDIR)/namedb/keys
	VARCONFDIR = $(DESTDIR)/var/lib/dms
	LOGDIR = $(DESTDIR)/var/log/dms
	RUNDIR = $(DESTDIR)/var/run/dms
	PYTHON_INTERPRETER ?= $(PREFIX)/bin/python3.2
	PYTHON_SETUP_OPTS =
	PGUSER=pgsql
	PGGROUP=pgsql
else
	PREFIX = /usr/local
	CONFDIR = $(DESTDIR)$(PREFIX)/dms$(ETCDIR)
	NAMEDCONFDIR=$(DESTDIR)$(PREFIX)/namedb$(ETCDIR)/master-config
	NAMEDSERVERCONFDIR=$(DESTDIR)$(PREFIX)/namedb$(ETCDIR)/rsync-config
	NAMEDDYNAMICDIR=$(DESTDIR)$(PREFIX)/namedb$(ETCDIR)/dynamic
	NAMEDKEYDIR=$(DESTDIR)$(PREFIX)/namedb$(ETCDIR)/keys
	VARCONFDIR = $(DESTDIR)$(PREFIX)/dms/var
	LOGDIR = $(DESTDIR)$(PREFIX)/dms/log
	RUNDIR = $(DESTDIR)$(PREFIX)/dms/var
	PYTHON_INTERPRETER ?= $(PREFIX)/bin/python3.2
	PYTHON_SETUP_OPTS =
	PGUSER=pgsql
	PGGROUP=pgsql
endif
SHAREDIR = $(DESTDIR)$(PREFIX)/share/dms
BINDIR = $(DESTDIR)$(PREFIX)/bin
SBINDIR = $(DESTDIR)$(PREFIX)/sbin
MANDIR = $(DESTDIR)$(PREFIX)/man
INSTALL = /usr/bin/install

.PHONY: install install-dir install-conf install-python install-bin \
	install-wsgi clean clean-python build-python

all: build-python

install: install-conf install-bin install-wsgi

install-dir:
	- $(INSTALL) -d $(BINDIR)
	- $(INSTALL) -d $(SBINDIR)
	- $(INSTALL) -d $(MANDIR)
	- $(INSTALL) -d $(CONFDIR)
	- $(INSTALL) -d $(NAMEDCONFDIR)
	- $(INSTALL) -d $(NAMEDSERVERCONFDIR)
	- $(INSTALL) -d $(NAMEDDYNAMICDIR)
	- $(INSTALL) -d $(NAMEDKEYDIR)
	- $(INSTALL) -d $(VARCONFDIR)/dms-sg
	- $(INSTALL) -d $(LOGDIR)
	- $(INSTALL) -d $(RUNDIR)
	- $(INSTALL) -d $(SHAREDIR)
	- $(INSTALL) -d $(SHAREDIR)/dr_scripts
	- $(INSTALL) -d $(SHAREDIR)/setup_scripts
	- $(INSTALL) -d $(SHAREDIR)/postgresql
	- $(INSTALL) -d $(VARCONFDIR)/postgresql
ifeq ($(OSNAME), Linux)
	- $(INSTALL) -d $(SYSCTLDIR)
	- $(INSTALL) -d $(BACKUPDIR)
endif
ifndef DMS_DEB_BUILD
	chown $(DAEMONUSER):bind $(NAMEDCONFDIR)
	chmod 2755 $(NAMEDCONFDIR)
	chown bind:bind $(NAMEDSERVERCONFDIR)
	chmod 755 $(NAMEDSERVERCONFDIR)
	chown bind:$(DAEMONGROUP) $(NAMEDDYNAMICDIR)
	chmod 2775 $(NAMEDDYNAMICDIR)
	chown bind:$(DAEMONGROUP) $(NAMEDKEYDIR)
	chmod 2775 $(NAMEDKEYDIR)
	chown $(DAEMONUSER):$(DAEMONGROUP) $(VARCONFDIR)/dms-sg
	chown $(DAEMONUSER):$(DAEMONGROUP) $(LOGDIR)
	chown $(DAEMONUSER):$(DAEMONGROUP) $(RUNDIR)
endif
ifeq ($(OSNAME), Linux)
	- $(INSTALL) -d $(NAMEDMASTERDIR)
	- $(INSTALL) -d $(NAMEDSLAVEDIR)
ifndef DMS_DEB_BUILD
	chown root:bind $(NAMEDSLAVEDIR)
	chmod 775 $(NAMEDSLAVEDIR)
endif
	- ln -snf $(NAMEDSLAVELNDATA) $(NAMEDSLAVELN)
	- ln -snf $(NAMEDMASTERLNDATA) $(NAMEDMASTERLN)
endif

install-conf: install-dir
	for f in $(CONFFILES); do \
		if [ ! -f $(CONFDIR)/$${f}.sample ]; then \
			$(INSTALL) -m 644 \
				etc/$${f}.sample $(CONFDIR)/$${f}.sample; \
		fi; \
		if [ ! -f $(CONFDIR)/$$f ]; then \
			$(INSTALL) -m 644 \
				etc/$${f}.sample $(CONFDIR)/$$f; \
		fi; \
	done
ifndef DMS_DEB_BUILD
	for f in $(CONFFILES); do \
		chmod 640 $(CONFDIR)/$$f; \
	done
	chown root:$(DMSGROUP) $(CONFDIR)/dms.conf
	chmod 640 $(CONFDIR)/dms.conf
	chown root:$(DAEMONGROUP) $(CONFDIR)/rsync-dnsconf-password
	chmod 640 $(CONFDIR)/rsync-dnsconf-password
	chown root:$(DAEMONGROUP) $(CONFDIR)/rsync-dnssec-password
	chmod 640 $(CONFDIR)/rsync-dnssec-password
	chown $(PGUSER):$(PGGROUP) $(CONFDIR)/pgpassfile
	chmod 600 $(CONFDIR)/pgpassfile
	chmod 644 $(CONFDIR)/dr-settings.sh
endif
	for d in $(CONFSUBDIRS); do \
		if [ ! -e $(CONFDIR)/$$d ]; then \
			cp -R etc/$${d} $(CONFDIR); \
		fi; \
	done
	for f in $(MASTERINCFILES); do \
		touch $(NAMEDCONFDIR)/$$f; \
	done
ifndef DMS_DEB_BUILD
	for f in $(MASTERINCFILES); do \
		chown $(DAEMONUSER):bind $(NAMEDCONFDIR)/$$f; \
	done
endif
ifeq ($(OSNAME), Linux)
	- $(INSTALL) -m 644 etc/debian/sysctl.d/30-dms-core-net.conf \
		$(SYSCTLDIR)
endif

install-wsgi: install-dir
	$(INSTALL) -d $(CONFDIR)/wsgi-scripts/list_zone; \
	$(INSTALL) -d $(CONFDIR)/wsgi-scripts/dms; \
	for f in $(WSGISCRIPTS); do \
		$(INSTALL) -m 644 wsgi-scripts/dms/$$f \
			$(CONFDIR)/wsgi-scripts/dms; \
	done; \
	for f in $(LISTZONEWSGISCRIPTS); do \
		$(INSTALL) -m 644 wsgi-scripts/list_zone/$$f \
			$(CONFDIR)/wsgi-scripts/list_zone; \
	done;

clean-python:
	- rm -rf build

build-python:
	@$(PYTHON_INTERPRETER) setup.py build

install-python: build-python install-dir
	# Allow python directory to be symlinked for development and debug
	if [ ! -e $(SHAREDIR) -o ! -L $(SHAREDIR) ]; then \
		$(PYTHON_INTERPRETER) setup.py install --install-pure=$(SHAREDIR) --install-scripts=$(SHAREDIR) $(PYTHON_SETUP_OPTS) ; \
	fi

install-bin: install-python
	- for P in dyndns_tool dmsdmd zone_tool; do \
		$(INSTALL) -m 755 $${P} $(SHAREDIR) \
			&& perl -pe 's~^#!/\S+/python3.[0-9]$$~#!$(PYTHON_INTERPRETER)~' -i $(SHAREDIR)/$${P}; \
 	done;
	- $(INSTALL) -m 755 dns-createzonekeys $(SHAREDIR)
	- $(INSTALL) -m 755 dns-recreateds $(SHAREDIR)
	- for S in dms_start_as_replica dms_promote_replica dms_master_down; do \
		$(INSTALL) -m 755 dr_scripts/$${S} $(SHAREDIR)/dr_scripts; \
	done;
	- $(INSTALL) -m 755 dr_scripts/etckeeper_git_shell $(SHAREDIR)/dr_scripts \
	 	&& perl -pe 's~^#!/\S+/python3.[0-9]\s+.*$$~#!$(PYTHON_INTERPRETER)~' -i $(SHAREDIR)/dr_scripts/etckeeper_git_shell
	- $(INSTALL) -m 644 postgresql/dms-schema-pg93.sql $(SHAREDIR)/postgresql
	- $(INSTALL) -m 644 postgresql/dms-init-pg93.sql $(SHAREDIR)/postgresql
ifeq ($(OSNAME), Linux)
	- $(INSTALL) -m 755 postgresql/dms_createdb $(SHAREDIR)/postgresql \
		&& perl -pe 's~^DBLIBDIR=.*$$~DBLIBDIR=$(PREFIX)/share/dms/postgresql~' -i $(SHAREDIR)/postgresql/dms_createdb
	- $(INSTALL) -m 755 postgresql/pg_dumpallgz $(SHAREDIR)/postgresql \
	 	&& perl -pe 's~^#!/\S+/python3.[0-9]\s+.*$$~#!$(PYTHON_INTERPRETER)~' -i $(SHAREDIR)/postgresql/pg_dumpallgz
	- $(INSTALL) -m 644 postgresql/pg_hba.conf $(SHAREDIR)/postgresql
	- $(INSTALL) -m 644 postgresql/pg_ident.conf $(SHAREDIR)/postgresql
	- $(INSTALL) -m 644 postgresql/postgresql.conf $(SHAREDIR)/postgresql
	- $(INSTALL) -m 644 postgresql/30-dms-core-shm.conf $(SYSCTLDIR)
endif
	ln -snf $(SHAREDIR)/dmsdmd $(SBINDIR)
	ln -snf $(SHAREDIR)/dyndns_tool $(SBINDIR)
	ln -snf $(SHAREDIR)/dns-createzonekeys $(SBINDIR)
	ln -snf $(SHAREDIR)/dns-recreateds $(SBINDIR)
	ln -snf $(SHAREDIR)/zone_tool $(BINDIR)
	ln -snf $(SHAREDIR)/zone_tool~rnano $(BINDIR)
	ln -snf $(SHAREDIR)/zone_tool~rvim $(BINDIR)
	ln -snf $(SHAREDIR)/dr_scripts/etckeeper_git_shell $(SBINDIR)
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_basebackup
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_promote_replica
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_prepare_binddata
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_master_down
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_master_up
	ln -snf $(SHAREDIR)/dr_scripts/dms_start_as_replica $(SBINDIR)/dms_update_wsgi_dns
ifeq ($(OSNAME), Linux)
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_createdb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_admindb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_dropdb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_dumpdb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_sqldb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_pg_basebackup
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_write_recovery_conf
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_replicadb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_promotedb
	ln -snf $(SHAREDIR)/postgresql/dms_createdb $(SBINDIR)/dms_move_xlog
	ln -snf $(SHAREDIR)/postgresql/pg_dumpallgz $(SBINDIR)/pg_dumpallgz
endif

clean: clean-python


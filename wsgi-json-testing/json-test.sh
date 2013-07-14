#!/bin/bash
time curl -X POST -H 'Content-Type: application/json' --data-binary "@${1}.jsonrpc" http://admin-dms:admin-dms@localhost/admin_dms

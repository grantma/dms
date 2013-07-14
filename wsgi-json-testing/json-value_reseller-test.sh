#!/bin/bash
time curl -X POST -H 'Content-Type: application/json' -d "@testing/${1}.jsonrpc" http://value-reseller-dms:value-reseller@dmsi.foo.bar.net/value_reseller_dms

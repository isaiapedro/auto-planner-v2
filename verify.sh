#!/usr/bin/env sh
set -eu

verify_cache=/tmp/pios-planner-pycache
PYTHONPYCACHEPREFIX="$verify_cache" python3 -m compileall -q tools/api
PYTHONPATH=tools/api python3 -m unittest discover -s tools/api/tests
(cd mobile && npx tsc --noEmit)

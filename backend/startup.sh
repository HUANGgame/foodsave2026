#!/bin/sh
set -eu
# App Service Oryx activates the installed requirements environment before this.
# No pip/apt/install, migration, driver license acceptance or DB call at startup.
exec python -m uvicorn foodsave.api:app --host 0.0.0.0 --port 8000 --workers 1 --no-proxy-headers --limit-concurrency 16 --timeout-keep-alive 5

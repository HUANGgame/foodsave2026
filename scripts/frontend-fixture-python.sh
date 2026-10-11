#!/usr/bin/env bash
set -euo pipefail

log="${FOODSAVE_FIXTURE_LOG:?Fixture artifact log path is required}"
exec >>"$log" 2>&1
printf '\n=== loopback demo fixture launch ===\n'
if [ "$#" -ne 1 ] || [ "$1" != "backend/qa/demo_prize_fixture.py" ]; then
  echo 'Refusing a command other than the approved loopback fixture'
  exit 64
fi
python="${FOODSAVE_FIXTURE_PYTHON:?Isolated fixture interpreter is required}"
store="${FOODSAVE_DEMO_PRIZE_STORE:?Temporary demo store is required}"
test -x "$python"
test "${FOODSAVE_QA_LOOPBACK_ONLY:-}" = true
test "${FOODSAVE_DEMO_PRIZES_ENABLED:-}" = true
case "$store" in
  */foodsave-demo-qa-*/demo-prizes.json) ;;
  *) echo 'Refusing a store outside the synthetic fixture directory'; exit 64 ;;
esac
test -d "${store%/*}"
test ! -L "${store%/*}"
printf 'Interpreter: %s\nFixture: backend/qa/demo_prize_fixture.py\n' "$python"
# exec preserves the PID so Playwright's existing afterAll server.kill() cleans up.
# A clean environment prevents inherited credentials and service settings reaching the fixture.
exec env -i PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONUNBUFFERED=1 \
  PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend \
  FOODSAVE_QA_LOOPBACK_ONLY=true FOODSAVE_DEMO_PRIZES_ENABLED=true \
  FOODSAVE_DEMO_PRIZE_STORE="$store" "$python" "$@"

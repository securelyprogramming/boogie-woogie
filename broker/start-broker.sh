#!/bin/sh
set -eu
# No bind or certificate generation occurs until this script is explicitly run.
# Pass --bind with the Mac's LAN IPv4 address for physical-device testing.
exec python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/broker.py" "$@"

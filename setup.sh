#!/bin/sh
set -eu
umask 077
exec python3 "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/broker/bootstrap.py" "$@"

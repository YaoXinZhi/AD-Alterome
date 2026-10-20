#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3 is required. Install it and try again; no pip packages are needed.' >&2
    exit 1
fi
exec python3 server.py "$@"

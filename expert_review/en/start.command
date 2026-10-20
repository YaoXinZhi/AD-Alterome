#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3 is required. Install it from https://www.python.org/ and double-click this file again.'
    printf '%s' 'Press Enter to close... '
    read -r _review_reply
    exit 1
fi
python3 server.py "$@"
_review_status=$?
if [ "$_review_status" -ne 0 ]; then
    printf '%s' 'Startup failed. Review the error above and press Enter to close... '
    read -r _review_reply
fi
exit "$_review_status"

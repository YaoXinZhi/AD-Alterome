#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '需要 Python 3。请安装 Python 3 后重新运行；无需安装任何 pip 依赖。' >&2
    exit 1
fi
exec python3 server.py "$@"

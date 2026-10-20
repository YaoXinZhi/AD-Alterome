#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' '需要 Python 3。请先从 https://www.python.org/ 安装 Python 3，再重新双击此文件。'
    printf '%s' '按回车退出… '
    read -r _review_reply
    exit 1
fi
python3 server.py "$@"
_review_status=$?
if [ "$_review_status" -ne 0 ]; then
    printf '%s' '启动未完成，请查看上方错误。按回车退出… '
    read -r _review_reply
fi
exit "$_review_status"

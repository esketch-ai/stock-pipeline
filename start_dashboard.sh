#!/bin/zsh
# 대시보드 실행 스크립트
#   ./start_dashboard.sh            # 포트 8787
#   PORT=9000 ./start_dashboard.sh  # 포트 변경

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR" || exit 1

if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
else
    echo "venv 없음: $PROJECT_DIR/venv" >&2
    exit 1
fi

exec "$PROJECT_DIR/venv/bin/python3" "$PROJECT_DIR/dashboard.py"
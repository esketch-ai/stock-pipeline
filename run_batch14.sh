#!/bin/zsh
# 14개 전 종목 7분 4K 풀버전 제작 및 유튜브 업로드 일괄 실행 스크립트
#
# 잠자기 방지 caffeinate 로 구동되어 맥북 덮개를 닫거나 절전 모드 진입을 방지합니다.

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="$(eval echo ~$(whoami))"

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR" || exit 1

if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
else
    echo "venv 없음: $PROJECT_DIR/venv" >&2
    exit 1
fi

echo "=========================================================="
echo "🚀 14개 종목 7분 4K 영상 제작 및 유튜브 업로드 시작"
echo "=========================================================="

exec caffeinate -dimsu python3 tools/batch_14_pipeline.py "$@"

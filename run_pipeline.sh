#!/bin/zsh
# stock-pipeline launchd 실행 스크립트
#
# launchd 는 대화형 터미널과 달리 non-interactive/non-login 셸로 실행되므로
# PATH 와 가상환경을 여기서 명시적으로 주입해야 한다. (.zshrc 을 source 하지 않는다)

set -euo pipefail

# ── Apple Silicon Homebrew 및 시스템 PATH 강제 주입 ──
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# GUI 세션 환경 변수 상속 (launchd GUI 컨텍스트 보정)
export HOME="$(eval echo ~$(whoami))"

# 프로젝트 디렉터리 = 이 스크립트가 있는 위치 (이동해도 자동 추적)
PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR" || exit 1

# ── 가상환경 활성화 ──
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
else
    echo "venv 없음: $PROJECT_DIR/venv" >&2
    exit 1
fi

# ── 로그 회전 (7일 초과) ──
find "$PROJECT_DIR/logs" -name "*.log" -mtime +7 -delete 2>/dev/null || true

# ── 잠자기 방지 caffeinate 로 오케스트레이터 구동 ──
# 전원 어댑터 연결 + 덮개 닫힘 상태에서도 절전 방지
exec caffeinate -dimsu "$PROJECT_DIR/venv/bin/python3" "$PROJECT_DIR/main_orchestrator.py" "$@"
#!/bin/zsh
# ─────────────────────────────────────────────────────────────
# 🍎 맥미니 운영서버 원클릭 마이그레이션 & 자동화 구축 스크립트
# ─────────────────────────────────────────────────────────────
# 이 스크립트는 맥미니에서 stock-pipeline 을 완벽하게 가동하기 위해
# Homebrew, Python, Node/Remotion, Whisper Metal 모델, launchd 데몬 등록,
# 대시보드 상시 가동까지 한 번에 자동화합니다.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "🚀 맥미니 운영서버 환경 구축 및 마이그레이션을 시작합니다."
echo "   프로젝트 위치: $SCRIPT_DIR"
echo "   실행 사용자:   $USER ($HOME)"
echo "========================================================"

# ── 1. OS 및 Apple Silicon 확인 ──────────────────────────────
ARCH=$(uname -m)
OS=$(uname -s)

if [ "$OS" != "Darwin" ]; then
    echo "❌ macOS 가 아닙니다. ($OS)" >&2
    exit 1
fi

if [ "$ARCH" = "arm64" ]; then
    echo "✅ Apple Silicon (arm64) 감지: MLX Metal GPU 하드웨어 가속 지원"
else
    echo "⚠️ Intel x86_64 감지: MLX 가속 대신 CPU Whisper 폴백 모드로 동작합니다."
fi

# ── 2. Homebrew 및 시스템 도구 점검 ───────────────────────────
echo ""
echo "🔍 [1/7] 시스템 필수 도구 점검 중..."

if ! command -v brew >/dev/null 2>&1; then
    echo "⚠️ Homebrew 가 설치되어 있지 않습니다."
    echo "   다음 명령어로 Homebrew 를 먼저 설치하세요:"
    echo '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

MISSING_BREW=()
for tool in ffmpeg node git; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        MISSING_BREW+=("$tool")
    fi
done

if [ ${#MISSING_BREW[@]} -gt 0 ]; then
    echo "📦 필수 패키지 설치 중: ${MISSING_BREW[*]}..."
    brew install "${MISSING_BREW[@]}"
else
    echo "✅ 필수 시스템 도구 (ffmpeg, node, git) 설치 완료"
fi

if ! command -v gcloud >/dev/null 2>&1; then
    echo "💡 Google Cloud CLI (gcloud) 가 없습니다. Homebrew 로 설치합니다..."
    brew install --cask google-cloud-sdk || true
fi

# ── 3. 마이그레이션 팩 압축 해제 (.env, 토큰, DB) ──────────────
echo ""
echo "📦 [2/7] 마이그레이션 데이터 패키지 확인 중..."

if [ -f "macmini_migration_pack.tar.gz" ]; then
    echo "📂 macmini_migration_pack.tar.gz 감지 — 압축 해제 중..."
    tar -xzf macmini_migration_pack.tar.gz
    echo "✅ .env, state/(토큰), data/(종목 DB, 아카이브) 복원 완료"
fi

if [ ! -f ".env" ]; then
    echo "⚠️ .env 파일이 없습니다! .env.example 에서 기본 복사합니다."
    cp .env.example .env
    echo "❗ .env 파일에 API 키와 계정 정보를 확인/입력하세요."
else
    echo "✅ .env 환경설정 파일 확인 완료"
fi

# ── 4. Python 가상환경 및 의존성 설치 ─────────────────────────
echo ""
echo "🐍 [3/7] Python 가상환경(venv) 및 라이브러리 구축 중..."

if [ ! -d "venv" ]; then
    echo "   가상환경(venv) 생성 중 (python3)..."
    python3 -m venv venv
fi

echo "   pip 최신화 및 의존성 패키지 설치 중..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

if [ "$ARCH" = "arm64" ]; then
    echo "   Apple Silicon Metal 가속용 mlx-whisper 확인 중..."
    venv/bin/pip install mlx mlx-whisper -q || echo "⚠️ mlx-whisper 설치 건너뜀 (이미 설치됨 또는 폴백 사용)"
fi
echo "✅ Python 가상환경 준비 완료"

# ── 5. Remotion 렌더러 의존성 설치 ───────────────────────────
echo ""
echo "🎬 [4/7] Remotion 4K 비디오 렌더러 환경 구축 중..."

if [ -d "remotion" ]; then
    cd remotion
    npm install --silent
    cd ..
    echo "✅ Remotion npm 패키지 설치 완료"
fi

# ── 6. Whisper 고속 모델 사전 다운로드 (Prefetch) ─────────────
echo ""
echo "🎙️ [5/7] Whisper 음성 인식 모델 사전 다운로드 중..."

venv/bin/python setup_status.py --prefetch-whisper || true
echo "✅ 음성 모델 캐시 준비 완료"

# ── 7. macOS launchd 백그라운드 데몬 등록 ─────────────────────
echo ""
echo "⚙️ [6/7] macOS launchd 자동화 데몬 등록 중..."

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# 1) 대시보드 데몬 (부팅 시 자동 기동 + 상시 실행)
cat << EOF > "$LAUNCH_AGENTS_DIR/com.stockpipeline.dashboard.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpipeline.dashboard</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>$SCRIPT_DIR/start_dashboard.sh</string>
    </array>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/dashboard.out.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/dashboard.err.log</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

# 2) 매일 새벽 2시 자동 배치 데몬
cat << EOF > "$LAUNCH_AGENTS_DIR/com.stockpipeline.daily.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stockpipeline.daily</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>$SCRIPT_DIR/run_pipeline.sh</string>
    </array>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/launchd.err.log</string>
    <key>KeepAlive</key>
    <false/>
    <key>ThrottleInterval</key>
    <integer>300</integer>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

# 기존 서비스 해제 후 재등록
launchctl unload "$LAUNCH_AGENTS_DIR/com.stockpipeline.dashboard.plist" 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS_DIR/com.stockpipeline.daily.plist" 2>/dev/null || true

launchctl load -w "$LAUNCH_AGENTS_DIR/com.stockpipeline.dashboard.plist"
launchctl load -w "$LAUNCH_AGENTS_DIR/com.stockpipeline.daily.plist"

echo "✅ launchd 데몬 등록 완료:"
echo "   - 대시보드: 부팅 시 자동 시작 (포트 8787)"
echo "   - 일일 배치: 매일 새벽 02:00 자동 실행"

# ── 8. 통합 시스템 진단 및 셀프 테스트 ─────────────────────────
echo ""
echo "🩺 [7/7] 통합 시스템 셀프 헬스체크 실행..."

venv/bin/python setup_status.py || true

LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")

echo ""
echo "========================================================"
echo "🎉 맥미니 운영서버 셋업이 완벽하게 완료되었습니다!"
echo "========================================================"
echo "📊 관리자 대시보드 주소:"
echo "   - 맥미니 로컬: http://localhost:8787"
echo "   - 공유기/사내망: http://$LOCAL_IP:8787"
echo ""
echo "⏰ 자동화 스케줄:"
echo "   - 매일 새벽 02:00 전 종목 자동 스크리닝 & 4K 렌더 & 아카이브 & 업로드"
echo ""
echo "💡 추가 권장 설정 (맥미니 절전 방지):"
echo "   운영서버로 잠들지 않게 하려면 터미널에서 다음을 실행하세요:"
echo "   sudo pmset -a disablesleep 1"
echo "========================================================"

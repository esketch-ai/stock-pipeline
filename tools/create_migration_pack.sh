#!/bin/zsh
# ─────────────────────────────────────────────────────────────
# 맥미니 마이그레이션 팩 생성기 (현재 머신에서 실행)
# git에 없는 비밀키(.env), 인증 토큰, 종목 DB, 아카이브를 하나의 파일로 패키징
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
cd "$PROJECT_DIR"

OUTPUT_PACK="macmini_migration_pack.tar.gz"
echo "📦 맥미니 운영서버 마이그레이션 팩 생성 시작..."

# 포함할 대상 파일/폴더 목록
FILES_TO_PACK=(
    ".env"
    "contact.txt"
    "data/stock_analytics.db"
    "data/archive"
    "state"
)

# 실제 존재하는 파일들만 필터링
EXISTING_FILES=()
for f in "${FILES_TO_PACK[@]}"; do
    if [ -e "$f" ]; then
        EXISTING_FILES+=("$f")
        echo "  [포함] $f"
    else
        echo "  [건너뜀 (없음)] $f"
    fi
done

if [ ${#EXISTING_FILES[@]} -eq 0 ]; then
    echo "❌ 포함할 대상 파일이 없습니다." >&2
    exit 1
fi

tar -czf "$OUTPUT_PACK" "${EXISTING_FILES[@]}"
PACK_SIZE=$(du -h "$OUTPUT_PACK" | cut -f1)

echo "========================================================"
echo "✅ 마이그레이션 팩 생성 완료: $OUTPUT_PACK ($PACK_SIZE)"
echo "========================================================"
echo "다음 파일이 압축에 포함되었습니다:"
tar -tzf "$OUTPUT_PACK" | head -n 25
echo "..."
echo ""
echo "🚀 맥미니로 전송 방법 (택 1):"
echo " 1) AirDrop으로 '$OUTPUT_PACK' 파일을 맥미니로 전송"
echo " 2) scp 명령어 전송:"
echo "    scp $OUTPUT_PACK <맥미니유저>@<맥미니IP>:~/Downloads/"
echo "========================================================"

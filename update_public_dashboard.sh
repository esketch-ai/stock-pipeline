#!/bin/zsh
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
ROOT="${0:A:h}"
cd "$ROOT"
"$ROOT/venv/bin/python3" pages_export.py
# 배포 전용 저장소에는 공개용 파일만 복사한다.
REPO="$ROOT/pages-deploy"
if [[ -d "$REPO/.git" ]]; then
  cp public-dashboard/index.html public-dashboard/app.js public-dashboard/style.css public-dashboard/data.json public-dashboard/.nojekyll "$REPO/"
  git -C "$REPO" add index.html app.js style.css data.json .nojekyll
  if ! git -C "$REPO" diff --cached --quiet; then
    git -C "$REPO" commit -m "Update stock follow-up dashboard"
    git -C "$REPO" push origin main
  fi
fi

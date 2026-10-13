# 이식·설치 가이드

## 지원 기준

| 환경 | 상태 |
|---|---|
| macOS Apple Silicon / Python 3.12 | 기존 제작 운영 환경, 권장 |
| Linux x86_64/arm64 | MLX 설치 제외·CPU Whisper·소프트웨어 인코더 경로 준비. 전체 렌더 미검증 |
| Windows | zsh/launchd 및 심볼릭 링크 가정 때문에 네이티브 절차 미제공 |
| GitHub Pages만 | 정적 화면은 독립 실행 가능. 시세 생성기와 관리 API는 별도 머신 필요 |

## 1. 소스 전달

기존 머신에서:

```bash
python3 tools/portable.py bundle
```

`dist/stock-pipeline-source.tar.gz`, `.tar.gz.sha256`를 대상 머신에 전달합니다. 압축 안 `SOURCE_SHA256.json`에는 파일별 체크섬이 있습니다.

대상 머신의 원하는 작업 폴더에서:

```bash
shasum -a 256 -c stock-pipeline-source.tar.gz.sha256
tar -xzf stock-pipeline-source.tar.gz
cd stock-pipeline
```

macOS에서 백그라운드 작업을 사용할 경우 Documents/Desktop 아래는 TCC 접근 제한이 생길 수 있습니다. 백그라운드 접근이 가능한 디렉터리에 설치하고 필요하면 작업 폴더에 심볼릭 링크를 만드세요. 특정 사용자명이나 홈 바로 아래 설치를 전제로 하지 않습니다.

## 2. 런타임 설치

macOS 예시(Homebrew 설치 전제):

```bash
brew install python@3.12 node@22 ffmpeg git gh
export PATH="$(brew --prefix node@22)/bin:$PATH"
python3.12 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-tested.txt
cd remotion
npm ci
cd ..
python3 tools/portable.py prepare
```

`requirements-tested.txt`는 현재 직접 의존성 버전 스냅샷이며 전체 lock은 아닙니다. 해당 버전이 설치 불가하면 Python/OS 및 패키지 공급 여부를 먼저 확인하고 `requirements.txt`의 범위를 이용해 별도 환경에서 호환성을 검증합니다.

`prepare`는 `.env`가 없을 때만 예제를 복사하고, 런타임 폴더·상대 심볼릭 링크·`state/launchd/*.plist`를 생성합니다. 기존 데이터 폴더와 실제 자산 디렉터리를 삭제하지 않습니다. 생성된 launchd 파일은 자동 등록하지 않습니다.

Linux는 Python 3.12/venv, Node.js, FFmpeg, Chromium 런타임 라이브러리 및 한국어 Noto CJK 폰트를 설치합니다. 실행은 zsh 셸 래퍼 대신 `venv/bin/python` 직접 호출과 cron/systemd를 사용하세요. 새 OS에서 폰트와 Chromium 렌더 결과를 확인해야 합니다.

## 3. 인증 및 설정

1. `.env`에 KRX 계정과 LLM/TTS 공급자 키를 입력합니다. 예제 모델명이 대상 계정에서 제공되는지 확인합니다.
2. Google TTS 사용 시 Google Cloud CLI를 설치하고 `gcloud auth login`, `gcloud config set project YOUR_PROJECT`를 실행합니다. Text-to-Speech API·결제·권한을 설정하고 `GOOGLE_TTS_PROJECT`를 채웁니다.
3. YouTube 사용 시 `.env`의 대상 OAuth 클라이언트·채널을 설정하고 `venv/bin/python token_auth.py`로 새 머신에서 인증합니다.
4. `venv/bin/python setup_status.py --prefetch-whisper`로 모델을 미리 받습니다. 공급자 설정과 캐시 상태는 `setup_status.py`에서 확인합니다.

가상환경·node_modules·gcloud/gh 인증 캐시는 복사해서 재사용하지 말고 새 환경에서 설치·로그인하세요.

## 기존 데이터 이전

원본 배치를 중지한 상태에서 다음을 별도 비공개 백업/복사합니다.

| 대상 | 필요한 이유 |
|---|---|
| `data/` | 실행 이력·대본·manifest·props |
| `state/price_tracking.json` | 최초 기준가·후속 시세를 이어서 추적 |
| 나머지 `state/` | 쿨다운·실행 상태. 토큰 파일은 별도 인증 정책에 따라 처리 |
| `cache/` | 과거 음성·차트 재렌더 |
| `output/` | 기존 완성 영상 |

모델은 사용자 `~/.cache`에 있을 수 있으며 소스 패키지에 포함되지 않습니다. 복사하지 않아도 prefetch로 다시 준비할 수 있습니다.

JSON 내부 절대 경로를 새 위치에 맞춥니다:

```bash
python3 tools/portable.py rebase --old-root /이전/프로젝트/stock-pipeline
# 출력 목록 확인 후
python3 tools/portable.py rebase --old-root /이전/프로젝트/stock-pipeline --apply
python3 tools/portable.py prepare
```

`data/**/*.json`의 해당 접두사로 시작하는 문자열만 수정하며 `.json.pre-migration` 백업을 남깁니다. `.env`의 절대 토큰 경로와 사용자별 외부 설정은 별도로 수정합니다. `rebase`는 영상·음원 자체를 복사하지 않습니다. 변경 전 원본 데이터를 보존하세요.

## 4. 검증 순서

```bash
venv/bin/python -m unittest test_campaign test_pages_export -v
venv/bin/python pages_export.py --offline
cd remotion
npx tsc --noEmit -p tsconfig.json
cd ..
venv/bin/python dashboard.py
```

브라우저에서 이력·대본·음원·영상 재생을 확인합니다. 그다음 새 터미널에서:

```bash
venv/bin/python main_orchestrator.py --no-publish --tickers 000650
```

API 비용과 다운로드가 발생할 수 있습니다. 생성물의 자막 타이밍·음성·차트·헤드라인을 확인한 뒤 게시를 사용합니다. `--dry-run`은 외부 API를 차단하는 옵션이 아닙니다.

## 5. GitHub Pages 이식

새 계정의 **정적 배포 전용 저장소**를 만듭니다. 전체 프로젝트를 공개 저장소에 넣을 필요가 없습니다.

```bash
gh auth login
venv/bin/python pages_export.py
mkdir pages-deploy
git -C pages-deploy init -b main
cp public-dashboard/index.html public-dashboard/app.js public-dashboard/style.css public-dashboard/data.json public-dashboard/.nojekyll pages-deploy/
git -C pages-deploy add .
git -C pages-deploy commit -m "Initial dashboard"
gh repo create OWNER/REPOSITORY --public --source=pages-deploy --remote=origin --push
gh api repos/OWNER/REPOSITORY/pages -X POST --input - <<'JSON'
{"source":{"branch":"main","path":"/"},"build_type":"legacy"}
JSON
```

기존 배포 저장소를 계속 운영한다면 생성 대신 `gh repo clone OWNER/REPOSITORY pages-deploy`를 사용합니다. `pages-deploy`가 없는 경우 갱신 스크립트는 로컬 JSON만 생성합니다. 이후 `zsh update_public_dashboard.sh`로 시세 조회와 푸시를 함께 수행합니다. Linux에서는 Python 생성 후 동일한 복사·Git 명령을 cron에 등록합니다.

## 6. macOS 일정 등록

저장소 루트의 과거 `com.stockpipeline.*.plist`는 기존 머신 경로가 들어 있습니다. **새로 생성한 `state/launchd` 파일만 사용하세요.**

```bash
mkdir -p "$HOME/Library/LaunchAgents"
cp state/launchd/com.stockpipeline.pages.plist "$HOME/Library/LaunchAgents/"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.stockpipeline.pages.plist"
launchctl print "gui/$(id -u)/com.stockpipeline.pages"
```

관리 서버는 `dashboard`, 제작은 `daily`로 같은 절차를 적용합니다. 같은 label이 이미 등록돼 있으면 기존 항목을 `launchctl bootout gui/$(id -u)/com.stockpipeline.pages`로 내린 후 등록합니다. 이식 동안 두 머신이 같은 배포 저장소에 동시에 푸시하지 않도록 기존 스케줄을 중지합니다.

제작 스케줄은 기본적으로 게시가 가능한 전체 실행입니다. 게시 없는 일일 제작을 원하면 생성된 daily plist의 `ProgramArguments` 끝에 `--no-publish`를 추가한 후 등록합니다. Homebrew keg-only Node 경로 등은 실행 래퍼의 PATH에 맞게 연결하거나 추가하세요.

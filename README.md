# Stock Pipeline

한국 주식 데이터로 분석 대본·음성·자막·SVG 차트를 만들고, Remotion으로 영상을 제작하는 프로젝트입니다. 로컬 관리자 대시보드와 GitHub Pages 가격 추적 대시보드를 제공합니다.

**문서 기준: 2026-10-13 / 권장 운영 환경: macOS Apple Silicon, Python 3.12, Node.js 22 LTS, FFmpeg.** Linux는 CPU Whisper/소프트웨어 인코딩 경로가 있으나 전체 제작은 검증되지 않았습니다. Windows 네이티브 실행은 지원 확인 전입니다.

**설치와 첫 실행은 [INSTALL.md](INSTALL.md) 를 보세요.**

## 처음 사용할 때

1. [이식·설치 가이드](docs/MIGRATION.md)에 따라 새 폴더에서 가상환경을 만듭니다.
2. `.env.example`을 기반으로 KRX 및 사용할 LLM/TTS 인증을 설정합니다.
3. `python3 tools/portable.py prepare`로 자산 링크·새 경로용 launchd 파일을 생성합니다.
4. `venv/bin/python3 main_orchestrator.py --no-publish --tickers 000650`으로 게시 없이 제작합니다.
5. `venv/bin/python3 dashboard.py` → http://127.0.0.1:8787

`--dry-run`도 LLM/TTS 호출을 할 수 있습니다. 무과금 오프라인 검사는 아래 테스트를 사용합니다.

```bash
venv/bin/python3 -m unittest discover -s . -p 'test_*.py'
cd remotion
npx tsc --noEmit -p tsconfig.json
```

## 문서 목록

| 문서 | 내용 |
|---|---|
| [기술 설계](docs/ARCHITECTURE.md) | 전체 흐름, 모듈 책임, 데이터 계약, 대시보드 API |
| [설정 명세](docs/CONFIGURATION.md) | 인증, 모델, 음성, CTA, 렌더·게시 설정 |
| [이식·설치](docs/MIGRATION.md) | 신규 설치, 기존 데이터 이동, Pages 재연결, 일정 등록 |
| [운영 매뉴얼](docs/OPERATIONS.md) | 일상 실행, 로그, 백업, 장애 복구 |
| [작업 내역·검증 상태](docs/STATUS.md) | 구현 기능, 확인 범위, 알려진 제약과 후속 작업 |
| [마케팅 시나리오](docs/lead-video-scenario.md) | 시청 유지 → 자료 신청 설계 |
| [Pages 가격 추적](docs/github-pages-dashboard.md) | 기준가격, 최신 종가, D+N, 공개 데이터 범위 |

`README_SETUP.md`는 초기 장비의 과거 작업 기록입니다. 현재 설치 방법·지원 상태는 이 README와 `docs/`를 기준으로 합니다.

## 이식용 소스 패키지

```bash
python3 tools/portable.py bundle
```

`dist/stock-pipeline-source.tar.gz` 및 SHA-256 파일을 생성합니다. 소스·문서·설정 예제만 들어갑니다. `.env`, 토큰, 모델, 가상환경, 영상, 아카이브 및 실제 가격 추적 데이터는 포함하지 않습니다. 기존 이력을 이어가려면 [데이터 이전 절차](docs/MIGRATION.md#기존-데이터-이전)를 함께 수행하세요.

## 현재 공개 대시보드

https://esketch-ai.github.io/stock-video-dashboard/

Pages는 조회용 정적 사이트입니다. 영상 제작·편집·게시 API는 로컬 FastAPI 서버에서 실행합니다. 다른 운영자로 이식할 때는 자신의 배포 저장소와 인증으로 연결합니다.

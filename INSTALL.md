# stock-pipeline

한국 주식 데이터로 분석 대본·음성·자막·SVG 차트를 만들고, Remotion으로 영상을 제작하는 파이프라인입니다.
관리자 대시보드와 GitHub Pages 가격 추적 대시보드를 함께 제공합니다.

**문서 기준: 2026-10-13 / 권장 환경: macOS Apple Silicon, Python 3.12, Node.js 22 LTS, FFmpeg.**
Linux는 CPU Whisper·소프트웨어 인코딩 경로가 있으나 전체 제작은 검증되지 않았습니다.

## 무엇을 만드나

| 단계 | 내용 |
|---|---|
| 1 | 종목 스크리닝 · 쿨다운 필터 (KRX, pykrx) |
| 2 | 종목별 대본 생성 + 4K 차트 (7구간 장편, 약 7분) |
| 3 | TTS + 로컬 단어 타임스탬프 (Apple Silicon Metal 가속) |
| 4 | Remotion 렌더링 (VideoToolbox 하드웨어 인코딩) |
| 5 | ffprobe 무결성 QC + YouTube 예약 발행 |

대본은 종목마다 다른 분석 관점(기업 가치 / 기대와 반증 / 위험 관리 / 데이터 검증 등)을 배정해
만들고, 같은 문장이 되풀이되거나 다른 종목과 겹치면 재생성한 뒤 TTS로 넘어갑니다.

## 빠른 시작

```bash
git clone <이 저장소>
cd stock-pipeline

brew install python@3.12 node@22 ffmpeg   # macOS
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env      # KRX 계정·LLM/TTS 키 입력
cd remotion && npm install && cd ..

venv/bin/python tools/portable.py prepare
venv/bin/python main_orchestrator.py --no-publish --tickers 000650
venv/bin/python dashboard.py      # → http://127.0.0.1:8787
```

자세한 설치·이식 절차는 [docs/MIGRATION.md](docs/MIGRATION.md)를 보세요.

## 대본 모델 선택

| 제공자 | 설정 | 특징 |
|---|---|---|
| OpenAI | `LLM_PROVIDER=openai` | 기본값. 품질이 가장 좋음 |
| 로컬 Ollama | `LLM_PROVIDER=ollama` | API 키 불필요. `OLLAMA_MODEL`로 지정 |

```bash
ollama pull qwen3:8b
LLM_PROVIDER=ollama venv/bin/python main_orchestrator.py --tickers 000650 --no-publish
```

`qwen3:8b`(5.2GB)는 빠르고 수치를 정확히 옮깁니다. `gpt-oss:20b`는 대본 생성에 수백 초가 걸리고
지시를 자주 어기므로 권하지 않습니다.

## 영상 파일명

`output/종목코드_종목명_생성일자(YYYYMMDD).mp4`

```
output/001210_금호전기_20261013.mp4
```

## 연락처 · 자료 안내

영상 하단과 마지막 카드에 표시할 제공자 정보는 `contact.txt` 에 적습니다.
이 파일은 `.gitignore` 대상이며 소스 번들에 포함되지 않습니다. 예시는 `contact.example.txt` 입니다.

```text
name: 제공자명
email: help@example.com
phone: 010-0000-0000
channel: 전화 문의
url: https://example.com/apply
offer: 제공 자료명
```

자료명과 주소가 모두 있어야 QR과 신청 유도 문장이 생성됩니다. 전화·이메일만 있으면
마지막 카드와 하단에 연락처만 표시됩니다.

## 무과금 검증

```bash
venv/bin/python -m unittest discover -s . -p 'test_*.py'
cd remotion && npx tsc --noEmit -p tsconfig.json
```

API를 호출하지 않는 검사만 포함되어 있습니다.

## 자주 쓰는 명령

```bash
# 지정 종목 제작, YouTube 게시 생략
venv/bin/python main_orchestrator.py --no-publish --tickers 000650,001210

# 대본 생성 없이 저장된 음성·자막으로 다시 렌더
venv/bin/python tools/render_local.py --tickers 000650

# 신규 종목 스크리닝 + 시나리오 설계만 (LLM 호출 없음)
venv/bin/python tools/plan_batch3.py

# 로컬 모델로 장편 샘플 다시 만들기 (대본 재사용)
venv/bin/python tools/render_sample3.py 000650 001210 084670

# 소스 번들 생성 (비밀·영상·데이터 제외)
venv/bin/python tools/portable.py bundle
```

## 문서

| 문서 | 내용 |
|---|---|
| [기술 설계](docs/ARCHITECTURE.md) | 전체 흐름, 모듈 책임, 데이터 계약 |
| [설정 명세](docs/CONFIGURATION.md) | 인증, 모델, 음성, CTA, 렌더·게시 설정 |
| [이식·설치](docs/MIGRATION.md) | 신규 설치, 기존 데이터 이동, 일정 등록 |
| [운영 매뉴얼](docs/OPERATIONS.md) | 일상 실행, 로그, 백업, 장애 복구 |
| [작업 내역·검증 상태](docs/STATUS.md) | 구현 기능, 확인 범위, 알려진 제약 |
| [대본 다양성 기준](docs/EDITORIAL_DIVERSITY.md) | 종목별 관점 배정과 반복 방지 규칙 |
| [시나리오 설계](docs/lead-video-scenario.md) | 자료 신청 구조와 설정 방법 |

## 라이선스와 제약

- 소스는 공개 저장소를 배포용이며, 영상·계정 정보·토큰은 포함되지 않습니다.
- 각 운영자가 자신의 KRX 계정, LLM/TTS 키, YouTube OAuth 토큰을 별도로 보유해야 합니다.
- 투자 권유를 하지 않는 분석 채널이며, 모든 대본은 실제 조회 데이터로만 작성됩니다.
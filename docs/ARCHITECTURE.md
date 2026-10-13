# 기술 설계

## 1. 시스템 경계

```text
KRX/pykrx → screening → facts → script_long / stage2_script
                                  ↓
                    script_gate / 한국어·수치 검증
                                  ↓
                 TTS → Whisper → caption_align / cues
                                  ↓
              OHLCV series + scenes + contact + timestamps
                                  ↓
                   stage4_render → Remotion → MP4
                                  ↓
                       QC → 선택적 YouTube 게시
                                  ↓
                  archive ← 로컬 관리자 대시보드
                     ↓
            pages_export + state/price_tracking.json
                     ↓
       public-dashboard → pages-deploy Git → GitHub Pages
```

외부 연동: KRX 계정, 선택한 LLM/TTS API, Google Cloud CLI 인증, 선택적 YouTube OAuth 및 GitHub CLI 인증. 영상 제작과 가격 추적은 별도 프로세스입니다. Pages 시세 갱신은 현재 로컬 launchd 스케줄러가 수행합니다.

## 2. 모듈 책임

| 파일/폴더 | 책임 |
|---|---|
| `config.py`, `logger.py` | 프로젝트 기준 경로, 환경 로딩, 파일 로그 |
| `main_orchestrator.py` | 단계 실행·상태 저장·모드 분기·아카이브 |
| `screening.py` | KRX 조회, 후보 점수, 휴장 대응, 거래량 0 제외, 지정 종목 조회 |
| `facts.py` | 차트용 가격 이력 및 대본에 공급할 확인된 수치 |
| `stage2_script.py` | 단편 대본, LLM별 HTTP 호출, 차트 생성 |
| `script_long.py`, `investors.py` | 7개 섹션 장편, 투자자 인용·폴백, 최종 다듬기 |
| `stage2_long.py` | 장편 생성·검증·TTS 청크 병합·manifest 구성 |
| `script_gate.py`, `script_quality.py` | 대본 게이트·품질 검사 |
| `numeric_verify.py`, `korean_lint.py`, `josa_rules.py`, `text_polish.py`, `llm_proofread.py` | 수치·한국어·조사 교정 |
| `stage3_audio.py`, `gcloud_tts.py`, `tts_numbers.py` | 공급자별 합성, 숫자 발음 처리, Whisper 폴백 |
| `whisper_improved.py`, `caption_align.py` | 전사·단어 타이밍 정렬 관련 구현 |
| `chart_data.py`, `charts_extended.py` | OHLCV 직렬화·수급·스윙 가격 후보 및 PNG 차트 |
| `scene_data.py`, `cues.py` | 섹션 타이밍, 헤드라인·통계, 차트 강조 단서 |
| `campaign.py` | 자료 제안·단일 CTA·UTM 파라미터, 화면과 대본의 설정 공유 |
| `stage4_render.py` | manifest → props, 자산 링크, Remotion 프로세스 |
| `remotion/src/` | StockVideo, SVG 가격/추세/RSI/수익률/수급, SceneFrame, ClosingCard |
| `stage5_publish.py`, `token_auth.py` | ffprobe 기반 QC·YouTube·OAuth·정리 |
| `archive.py`, `qc_review.py` | 날짜별 실행 기록·종목 상태·품질 요약 |
| `dashboard.py`, `static/` | 로컬 관리 API·작업 큐·HTML/CSS/JS |
| `pages_export.py`, `public-dashboard/` | 공개 데이터 허용 목록·가격 시계열·정적 화면 |
| `tools/portable.py` | 경로 준비, JSON 경로 재지정, 소스 배포본 생성 |

## 3. 제작 흐름과 계약

단편은 stage2 → stage3 → stage4 순서입니다. 장편은 `stage2_long`에서 대본·음성·타임스탬프를 함께 구성한 뒤 stage4로 전달합니다. `--stage`로 재개할 때는 해당 모드에서 생성된 이전 산출물이 있어야 합니다.

장편 섹션 ID: `hook`, `setup`, `reveal`, `deep_dive`, `risk`, `wisdom`, `outro`. 현재 scene 계획은 이 ID를 고정된 분석 화면에 매핑합니다. 문자 누적 위치 기반 타이밍은 근사치이며, 최종 대본 교정 후 섹션 경계가 유지된다는 보장이 없습니다.

주요 JSON 필드:

| 객체 | 핵심 필드 |
|---|---|
| manifest 항목 | `audio`, `timestamps`, `script`, `long_text`, `sections`, `facts`, `series`, `metrics`, `cues` |
| Remotion item | `ticker`, `name`, `audioSrc`, `charts`, `series`, `timestamps`, `scenes`, `supply`, `levels`, `contact` |
| series | `d`, `o`, `h`, `l`, `c`, `v` 및 이동평균·RSI 등 지표 |
| timestamp | `word`, `start`, `end` (초) |
| scene | `id`, `point`, `eyebrow`, `headline`, `sub`, `chart`, `from`, `to`, `stats` |
| contact | `enabled`, `offer`, `channel`, `url`, `displayUrl`, `note` |
| archive item | 제작 팩트·대본·미디어 경로·QC·게시 ID·`archived_at`·`video_created_at` |

`series`가 없을 때는 기존 PNG 차트 경로를 사용합니다. 문의 제안은 실제 `LEAD_OFFER`와 HTTP(S) `CONTACT_URL`이 둘 다 설정돼야 활성화됩니다. UTM이 붙은 링크는 `contact.url`, 화면용 원본은 `displayUrl`입니다.

## 4. 파일 저장과 보존

- `data/long_manifest.json`, `data/audio_manifest.json`: 최신 실행 중간 산출물.
- `data/props_*.json`: 렌더 입력. 재생성될 수 있습니다.
- `data/archive/YYYY-MM-DD/{run,종목}.json`: 날짜별 영속 기록. 같은 날짜·종목 재실행은 덮어쓸 수 있습니다.
- `cache/<ticker>/`: 음성·차트 등 재제작 자산.
- `output/<ticker>.mp4`: 종목별 출력. 버전별 독립 미디어 저장 구조는 아닙니다.
- `state/price_tracking.json`: 가격 기준 스냅샷과 이력. 삭제하면 최초 기준을 다시 등록하므로 반드시 보존합니다.
- `state/`의 OAuth 토큰·실행 상태·쿨다운: 역할을 확인하고 비공개로 이전합니다.

기존 JSON에는 절대 파일 경로가 있습니다. 폴더 이동 시 `tools/portable.py rebase`로 경로 문자열만 바꿉니다. 대본 본문 전체를 문자열 치환하지 않습니다.

## 5. 로컬 관리 API

기본 `127.0.0.1:8787`. 상세 요청/응답 스키마는 실행 중인 `/docs`와 `/openapi.json`을 기준으로 합니다.

| 종류 | 엔드포인트 |
|---|---|
| 상태 | GET `/api/stats`, `/api/health`, `/api/diagnostics`, `/api/jobs` |
| 이력 | GET `/api/runs`, `/api/runs/{date}`, `/api/items/{date}/{ticker}` |
| 대본 | GET/PATCH `/api/items/{date}/{ticker}/script` |
| 검증/실행 | POST `/api/actions/validate-script`, `/api/actions/run` |
| 종목 작업 | POST `/api/actions/rebuild/{date}/{ticker}`, `/qc/{date}/{ticker}`, `/publish/{date}/{ticker}`, `/visibility/{date}/{ticker}` (모두 `/api/actions` 하위) |
| 삭제 | DELETE `/api/items/{date}/{ticker}`, `/api/runs/{date}` |
| 로그 | GET `/api/actions/log` (텍스트 응답) |
| 미디어 | GET `/media/video/{ticker}`, `/media/audio/{ticker}`, `/media/thumb/{ticker}`, `/media/chart/{ticker}/{name}` |

로그 응답을 JSON으로 파싱하는 UI 경로 등 알려진 문제는 STATUS 문서를 참고하세요. 관리 API는 별도의 원격 인증 계층을 제공하는 서비스로 검증되지 않았습니다.

## 6. 공개 가격 추적

`archive 날짜 + ticker`를 ID로 등록하며 기준은 선별 후보 가격이 아니라 제작 `facts.close_raw` 또는 `facts.close`입니다. 최초 기준을 고정하고 조회된 종가는 별도 보관합니다.

- `latestQuote`: 기준일을 포함해 조회된 최신 종가.
- `history`: 기준일보다 늦고 제작일 이전이 아닌 유효 거래 시세.
- `latest.changePct`: `(최신 종가 / 제작 기준가 - 1) × 100`.
- `milestones`: 후속 관측 1/5/20번째 값. 없는 기간은 `null`.
- `status`: `ok`, `waiting`, `pending`, `no-new-data`, `fetch-error`, `missing-baseline`.

같은 날 제작 기준가와 확정 종가가 다를 수 있습니다. 최신 가격 비교에는 표시하지만 D+1로 계산하지 않습니다. 배당·수수료·권리변동을 반영하는 총수익률 시스템은 아닙니다.

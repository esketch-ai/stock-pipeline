# stock-pipeline — 실행 환경 세팅 완료 보고

> **과거 설치 기록입니다.** 아래 모델·성별·완료 상태·API 설명 중 일부는 현재 코드와 다릅니다. 신규 설치 및 이식은 [README.md](README.md)와 [docs/MIGRATION.md](docs/MIGRATION.md), 검증 범위는 [docs/STATUS.md](docs/STATUS.md)를 기준으로 하세요.

M4 Pro (48GB) · macOS 26.6 · **매일 02:00 자동 실행** (launchd) 에 맞춰 구성했습니다.
구현 기준은 원본 `README.md` 의 5단계 아키텍처 + Critical Fixes 입니다.

---

## 설치 위치

`~/.local/share/stock-pipeline` (TCC 비보호 위치 — launchd 백그라운드 접근 안전)

## 디렉터리 구조

```
~/.local/share/stock-pipeline/
├── .env                     # API 키 (chmod 600, 직접 입력 필요)
├── config.py                # 전역 설정/키 로더
├── logger.py                # 단계별 로그 (logs/pipeline.log)
├── screening.py             # 1단계: pykrx 스크리닝 + 7일 쿨다운
├── stage2_script.py         # 2단계: LLM 비동기 대본 + mplfinance 4K 투명 차트
├── stage3_audio.py          # 3단계: TTS 비동기 + mlx-whisper 단어 타임스탬프
├── stage4_render.py         # 4단계: Remotion VideoToolbox 렌더
├── stage5_publish.py        # 5단계: ffprobe QC + YouTube 예약 + 7일 클린업
├── main_orchestrator.py     # 5단계 오케스트레이터
├── archive.py               # 실행 이력 아카이브 (대시보드 데이터 계층)
├── dashboard.py             # FastAPI 대시보드 서버
├── start_dashboard.sh       # 대시보드 실행 스크립트
├── static/index.html        # 대시보드 UI
├── token_auth.py            # YouTube OAuth 최초 인증 (1회)
├── setup_status.py          # 환경 진단
├── run_pipeline.sh          # launchd 실행 셸 (PATH/venv/caffeinate)
├── com.stockpipeline.daily.plist
├── com.stockpipeline.dashboard.plist
├── venv/                    # Python 3.12 가상환경
├── remotion/                # Remotion 프로젝트 (+ public/cache,output 심볼릭 링크)
└── logs/ output/ cache/ state/ data/
```

---

## ✅ 이미 구성·검증 완료

| 항목 | 상태 | 검증 내용 |
|---|---|---|
| Python 3.12 venv | 완료 | 모든 모듈 import 통과 |
| Python 의존성 | 완료 | pykrx, mlx-whisper 0.4.3, mplfinance, google-api 등 설치 |
| MLX / Metal 가속 | 완료 | `Device(gpu, 0)` — whisper GPU 추론 동작 |
| Whisper 단어 타임스탬프 | 완료 | 한국어 9토큰 정확 추출 (모델 캐시 후 2.6초) |
| Remotion + node_modules | 완료 | 258 패키지, esbuild 정상 |
| **VideoToolbox HW 인코딩** | 완료 | 렌더 로그에 **`-c:v h264_videotoolbox`** 확인 |
| 동적 Concurrency | 완료 | 48GB 감지 → 4 (24GB 이관 시 자동 2) |
| 4K 투명 차트 | 완료 | 3840×2160 RGBA 생성, 한글 폰트(AppleGothic) 적용 |
| launchd 등록 | 완료 | `com.stockpipeline.daily`, 매일 02:00 |
| launchd 실행 체인 | 완료 | kickstart로 셸→venv→오케스트레이터 구동 확인 |
| 환경 진단 | 완료 | `python3 setup_status.py` |

### ⚠️ README 1번 항목 정정 (중요)

원본 README 의 아래 코드는 **Remotion 4.x 에서 동작하지 않습니다**:

```ts
Config.overrideFfmpegCommand((defaultArgs) => defaultArgs.map(...))  // ❌
```

Remotion 4.x 훅 시그니처는 `(info: {type, args}) => string[]` 이므로
`info.args` 를 매핑해야 합니다. `remotion.config.ts` 에 **정정본**으로 반영했고,
VideoToolbox 가 실제로 붙는 것까지 렌더 로그로 확인했습니다.

### ⚠️ pykrx 1.2.x API 변경 (README 2단계 전제 아님)

README 은 `market="ALL"` / `adjusted=True` 인자를 전제하나 pykrx 1.2.9 에서는
제거되어 `TypeError` 가 납니다. `data.krx.co.kr` 무인증 엔드포인트는 **403 폐기**되어
KRX 계정 로그인이 필수입니다. 아래와 같이 재구현했습니다.

| 항목 | 처리 |
|---|---|
| KRX 로그인 | `.env` 의 `KRX_ID` / `KRX_PW` 로 자동 인증 (세션 60분) |
| 거래일 판정 | `get_nearest_business_day_in_a_week` — **주말/공휴일 대응 필수** (02:00 배치가 휴일에도 발동) |
| 종목 조회 | 종목별 120회 호출 시 KRX 연결이 30~85초 지연 후 reset → **거래일 스냅샷 6회**로 전 종목(942개) 점수 산출 후 상위 40만 상세 조회 |
| 종목명 | `ohlcv_by_date(name_display=True)` 의 **`columns.name`** 에 있음 (`index.name` 은 항상 '날짜') |
| 네트워크 | 전 호출에 지수 백오프 재시도 |
| 차트 컬럼 | pykrx 는 `등락률` 추가 반환 → mplfinance 요구사항(Open/High/Low/Close/Volume)에 맞춰 선택·개명 |
| 한글 폰트 | mplfinance 가 내부에서 rc 를 덮어쓰므로 `make_mpf_style(rc=...)` 로 주입 |
| 차트 크기 | `bbox_inches="tight"` 는 4K 규격을 잘라내므로 제거해 정확히 3840×2160 유지 |

### ⚠️ Gemini TTS 는 MP3 가 아니라 raw PCM

`gemini-2.5-flash-preview-tts` 는 `audio/L16;codec=pcm;rate=24000` (raw PCM)을 반환합니다.
이를 그대로 `.mp3` 로 쓰면 디코딩 실패하므로 `_encode_audio()` 가 ffmpeg `libmp3lame`
으로 변환 후 저장합니다.

---

## 🔧 남은 작업 — YouTube 자격증명만

`.env` 에 값을 넣으세요 (`nano ~/.local/share/stock-pipeline/.env`):

1. **YouTube 자격증명** — `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_CHANNEL_ID`
2. **YouTube 토큰** — 키 입력 후 1회 실행:
   ```bash
   ~/.local/share/stock-pipeline/venv/bin/python3 ~/.local/share/stock-pipeline/token_auth.py
   ```

### ✅ 이미 입력·검증 완료

| 키 | 상태 | 실측 검증 |
|---|---|---|
| `KRX_ID` / `KRX_PW` | 동작 | KRX 로그인 성공, 전 종목(942개) 시세 조회 정상 |
| `GEMINI_API_KEY` | 동작 | 대본 생성 12초, TTS 35초, 단어 타임스탬프 139토큰 |

현재 프로바이더: **LLM=gemini / TTS=gemini** (`.env` 에서 변경 가능)

> 참고: `GEMINI_TTS_API_KEY` 는 비어 있어도 됩니다. 코드가 `GEMINI_API_KEY` 를 재사용합니다.

입력 완료 후 확인:
```bash
~/.local/share/stock-pipeline/venv/bin/python3 ~/.local/share/stock-pipeline/setup_status.py
```

---

## 실제 처리 시간 (M4 Pro 실측)

| 항목 | 소요 | 비고 |
|---|---|---|
| 1. 스크리닝 | **7.6초** | 전 종목 6거래일 스냅샷 + 상위 40 상세 |
| 2. LLM + 4K 차트 | **12.3초** | Gemini 12초, 차트 2종 즉시 |
| 3. TTS + 타임스탬프 | **43.5초** | TTS 35초, whisper 8초 (139토큰) |
| 4. Remotion 렌더 | **60초** | 84초 영상 4K / Concurrency 4 / VideoToolbox |
| 5. QC + 게시 + 클린업 | 수십 초 | ffprobe 검증 통과 (3840×2160, 85.8초) |
| **합계** | **약 2.1분** | |

실측 샘플: 동양고속(084670) · 38,000원 · +29.91% · 3일 +65.22% · 거래량 4.58배
대본 수치 모두 실제 KRX 데이터와 일치, 투자 권유 고지 문구 포함.

---

## 🖥 대시보드 — http://127.0.0.1:8787

매일 생성된 컨텐츠를 보고 관리하는 웹 대시보드입니다. `com.stockpipeline.dashboard`
launchd 에 등록되어 부팅 시 자동 실행되고 죽으면 자동 재시작됩니다
(127.0.0.1 전용 — 외부에 열리지 않습니다).

### 보는 것

- **요약 지표** — 총 실행 / 생성 영상 / QC 통과 / 게시 완료 / 마지막 실행 / 디스크 용량
- **실행 이력 사이드바** — 날짜별 건수, 소요시간, 상태 (정상 / dry-run / 오류)
- **콘텐츠 카드** — 실제 영상 프레임 썸네일, 등락률, 종가, 점수, HOOK 발췌
- **상세 모달** — 영상 플레이어, 음원, 차트 2종(캔들/추세선), HOOK·BODY·CLOSING 전문,
  QC 결과, 단어 타임스탬프 139개 전체

### 관리하는 것

| 액션 | 설명 |
|---|---|
| **재렌더** | VideoToolbox HW 인코딩으로 해당 영상만 재생성 |
| **YouTube 게시** | 대시보드에서 즉시 예약 게시 (게시 후 7일 쿨다운 자동 등록) |
| **QC 재검증** | ffprobe 로 해상도·길이·용량 재검사 |
| **삭제** | 항목 또는 날짜 전체 삭제 (媒体的 포함/제외 선택) |
| **수동 게시 표시** | 외부 업로드한 항목을 게시됨으로 표시 + 쿨다운 등록 |
| **쿨다운 해제** | 해당 종목의 재투입 제한을 즉시 해제 |

> 링크 공유: `http://127.0.0.1:8787/?date=2026-10-11&t=084670` → 해당 항목 상세 자동 오픈

### 수동 실행

```bash
~/.local/share/stock-pipeline/start_dashboard.sh          #前台 실행
launchctl kickstart -p gui/$(id -u)/com.stockpipeline.dashboard   # 지금 실행
launchctl bootout gui/$(id -u)/com.stockpipeline.dashboard       # 중지
```

### 데이터 계층 (archive.py)

파이프라인 중간 산출물은 매 실행마다 덮어써지므로 이력이 사라집니다. `archive.py` 가
매 실행 종료 시(실패 시에도) 날짜 폴더로 스냅샷을 남깁니다.

```
data/archive/2026-10-11/run.json      실행 메타(단계 소요시간, 상태, 오류)
data/archive/2026-10-11/084670.json   종목 1건 전체(대본/타임스탬프/QC/게시)
data/archive/index.json               대시보드 목록용 요약 (자동 재생성)
```

---

## 🎬 영상 길이 모드

`.env` 의 `VIDEO_DURATION` 으로 전환합니다.

| 모드 | 길이 | 대본 | 구성 |
|---|---|---|---|
| `short` (기본값 아님) | 60~90초 | 350자 내외 | 단일 프롬프트 + 품질 검수 |
| `long` ✅ 현재 | **약 5~7분** | 2,400자 내외 | 6개 섹션 순차 생성 → 다듬기 |

> README 85행의 "7분 오디오 20편"은 whisper 처리 용량 산정 근거이며 목표 영상 길이가 아닙니다.

### 장편 구조 (`script_long.py`)

LLM 이 한 번에 2,400자를 안정적으로 뽑지 못하므로 6개 섹션으로 나눠 순차 생성합니다.

| 섹션 | 목표 | 역할 |
|---|---|---|
| `hook` | 180자 | 시네마틱 오프닝 |
| `setup` | 480자 | 오늘 장면의 큰 그림 |
| `reveal` | 620자 | 핵심 수치 공개 |
| `deep_dive` | 780자 | 심층 해석 (최장) |
| `risk` | 620자 | 반대편 논리·시나리오 |
| `outro` | 320자 | 정리 + 투자권유 고지 |

섹션 간 20초 간격(`LONG_SECTION_GAP`) — Gemini free-tier 분당 요청 제한 회피.

### 대본 품질 관리

| 파일 | 역할 |
|---|---|
| `facts.py` | KRX/뉴스에서 **팩트를 직접 수집** (LLM 환각 차단) |
| `script_quality.py` | 반복어·나열형·클리셰·환각 패턴을 기계 검사, 85점 미만이면 재생성 |

**LLM 이 절대 말하지 못하게 막은 것:**
공시 존재/부재, 테마성, 기관·외국인 수급, 실적, 수주 — 팩트 블록에 근거가 없으므로 금지.

---

## 🧠 유명 투자자 인용 시스템

출처: [the-modellers.com — 세계에서 가장 유명한 투자자 10명과 그들의 전략](https://the-modellers.com/blog/top-10-famous-investors)

`investors.py` 에 10명의 **전략 / 핵심 원칙 / 대표 사례 / 설명 톤**을 구조화해 저장합니다.

| # | 투자자 | 별칭 | 전략 |
|---|---|---|---|
| 1 | 워렌 버핏 | 오마하의 현인 | 가치 투자 |
| 2 | 피터 린치 | 성장 투자자 | 알고 있는 것에 투자하라 |
| 3 | 벤저민 그레이엄 | 가치투자의 아버지 | 안전마진(Margin of Safety) |
| 4 | 레이 달리오 | 헤지펀드 개척자 | 위험 균형 & 분산 투자 |
| 5 | 조지 소로스 | 투기의 대가 | 거시 투자(Macro) |
| 6 | 존 보글 | 인덱스 펀드의 선구자 | 수동적 투자 |
| 7 | 칼 아이칸 | 행동주의 투자자 | 기업 행동주의 |
| 8 | 데이비드 스웬슨 | 기금 관리자 | 대체 투자 |
| 9 | 짐 사이먼스 | 퀀트의 왕 | 알고리즘 트레이딩 |
| 10 | 찰리 멍거 | 합리성의 현자 | 정신 모델 & 합리적 투자 |

### 동작 방식

1. `wisdom` 섹션에서만 전체 카탈로그(전략·원칙·유효 키워드)를 LLM 에 전달
2. LLM 이 현재 장면에 맞는 **1~2인**을自行 선택하고 종목에 대입해 해석
3. `extract_investors()` 로 실제 인용된 사람만 추출해 아카이브/대시보드에 기록

### **투자자 추가 방법**

`investors.py` 의 `INVESTORS` 리스트에 항목 하나만 추가하면 자동 반영됩니다.
프롬프트·폴백·대시보드·아카이브를 건드릴 필요가 없습니다.

```python
Investor(
    id="new_id",
    name_ko="이름", name_en="English Name",
    nickname="별칭",
    strategy="전략명",
    keywords=["매칭 키워드", ...],
    principle="핵심 원칙 한 문장",
    case="대표 사례",
    tone="설명 톤 가이드",
    best_for=["이 상황에서 유효한 이유", ...],
)
```

### LLM 실패 시 폴백

`wisdom` 섹션은 LLM 이 429/503으로 죽어도 **투자자 DB 로 결정론적으로 생성**됩니다
(`build_fallback_section`). 야간 자동 실행이 API 한도 때문에 실패하지 않도록 한 안전장치입니다.

---

## 🎥 모션 디자인 (`remotion/src/StockVideo.tsx`)

| 요소 | 기법 |
|---|---|
| 배경 | 광원 2개 느린 드리프트 + 그리드 + 스캔 라인 |
| 오프닝 | 제목 **글자별 등장**(stagger) + 스케일 아웃, 3.5초 |
| 차트 | Ken Burns 줌(1.02→1.18) + 미세 팬 + 비네트 |
| 차트 전환 | 0~45% 캔들스틱 → 45~80% 추세선 → 80~100% 캔들스틱 |
| 자막 | **문장 단위** 구간(최대 14어절/5.2초), 현재 단어 글로우 하이라이트 |
| 상단 바 | 슬라이드 인 + 종목/등락률 배지 |
| 진행 바 | 하단 그라디언트, 구간 비율 표시 |

해상도 비례 스케일 — `width` 기준으로 모든 크기를 계산해 4K/1080p 자동 대응.

---

## 🎥 화면 구성 — 전문가 방송 스타일

### 1. 한국어 표기 표준 (`text_polish.py`)

생성된 대본에 자동 교정을 적용합니다.

| 규칙 | 예시 |
|---|---|
| 소수점 제거 | `65.22%` → `65%`, `4.58배` → `5배`, `524.52억` → `524억` |
| 어휘 난이도 하향 | 간극→격차, 역전 개연성→뒤집힐 가능성 |
| 띄어쓰기 | `사흘 새` → `사흘 만에` |

LLM 프롬프트에도 같은 규칙을 명시해 **생성 단계부터** 방지하고, 후처리로 한 번 더 잡습니다.

### 2. 다중 지표 차트 (`charts_extended.py`)

단일 이미지 반복 대신 4종을 생성해 영상 전체에 분산 배치합니다.

| 차트 | 보는 포인트 |
|---|---|
| `chart_price` | 캔들 + 거래량 (기세) |
| `chart_trend` | 이동평균 5/20/60일 (방향) |
| `chart_momentum` | 가격 vs RSI + 과매수/과매도 70·30 |
| `chart_return` | 기간 수익률 + 거래량 20일 평균 |

영상 길이를 N등분해 각 차트가 균등 노출되도록 배치합니다.

### 3. 방송용 오버레이 (`AnalystOverlay.tsx`)

- **지표 스트립** (상단) — 현재가 / 시가총액 / 거래대금 / 52주 고점 / 52주 위치.
  대본에서 그 지표가 언급되는 시각에 해당 칸이 골드로 점등됩니다.
- **차트 포인터** — 펄스 링 + 리더 라벨로 "지금 이 지점을 보고 있다"를 시각화.
  영상 전체에 4개 지점이 고르게 분포됩니다.
- **근거 배너** — 자막 위 강조 문구.

cue 는 `cues.py` 가 대본의 수치 언급 시각을 스캔해 자동 생성합니다(라벨당 최대 2회로 중복 억제).

---

## 실행 방법

```bash
# 진단
~/.local/share/stock-pipeline/venv/bin/python3 ~/.local/share/stock-pipeline/setup_status.py

# 전체 실행 (수동)
~/.local/share/stock-pipeline/run_pipeline.sh

# 렌더/게시 생략 검증
~/.local/share/stock-pipeline/venv/bin/python3 ~/.local/share/stock-pipeline/main_orchestrator.py --dry-run

# 특정 단계만
~/.local/share/stock-pipeline/venv/bin/python3 ~/.local/share/stock-pipeline/main_orchestrator.py --stage 3

# launchd 즉시 실행 (02:00 말고 지금)
launchctl kickstart -p gui/$(id -u)/com.stockpipeline.daily

# launchd 등록 해제
launchctl bootout gui/$(id -u)/com.stockpipeline.daily
```

로그: `~/.local/share/stock-pipeline/logs/pipeline.log` (단계별) · `launchd.out/err.log` (launchd)

---

## M4 노트북 운영 시 유의사항 (README 3번)

- **전원 어댑터 연결 필수** — 덮개 닫힘(Clamshell)으로 새벽 실행 시 어댑터 없으면 잠자기.
  `run_pipeline.sh` 의 `caffeinate -dimsu` 가 절전을 막습니다.
- **화면 잠금 허용** — 잠금 화면에서는 `launchd` GUI 에이전트가 계속 동작합니다.
- **첫 실행 메모리** — 4K 렌더는 Concurrency 4 기준 RAM 여유 필요. 메모리 압력 그래프가
  노랑/빨강이면 Mac mini(24GB) 이관 후 `os.totalmem()` 분기로 자동 2 로 내려갑니다.

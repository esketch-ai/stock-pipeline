# 운영 매뉴얼

## 명령 모음

프로젝트 루트에서 실행합니다.

```bash
# 지정 종목 제작, YouTube 게시 생략
venv/bin/python main_orchestrator.py --no-publish --tickers 000650,001210,012170
# 스크리닝부터 자동 제작, 게시 생략
venv/bin/python main_orchestrator.py --no-publish
# 이전 중간 산출물이 있는 경우 렌더 단계
venv/bin/python main_orchestrator.py --stage 4 --no-publish
# 관리자
venv/bin/python dashboard.py
# 시세와 공개 페이지 갱신(macOS/zsh)
zsh update_public_dashboard.sh
# 네트워크 없이 보존된 시세로 JSON 재생성
venv/bin/python pages_export.py --offline
```

## 일상 점검

### LLM 없이 장편 샘플 다시 만들기

대본 생성(LLM)을 건너뛰고 저장된 대본으로 TTS·자막·렌더만 다시 수행합니다.
할당량이 소진된 상태에서 화면·음성 품질을 확인할 때 사용합니다.

```bash
venv/bin/python tools/render_sample3.py 000650 001210 084670
```

대본은 `data/script_long_<종목>.txt` 에 있어야 합니다. 대본이 없으면 생성하지 않고 중단합니다.
구간은 저장된 구간표 비율로 문장 경계에서 자르므로 빈 구간이 생기지 않습니다.
LLM 할당량이 복구되면 정규 경로(`main_orchestrator.py`)로 전체 대본을 새로 만들어야 합니다.

### 저장된 음성·자막으로 로컬 렌더 복구

```bash
venv/bin/python tools/render_local.py
venv/bin/python tools/render_local.py --tickers 002990
venv/bin/python tools/render_local.py --manifest data/long_manifest.json
```

`audio_manifest.json`이 기본 입력이며 기존 `remotion/src/index.ts`의
`StockVideo`를 렌더링합니다. 출력은 `output/<ticker>.mp4`, QC 결과는
`data/local_render_qc.json`입니다. 렌더 누락 또는 QC 실패 시 종료 코드 1을
반환합니다. LLM/TTS 재생성 및 YouTube 게시 없이 저장된 제작 자산을 사용합니다.
`--dry-run`은 영상을 만들지 않으므로 실제 렌더 실행에 사용하지 않습니다.

1. `logs/`의 제작·Pages 로그와 프로세스 종료 상태 확인.
2. 새 영상의 음원, 숫자 발음, 자막, 화면-내레이션 일치 확인.
3. 공개 화면의 `generatedAt`뿐 아니라 종목별 종가 날짜·`checkedAt`·상태 확인.
4. YouTube 게시 전 실제 visibility/예약 설정 확인.
5. 장기 보관 영상은 `output/<ticker>.mp4`를 별도 버전 보관소에 복사.

## 장애별 확인

| 증상 | 확인·조치 |
|---|---|
| KRX 인증 실패/빈 데이터 | KRX ID/PW·세션·휴장·거래정지 확인. 시세 실패를 0%로 해석하지 않음 |
| Whisper 처음 실행이 오래 걸림 | prefetch 실행, 모델 캐시·디스크 여유 확인 |
| MLX import 실패 | Apple Silicon인지 확인. 다른 OS는 torch 폴백. 실제 선택 장치 확인 |
| Cloud TTS 400 voice 오류 | 공급자에 존재하는 언어/음성 조합 확인. Studio-A 추천은 폐기된 기록 |
| Cloud TTS 403 | 활성 gcloud 계정·프로젝트·API 권한·과금 프로젝트 확인 |
| Remotion 자산 404 | `prepare` 실행, JSON 경로 rebase, public 심볼릭 링크 확인 |
| 인코더 오류 | macOS는 VideoToolbox 지원 확인, `REMOTION_SOFTWARE_ENCODING=1`로 소프트웨어 비교 |
| 한글 네모/폰트 차이 | OS 한국어 글꼴 설치 후 PNG/SVG 모두 확인 |
| Pages 갱신 안 됨 | Mac 실행/네트워크, launchd 시간대, gh 인증, Git push 결과, Pages 빌드 확인 |
| Pages 충돌 | `pages-deploy`의 원격 변경 확인·동기화. 무조건 force push하지 않음 |
| 최근 종가와 기준가격 다름 | 제작 시점 스냅샷과 확정 종가는 별도. 같은 날도 차이가 날 수 있음 |
| D+N 집계 대기 | 필요한 후속 관측 거래일이 아직 없음. 최신 종가 표시와 독립 |
| 아카이브 미디어가 다른 영상 | 파일이 ticker 단위로 덮어써짐. 버전 보관 영상 확인 |

## 스케줄·로그

```bash
launchctl print "gui/$(id -u)/com.stockpipeline.pages"
launchctl kickstart "gui/$(id -u)/com.stockpipeline.pages"
tail -n 100 logs/pages.err.log
tail -n 100 logs/pipeline.log
```

재배포는 조회·파일 생성·커밋·푸시 순입니다. GitHub 배포가 실패해도 로컬 시세 이력은 남을 수 있으므로 다음 배포에서 해당 상태를 확인합니다. 공개 페이지는 서버가 없어도 마지막 정적 데이터를 보여주며 브라우저가 5분마다 데이터를 다시 읽습니다.

## 백업·복구

- 필수: `data/archive`, `state/price_tracking.json`, 필요한 나머지 상태.
- 재제작/보관: `data` 전체, `cache`, `output`.
- 비밀 설정: `.env`, YouTube 토큰은 별도 보호 저장소에 보관하고 새 머신에서 인증을 재발급할 수 있습니다.
- 소스: `tools/portable.py bundle` 산출물·체크섬·문서.

복구 순서: 새 환경 설치 → 데이터 복사 → 경로 rebase → 자산 링크 prepare → 오프라인 검증 → 관리자 재생 확인 → 시세 조회 → 일정 등록. 이전 머신의 스케줄은 새 환경 검증이 끝날 때까지 중지 상태로 둡니다.

가격 추적 최초 기준가가 잘못된 것으로 판명되면 원본 archive와 영상 수치를 먼저 대조하고 `state/price_tracking.json`을 백업한 뒤 해당 레코드만 명시적으로 교정합니다. 최신 종가에 맞추려고 최초 기준을 자동 변경하지 않습니다.

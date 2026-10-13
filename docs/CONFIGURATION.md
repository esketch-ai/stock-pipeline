# 설정 명세

`config.py`는 소스 파일 위치를 프로젝트 루트로 삼습니다. 현재 `.env`를 `override=True`로 로딩하므로 **동일 키는 셸 환경변수보다 `.env`가 우선**합니다. 빈 문자열은 코드의 기본값을 사용합니다. CLI 전용 `PORT`나 Remotion Node 환경변수는 해당 프로세스에 직접 전달합니다.

실제 비밀값을 문서나 배포 패키지에 넣지 않습니다. 새 환경에서는 `.env.example`을 복사한 뒤 사용하는 공급자 항목만 채웁니다.

| 구분 | 설정 | 설명 |
|---|---|---|
| 시장 | `KRX_ID`, `KRX_PW` | pykrx/KRX 인증 |
| LLM | `LLM_PROVIDER` | openai / anthropic / gemini |
| LLM | `OPENAI_API_KEY`, `OPENAI_MODEL` | 계정에서 실제 호출 가능한 모델 지정 |
| LLM | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Anthropic 공급자 |
| LLM | `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini 공급자 |
| 합성 | `TTS_PROVIDER` | openai / elevenlabs / gemini / gcloud |
| 합성 | `TTS_MODEL`, `TTS_VOICE`, `OPENAI_TTS_API_KEY` | OpenAI 음성. 키 폴백은 config 참고 |
| 합성 | `ELEVENLABS_API_KEY`, `ELEVENLABS_MODEL_ID`, `ELEVENLABS_VOICE_ID` | ElevenLabs |
| 합성 | `GEMINI_TTS_API_KEY`, `GEMINI_TTS_VOICE` | Gemini, LLM 키 재사용 가능 |
| Google | `GOOGLE_TTS_PROJECT`, `GOOGLE_TTS_VOICE` | 프로젝트 ID, 실제 지원되는 음성명 |
| Google | `GOOGLE_TTS_RATE`, `GOOGLE_TTS_PITCH` | 속도 및 반음 단위 피치. 음성별 지원 차이 확인 |
| 전사 | `WHISPER_MODEL` | 기본 MLX large-v3-turbo |
| 전사 | `WHISPER_FALLBACK_MODEL` | torch 기반 whisper-timestamped 모델, 기본 medium |
| 제작 | `VIDEO_DURATION` | long / short |
| 제작 | `LONG_TARGET_CHARS`, `LONG_SECTION_GAP` | 목표 글자 수와 섹션 호출 간격 |
| 제작 | `DAILY_VIDEO_COUNT`, `VIDEO_RESOLUTION` | 개수, 4k / 1080p |
| 병렬 | `LLM_MAX_CONCURRENCY`, `TTS_MAX_CONCURRENCY` | 공급자 한도에 맞춰 조정 |
| 재시도 | `LLM_MAX_RETRIES`, `API_TIMEOUT`, `TTS_TIMEOUT` | 재시도·요청 대기 |
| YouTube | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_CHANNEL_ID` | OAuth 및 대상 채널 |
| YouTube | `YOUTUBE_TOKEN_PATH` | 상대 경로는 프로젝트 루트 기준 |
| YouTube | `YOUTUBE_VISIBILITY`, `YOUTUBE_SCHEDULE_ENABLED` | private/unlisted/public, 예약 사용 여부 |
| CTA | `LEAD_OFFER`, `LEAD_CAMPAIGN` | 제공 자료명·유입 캠페인 |
| CTA | `CONTACT_CHANNEL`, `CONTACT_URL`, `CONTACT_NOTE` | 신청 경로 표시·실제 URL·설명 |
| CTA | `contact.txt` | 제공자 이름·이메일·전화·채널·주소·자료명·사업자 표시 (개인 파일, git·번들 제외) |
| CTA | `CONTACT_PROVIDER`, `CONTACT_EMAIL`, `CONTACT_PHONE`, `CONTACT_BUSINESS` | contact.txt 없이 환경변수로만 채울 때 |
| CTA | `CONTACT_QR_PERSISTENT` | `1` 이면 마무리 카드 외에 영상 상단에도 QR 유지 |

## 음성 선택 주의점

과거 추천했던 `ko-KR-Studio-A`는 실제 합성에서 존재하지 않는 이름으로 거절됐습니다. 로컬 `SUPPORTED_VOICES`의 성별 설명도 검증된 공급자 메타데이터가 아닙니다. `.env.example`은 `ko-KR-Neural2-C`를 제시하지만, 대상 계정에서 짧은 합성을 해보고 음색과 피치를 결정하세요. 기존 음성 F0 추정 실험은 신뢰 가능한 평가로 보지 않습니다.

gcloud 공급자는 `gcloud auth print-access-token`을 사용합니다. 현재 인증 헬퍼가 ADC 파일을 임시 이동하는 코드가 있으므로 공유 머신에서 동시 gcloud 작업을 수행할 때 이 부분을 먼저 검토해야 합니다.

## Node/프로세스 설정

- `REMOTION_CONCURRENCY=2`: Node 렌더 동시성. 미설정 시 메모리에 따라 2/4.
- `REMOTION_SOFTWARE_ENCODING=1`: macOS에서도 VideoToolbox 치환을 비활성화. Linux에서는 자동으로 치환하지 않습니다.
- `DEBUG_FFMPEG_ARGS=1`: ffmpeg 인자 출력.
- `PORT=9000`: 로컬 대시보드 포트.

이 Node 환경변수는 `.env`에만 넣기보다 렌더 실행 셸에서 `export`하여 전달하는 것이 명확합니다.

## 고정된 스케줄

생성되는 launchd 기본값은 제작 02:00, Pages 갱신 18:30, 관리자 서버 로그인 시 실행입니다. 시각은 **OS 로컬 시간**입니다. 시세 마감 판정은 코드에서 Asia/Seoul을 사용합니다. 다른 시간대 머신에서는 plist의 실행 시각을 한국 장 마감 이후가 되도록 조정하세요.

# Windows 11 환경 설정

## 일반 설정

Windows 11 환경에서 사용할 수 있는 모든 환경 변수와 설정입니다. 이 설정은 `.env` 파일에 기록됩니다.

## KRX 인증 정보

```env
# KRX 로그인 정보
KRX_ID=your_krx_id
KRX_PW=your_krx_password
```

> **주의**: KRX ID/PW는 공식적으로 제공된 계정이어야 하며 테스트 용도로 사용되지 않습니다.

## LLM (대형 언어 모델) 설정

```env
# LLM 제공자 선택 (openai, anthropic 등)
LLM_PROVIDER=openai

# OpenAI API 키
OPENAI_API_KEY=your_openai_key

# 사용할 모델 이름
OPENAI_MODEL=gpt-4

# API 엔드포인트 (선택사항)
OPENAI_BASE_URL=https://api.openai.com/v1
```

## TTS (텍스트 to 음성) 설정

```env
# TTS 제공자 선택 (openai, google, aws 등)
TTS_PROVIDER=openai

# OpenAI TTS 모델
TTS_MODEL=tts-1

# TTS 음성 설정
TTS_VOICE=alloy

# Google Cloud TTS (선택사항)
GOOGLE_TTS_PROJECT=your_gcloud_project_id
GOOGLE_TTS_VOICE=ko-KR-Neural2-C

# TTS 확장 옵션
TTS_SPEED=1.0
TTS_PITCH=0.0
```

## Whisper 음성 인식 설정

```env
# Whisper 모델 이름
WHISPER_MODEL=large-v3-turbo

# Whisper 폴백 모델 (CPU 기반)
WHISPER_FALLBACK_MODEL=medium

# Whisper 설정
WHISPER_BEAM_SIZE=5
WHISPER_LOGPROB_THRESHOLD=-1.0
WHISPER_NO_REPEAT_NGRAM_SIZE=0
```

## 영상 제작 설정

```env
# 영상 길이 설정 (short, long)
VIDEO_DURATION=short

# 일일 생성 영상 수
DAILY_VIDEO_COUNT=1

# 시각적 요소 설정
VIDEO_WIDTH=1920
VIDEO_HEIGHT=1080

# 프레임 레이트
VIDEO_FPS=30

# 스크린샷 크기
SCREENSHOT_SIZE=1920x1080
```

## YouTube 게시 설정

```env
# YouTube 클라이언트 ID (선택사항)
YOUTUBE_CLIENT_ID=your_youtube_client_id

# YouTube 클라이언트 시크릿 (선택사항)
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret

# YouTube 채널 ID (옵션)
YOUTUBE_CHANNEL_ID=your_youtube_channel_id

# 예약 게시 사용 여부
YOUTUBE_SCHEDULE_ENABLED=false

# 공개 여부 설정
YOUTUBE_PRIVACY_STATUS=private
```

## 마케팅 설정

```env
# 자료 신청명
LEAD_OFFER=자산 분석 보고서

# 캠페인 이름
LEAD_CAMPAIGN=stock_analysis_campaign

# 신청 채널
CONTACT_CHANNEL=website

# 신청 URL
CONTACT_URL=https://example.com/subscribe

# 신청 설명
CONTACT_NOTE=자세한 분석 보고서를 요청해주세요
```

## Windows 특화 설정

```env
# Remotion concurrency 설정 (Windows에서는 2로 권장)
REMOTION_CONCURRENCY=2

# Windows에서의 FFmpeg 인코더 (CPU 기반은 libx264 사용)
FFMPEG_ENCODER=libx264

# 로그 경로 설정 (Windows 전용)
LOGS_PATH=logs
DATA_PATH=data
CACHE_PATH=cache

# 최대 파일 경로 길이 제한 (Windows 260자 제한)
MAX_PATH_LENGTH=260
```

## 폴더 구조 관련 설정

```env
# 데이터 디렉토리
DATA_DIR=data

# 캐시 디렉토리
CACHE_DIR=cache

# 로그 디렉토리
LOGS_DIR=logs

# 출력 디렉토리
OUTPUT_DIR=output

# 임시 파일 디렉토리
TEMP_DIR=temp

# Remotion 관련 설정 디렉토리
REMOTION_DIR=remotion
```

## 성능 최적화 설정

```env
# TTS 스레드 수
TTS_THREADS=2

# Whisper 병렬 처리 수
WHISPER_PARALLEL=2

# 메모리 사용량 상한 (MB)
MAX_MEMORY_USAGE=4096

# 캐시 만료 시간 (초)
CACHE_EXPIRY=3600
```

## 디버그 및 로깅 설정

```env
# 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# 로그 파일 유지 기간 (일수)
LOG_RETENTION_DAYS=7

# 세부 로깅 활성화 여부
DETAILED_LOGGING=false

# 에러 발생 시 즉시 종료 여부
EXIT_ON_ERROR=false
```

## Windows 경로 관련 설정

```env
# Windows에서의 경로 구분자 (자동 감지)
PATH_SEPARATOR=\\

# 기본 디렉토리
DEFAULT_ROOT_DIR=C:\\stock-pipeline

# 로그 파일 경로
LOG_FILE_PATH=C:\\stock-pipeline\\logs\\pipeline.log

# 캐시 폴더 경로
CACHE_FOLDER=C:\\stock-pipeline\\cache
```

## 환경 변수 우선순위

설정은 다음과 같은 우선순위로 적용됩니다:

1. **환경 변수**: 시스템 환경 변수로 설정된 값
2. **.env 파일**: 프로젝트 루트 디렉토리의 .env 파일 내용
3. **기본값**: 코드 내에 설정된 기본값

## 주의사항 및 권고 사항

### Windows 특화 고려사항

1. **경로 길이 제한**: Windows는 최대 260자 제한이 있으므로, 짧은 경로를 사용하는 것을 권장합니다.

2. **파일 시스템 성능**: Windows의 파일 시스템 성능을 높이기 위해 자주 사용되는 폴더는 SSD에 위치시키는 것이 좋습니다.

3. **메모리 관리**: Windows에서는 메모리가 부족한 경우 시스템 성능 저하가 발생할 수 있습니다. 최소 8GB RAM 이상 권장합니다.

### 보안 고려사항

```env
# 민감 정보는 반드시 .gitignore에 포함
# .env 파일은 버전 관리 시스템에 추가하지 말 것
```

## 검증 명령어

Windows 환경에서 설정 확인용으로 사용할 수 있는 명령어들:

```powershell
# Python 환경 변수 확인
python -c "import os; print(os.environ.get('OPENAI_API_KEY', 'Not set'))"

# .env 파일 내용 확인 (PowerShell)
Get-Content .env

# Windows 경로 확인
Get-ChildItem -Path C:\stock-pipeline\logs -Filter *.log
```

## 샘플 .env 파일

```env
# KRX 인증 정보
KRX_ID=your_krx_id_here
KRX_PW=your_krx_password_here

# OpenAI API 설정
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxxx
OPENAI_MODEL=gpt-4

# TTS 설정 
TTS_PROVIDER=openai
TTS_MODEL=tts-1
TTS_VOICE=alloy

# Whisper 설정
WHISPER_MODEL=large-v3-turbo
WHISPER_FALLBACK_MODEL=medium

# 제작 설정
VIDEO_DURATION=short
DAILY_VIDEO_COUNT=1

# Windows 전용 설정
REMOTION_CONCURRENCY=2
LOGS_PATH=logs
DATA_PATH=data
```

이 문서는 Windows 환경에서 stock-pipeline 프로젝트를 정확하게 설정하고 실행하는 데 필요한 모든 정보를 제공합니다.
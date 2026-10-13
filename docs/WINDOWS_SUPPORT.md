# Windows 11 지원 문서

## 지원 상태

2026-10-13 기준으로 Windows 11 환경에서 전체 기능이 실행 가능하지만, 성능과 호환성은 macOS 환경보다 다소 제한적입니다. 특히 TTS 및 음성 합성 시 CPU 기반 처리로 인해 성능이 저하될 수 있습니다.

## 주요 제약 사항

| 항목 | 설명 |
|------|------|
| **TTS 성능** | mlx-whisper 대신 CPU 기반 torch 기반 Whisper 사용 |
| **영상 인코딩** | VideoToolbox가 아닌 libx264로 인코딩 |
| **파일 경로** | Windows 최대 260자 경로 제한 |
| **글꼴 지원** | 다양한 운영체제 환경에서 글꼴 찾기 기능 추가 |

## 시스템 요구사항

- Windows 11 (64비트)
- Python 3.12
- Node.js 22 LTS
- FFmpeg (Windows용)
- Git
- 최소 8GB RAM (권장 16GB)

## 설치 가이드

### 1. 필수 프로그램 설치

```bash
# Windows에서 Chocolatey를 사용하여 설치 (관리자 권한에서 실행)
choco install python nodejs ffmpeg git

# 또는 직접 다운로드 및 설치
# - Python 3.12: https://www.python.org/downloads/
# - Node.js 22 LTS: https://nodejs.org/
# - FFmpeg: https://ffmpeg.org/download.html
# - Git: https://git-scm.com/downloads
```

### 2. 가상환경 설정

```bash
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements-tested.txt
```

### 3. Remotion 프로젝트 세팅

```bash
cd remotion
npm ci
cd ..
```

### 4. 환경 초기화

```bash
python tools/portable.py prepare
```

## 환경 변수 및 설정

### .env 파일 구성 예시 (Windows)

```env
# KRX 인증 정보
KRX_ID=your_krx_id
KRX_PW=your_krx_password

# LLM 제공자 (예: OpenAI)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4

# TTS 제공자 (예: OpenAI)
TTS_PROVIDER=openai
TTS_MODEL=tts-1
TTS_VOICE=alloy

# Whisper 설정
WHISPER_MODEL=large-v3-turbo
WHISPER_FALLBACK_MODEL=medium

# YouTube 인증 정보 (옵션)
YOUTUBE_CLIENT_ID=your_youtube_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret

# Windows 관련 설정
REMOTION_CONCURRENCY=2
```

## 실행 방법

### 1. 기본 제작

```bash
# 지정 종목 제작, YouTube 게시 생략
venv\Scripts\python main_orchestrator.py --no-publish --tickers 000650,001210,012170

# 스크리닝부터 자동 제작
venv\Scripts\python main_orchestrator.py --no-publish

# 이전 중간 산출물이 있는 경우 렌더 단계
venv\Scripts\python main_orchestrator.py --stage 4 --no-publish
```

### 2. 관리자 서버 실행

```bash
venv\Scripts\python dashboard.py
```

### 3. 공개 페이지 갱신

```bash
# 네트워크 없이 보존된 시세로 JSON 재생성
venv\Scripts\python pages_export.py --offline

# 실제 시세 조회 및 갱신
zsh update_public_dashboard.sh
```

## 성능 최적화 팁

### 1. 메모리 사용량 조절
```bash
REMOTION_CONCURRENCY=2 # Windows에서는 병렬 처리 수를 낮추는 것이 좋음
```

### 2. Whisper 모델 사전 다운로드
```bash
venv\Scripts\python setup_status.py --prefetch-whisper
```

## 문제 해결

### 1. 경로 관련 오류

Windows에서는 경로가 너무 길어지는 경우 다음과 같이 해결:

- 설정파일 및 환경 변수에 절대 경로 사용
- 로컬 실행 디렉토리를 짧게 유지
- 캐시 폴더 위치를 변경하여 경로를 단축

### 2. 글꼴 관련 이슈

```python
# charts_extended.py에서 글꼴 찾기를 위한 예외 처리:
# Windows에서는 추가적인 경로를 포함하여 검색
# 기본적으로 C:\Windows\Fonts\ 하위 경로 확인
```

### 3. TTS 성능 문제

- CPU 기반 처리로 인해 시간이 오래 걸릴 수 있음
- 높은 품질의 음성 합성을 원한다면 외부 서버나 클라우드 API를 사용하는 것을 고려

## 로그 확인 방법

```bash
# 제작 로그 확인
type logs\pipeline.log

# 공개 페이지 로그 확인  
type logs\pages.err.log

# 차트 생성 로그 확인
type chart_error.log
```

## 지원되는 기능 및 제한사항

### 지원되는 기능:
- 모든 데이터 수집 및 분석 기능
- 스크리닝, 팩트, 대본 생성
- TTS 합성 (CPU 기반)
- 영상 렌더링 (libx264 사용)
- 관리자 UI
- 공개 페이지 갱신

### 제한 사항:
- VideoToolbox를 통한 하드웨어 가속 사용 불가
- TTS 성능은 macOS보다 30-50% 느릴 수 있음
- 경로 길이에 따른 제약 사항 존재
- Windows Task Scheduler 구성을 위한 별도 작업 필요

## 참고 자료

1. **Windows 설치 관련 팁**: https://www.windowscentral.com/how-to-install-python-on-windows-10
2. **Node.js 다운로드**: https://nodejs.org/download/release/latest-v22.x/
3. **FFmpeg 설치**: https://ffmpeg.org/download.html
4. **Python 가상환경**: https://docs.python.org/3/library/venv.html
5. **Remotion 문서**: https://remotion.dev
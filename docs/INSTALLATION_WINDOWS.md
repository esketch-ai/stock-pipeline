# Windows 11 설치 가이드

## 전제 조건

다음 소프트웨어 및 환경이 필요합니다:
- Windows 11 (64비트)
- Python 3.12
- Node.js 22 LTS
- FFmpeg
- Git
- Chocolatey (선택사항 - 설치 자동화를 위해)

## 설치 단계

### 1. 필수 프로그램 설치

#### Windows Package Manager (Chocolatey) 설치 (선택)
```powershell
# 관리자 권한 PowerShell에서 실행
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

#### 필수 프로그램 설치
```powershell
# Chocolatey를 통한 설치 (관리자 권한)
choco install python nodejs ffmpeg git

# 또는 수동 설치:
# - Python 3.12: https://www.python.org/downloads/
# - Node.js 22 LTS: https://nodejs.org/
# - FFmpeg: https://ffmpeg.org/download.html
# - Git: https://git-scm.com/downloads
```

### 2. 프로젝트 다운로드 및 설정

```bash
# GitHub에서 저장소 클론
git clone <repository-url>
cd stock-pipeline

# 또는 소스 패키지 사용
# dist/stock-pipeline-source.tar.gz를 해제 후 작업
```

### 3. Python 가상환경 생성

```powershell
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (PowerShell)
venv\Scripts\Activate.ps1

# 또는 커맨드 프롬프트
venv\Scripts\activate

# 패키지 업데이트
pip install --upgrade pip
```

### 4. 의존성 설치

```powershell
# 요구사항 파일을 사용하여 설치
pip install -r requirements-tested.txt

# 또는 개발 환경에 맞게 수동 설치
pip install python-dotenv httpx pydantic pykrx pandas numpy mplfinance matplotlib mlx-whisper whisper-timestamped 
```

### 5. Node.js 프로젝트 세팅

```bash
cd remotion
npm ci
cd ..

# 필요 시 npm 패키지 수동 설치
npm install @remotion/cli @remotion/renderer
```

### 6. 환경 변수 설정

```bash
# .env.example 파일 복사 및 수정
copy .env.example .env
```

#### .env 파일 예시:

```env
# KRX 인증 정보
KRX_ID=your_krx_id
KRX_PW=your_krx_password

# LLM 제공자
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4

# TTS 제공자
TTS_PROVIDER=openai
TTS_MODEL=tts-1
TTS_VOICE=alloy

# Whisper 설정
WHISPER_MODEL=large-v3-turbo
WHISPER_FALLBACK_MODEL=medium

# 제작 설정
VIDEO_DURATION=short
DAILY_VIDEO_COUNT=1

# YouTube 인증 정보 (옵션)
YOUTUBE_CLIENT_ID=your_youtube_client_id
YOUTUBE_CLIENT_SECRET=your_youtube_client_secret

# Google Cloud TTS (선택)
GOOGLE_TTS_PROJECT=your_project_id
GOOGLE_TTS_VOICE=ko-KR-Neural2-C

# Windows에서의 추가 설정
REMOTION_CONCURRENCY=2
```

### 7. 초기화

```powershell
python tools/portable.py prepare
```

## 환경 확인

### 1. 의존성 설치 상태 확인

```powershell
# Python 패키지 상태 확인
pip list | findstr "pydantic"
pip list | findstr "pykrx"

# Node.js 패키지 상태 확인
cd remotion
npm list @remotion/cli
cd ..
```

### 2. Whisper 모델 사전 다운로드

```powershell
python setup_status.py --prefetch-whisper
```

## 실행 방법

### 1. 샘플 실행

```powershell
# 기본적인 스크리닝 및 제작
venv\Scripts\python main_orchestrator.py --no-publish --tickers 000650
```

### 2. 관리자 서버 실행

```powershell
venv\Scripts\python dashboard.py
# 웹 브라우저에서 http://localhost:8000 접속
```

### 3. 공개 페이지 갱신

```powershell
# 오프라인 모드 (네트워크 없이)
venv\Scripts\python pages_export.py --offline

# 실시간 갱신
zsh update_public_dashboard.sh
```

## Windows 특화 고려사항

### 1. 경로 제한

Windows는 파일 및 디렉토리 경로가 최대 260자 제한을 가집니다. 경로가 너무 길어지는 경우:

```powershell
# 프로젝트를 짧은 경로로 이동
cd C:\temp\stock-pipeline
```

### 2. 폰트 문제

Windows 환경에서 글꼴 문제가 발생할 수 있으므로, 다음과 같이 확인하거나 설치합니다:

```python
# charts_extended.py에서 자동 감지 시스템을 포함하여
# C:\Windows\Fonts\ 경로 하위의 모든 텍스트 파일 검색 기능 추가
```

### 3. 동기화 문제

Windows에서는 시간 동기화가 중요하므로, 시스템 설정에서 NTP(NTP Server)를 사용 설정하는 것을 권장합니다.

## 문제 해결

### 1. 파이썬 의존성 오류

```powershell
# 특정 패키지 재설치
pip uninstall package_name
pip install package_name

# 필요한 모듈 직접 설치 (Windows에서 빌드 오류 발생 시)
pip install --upgrade --force-reinstall numpy
```

### 2. Node.js 관련 오류

```powershell
cd remotion
npm cache clean --force
npm install
cd ..
```

### 3. FFmpeg 경로 문제

```powershell
# Windows에서 FFmpeg 가용성을 확인
where ffmpeg

# PATH에 추가된 경우 환경변수 확인
echo %PATH%
```

## 로그 확인

### 주요 로그 위치

```powershell
# 제작 로그
type logs\pipeline.log

# 페이지 갱신 로그
type logs\pages.err.log

# 차트 생성 오류 로그
type chart_error.log
```

### 로그 분석 팁

- `logs\pipeline.log` : 스크리닝, 분석, 대본 생성 등의 프로세스 로그
- `logs\pages.err.log` : 공개 페이지 갱신 중 발생한 오류 로그  
- `chart_error.log` : 차트 생성 실패 시 오류 상세 정보

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

## 팁 및 조언

1. **실행 환경**: 시스템의 메모리가 충분한지 점검 (최소 8GB 권장, 16GB 이상 추천)
2. **백업 주기**: 주기적으로 `data/`와 `state/` 폴더를 백업
3. **디스크 공간**: 최소 50GB 이상의 디스크 공간 확보 필요
4. **네트워크 안정성**: KRX API와 외부 서비스 접속에 대한 네트워크 연결 확인

## 참조 문서

- [Python 공식 문서](https://docs.python.org/)
- [Node.js 공식 문서](https://nodejs.org/docs/latest/)
- [Remotion 문서](https://remotion.dev)
- [FFmpeg 설치 가이드](https://ffmpeg.org/download.html)
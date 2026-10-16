# 🍎 맥미니(운영서버) 완벽 마이그레이션 & 가동 가이드

> **"맥미니를 24시간 365일 무중단 유튜브 주식 영상 자동 제작 서버로 변신시키기!"**  
> 본 가이드는 현재 개발 머신에서 작업한 모든 환경, 비밀 키, 인증 토큰, 종목 DB, 4K 렌더러를 **맥미니(Apple Silicon) 운영서버**로 한 치의 오차 없이 이식하여 새벽 2시 자동 배치와 관리자 대시보드를 안정적으로 구동하는 전체 절차를 안내합니다.

---

## 📋 마이그레이션 준비 요약 체크리스트

- [x] **깃허브 최신 코드 동기화 (`git push origin main`)** - *완료*
- [x] **비밀 및 운영 데이터 패키징 (`macmini_migration_pack.tar.gz`)** - *생성 완료*
- [x] **맥미니 전용 원클릭 자동 셋업 스크립트 (`setup_macmini.sh`)** - *준비 완료*
- [x] **macOS launchd 백그라운드 자동화 데몬 (새벽 2시 배치 & 대시보드 상시 가동)** - *자동 등록 준비 완료*

---

## 🚀 3단계 초간단 마이그레이션 절차

### 1단계: 현재 머신에서 마이그레이션 팩 전송

현재 머신의 터미널에서 아래 명령을 실행하면 `.env`, 유튜브/구글 드라이브 토큰, 종목 분석 DB, 아카이브가 담긴 `macmini_migration_pack.tar.gz`가 생성됩니다:

```bash
cd /Users/ssh/.local/share/stock-pipeline
./tools/create_migration_pack.sh
```

생성된 `macmini_migration_pack.tar.gz` 파일을 **맥미니로 전송**합니다:
* **방법 A (가장 편리)**: Finder에서 **AirDrop**으로 맥미니에 전송
* **방법 B (네트워크 scp 전송)**:
  ```bash
  scp macmini_migration_pack.tar.gz <맥미니유저>@<맥미니IP>:~/Downloads/
  ```

---

### 2단계: 맥미니에서 저장소 복제 및 원클릭 셋업 실행

이제 **맥미니에 접속(화면 공유 또는 SSH)**하여 터미널을 열고 아래 명령을 순서대로 실행합니다:

```bash
# 1. 원하는 작업 경로로 이동 (예: 홈 디렉터리)
cd ~

# 2. 깃허브에서 최신 코드 클론
git clone https://github.com/esketch-ai/stock-pipeline.git
cd stock-pipeline

# 3. 1단계에서 전송받은 마이그레이션 팩을 현재 디렉터리로 복사
# (Downloads 폴더에 받은 경우)
cp ~/Downloads/macmini_migration_pack.tar.gz .

# 4. 원클릭 자동 셋업 스크립트 실행
./setup_macmini.sh
```

#### 💡 `setup_macmini.sh`가 자동으로 수행하는 작업:
1. **시스템 필수 패키지 자동 설치**: Homebrew, `ffmpeg`, `node@22`, `python@3.12`, `gcloud`
2. **마이그레이션 데이터 자동 복원**: `.env`, `state/` (YouTube/GDrive 인증 토큰), `data/stock_analytics.db` (종목 DB), `data/archive` (영상 기록)
3. **Python 가상환경(venv) 및 Apple Silicon Metal 가속 구축**: `mlx-whisper` Metal GPU 가속 세팅
4. **Remotion 4K 비디오 렌더러 의존성 설치**: `cd remotion && npm install`
5. **Whisper 대용량 모델 사전 다운로드**: `whisper-large-v3-turbo` 가중치 사전 캐싱
6. **macOS launchd 백그라운드 데몬 자동 등록**:
   - `com.stockpipeline.dashboard`: 대시보드 상시 가동 (포트 `8787`, 맥미니 재부팅 시 자동 시작)
   - `com.stockpipeline.daily`: 매일 새벽 02:00 전 종목 자동 스크리닝 & 4K 렌더 & 아카이브 & 구글드라이브 업로드

---

### 3단계: Google Cloud 인증 확인 (최초 1회)

Google Cloud TTS(Neural2-C / Chirp3-HD)를 사용하기 위해 맥미니에서 최초 1회 Google 로그인을 진행합니다:

```bash
# Google Cloud CLI 로그인 (웹 브라우저가 열립니다)
gcloud auth login

# 프로젝트 ID 연결
gcloud config set project mmpt-511300

# TTS 연결 테스트 (정상 응답 확인)
venv/bin/python -c "import gcloud_tts; print(gcloud_tts.probe())"
# 출력 예: {'ok': True, 'project': 'mmpt-511300', 'voice': 'ko-KR-Neural2-C', 'reason': '연결 정상'}
```

---

## 🖥️ 맥미니 운영 환경 확인 및 접속

### 1. 관리자 대시보드 접속
* **맥미니 로컬 브라우저**: `http://localhost:8787`
* **맥북/아이패드/스마트폰 (동일 Wi-Fi / 사내망)**: `http://<맥미니_IP>:8787`
  - 맥미니 IP 확인: 터미널에서 `ipconfig getifaddr en0`

### 2. 맥미니 절전(Sleep) 방지 설정 (필수 권장)
맥미니가 화면이 꺼지거나 유휴 상태가 되어도 새벽 2시에 배치가 원활히 돌 수 있도록 시스템 절전을 해제합니다:

```bash
# 디스플레이는 꺼지더라도 맥미니 본체는 절대 잠들지 않도록 설정
sudo pmset -a disablesleep 1
```

### 3. 실시간 로그 모니터링
```bash
# 대시보드 서버 로그 확인
tail -f logs/dashboard.out.log

# 새벽 2시 자동 배치 실행 로그 확인
tail -f logs/launchd.out.log
```

### 4. 수동 즉시 테스트 실행 (원할 때 언제든)
```bash
# 동국제강(460860) 1종목 즉시 제작 테스트 (유튜브 게시 생략)
./run_pipeline.sh --tickers 460860 --no-publish
```

---

## 🛡️ 문제 발생 시 트러블슈팅

| 증상 | 원인 및 해결 방법 |
| :--- | :--- |
| **대시보드가 뜨지 않음** | `launchctl list \| grep stockpipeline` 실행 후 상태 확인. 수동 재시작: `launchctl load -w ~/Library/LaunchAgents/com.stockpipeline.dashboard.plist` |
| **TTS 오류 (HTTP 401/403)** | `gcloud auth login` 세션 만료. 터미널에서 다시 `gcloud auth login` 실행 |
| **Remotion 렌더 실패** | `cd remotion && npx remotion versions` 로 Chromium 설치 상태 확인. Node 버전이 18 이상인지 확인 (`node -v`) |
| **YouTube 토큰 만료** | `state/youtube_token.json`이 누락된 경우 `venv/bin/python token_auth.py` 로 브라우저에서 1회 재인증 |

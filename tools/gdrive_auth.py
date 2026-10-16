#!/usr/bin/env python3
"""Google Drive OAuth2 토큰 생성 및 갱신 CLI 도구 (tools/gdrive_auth.py).

사용법:
    # 1. 로컬 브라우저 자동 승인 방식 (권장)
    python3 tools/gdrive_auth.py

    # 2. 콘솔 복사/붙여넣기 방식 (원격 서버용)
    python3 tools/gdrive_auth.py --console
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# stock-pipeline 루트 경로 추가
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

import config
from logger import log

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

TOKEN_PATH = config.STATE_DIR / "gdrive_token.json"


def authenticate_local():
    """로컬 브라우저 루프백을 통한 Google Drive 인증."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = config.YOUTUBE_CLIENT_ID
    client_secret = config.YOUTUBE_CLIENT_SECRET

    if not client_id or not client_secret:
        print("❌ .env 파일에 YOUTUBE_CLIENT_ID 및 YOUTUBE_CLIENT_SECRET 가 설정되어 있지 않습니다.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/", "http://127.0.0.1:8080/"],
        }
    }

    print("🔑 Google Drive 인증을 시작합니다...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    print(f"✅ Google Drive 토큰이 성공적으로 저장되었습니다: {TOKEN_PATH}")


def authenticate_console():
    """콘솔 복사/붙여넣기 방식 인증."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = config.YOUTUBE_CLIENT_ID
    client_secret = config.YOUTUBE_CLIENT_SECRET

    if not client_id or not client_secret:
        print("❌ .env 파일에 YOUTUBE_CLIENT_ID 및 YOUTUBE_CLIENT_SECRET 가 설정되어 있지 않습니다.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES, redirect_uri="urn:ietf:wg:oauth:2.0:oob")
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    print("\n👉 아래 URL을 웹 브라우저에 붙여넣어 구글 계정으로 로그인하고 권한을 승인하세요:")
    print(f"\n{auth_url}\n")
    code = input("승인 후 표시된 인증 코드(Code)를 여기에 붙여넣으세요: ").strip()

    flow.fetch_token(code=code)
    creds = flow.credentials

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    print(f"✅ Google Drive 토큰이 성공적으로 저장되었습니다: {TOKEN_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Google Drive 인증 도구")
    parser.add_argument("--console", action="store_true", help="브라우저 대신 콘솔 입력으로 진행")
    args = parser.parse_args()

    if args.console:
        authenticate_console()
    else:
        try:
            authenticate_local()
        except Exception as e:
            print(f"로컬 서버 인증 실패 ({e}) → 콘솔 방식으로 전환합니다.")
            authenticate_console()


if __name__ == "__main__":
    main()

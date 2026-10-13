"""YouTube OAuth2 인증 (최초 1회 실행 후 자동 갱신).

    ~/.local/share/stock-pipeline/venv/bin/python3 token_auth.py            # 로컬 서버 방식
    ~/.local/share/stock-pipeline/venv/bin/python3 token_auth.py --playground  # OAuth Playground 방식

두 방식의 차이:
  * 로컬 서버 : redirect_uri 가 http://localhost:<임의포트>.
                Google Cloud 의 "데스크톱 앱" 유형은 localhost 를 자동 허용하므로
                등록 없이 동작합니다. (웹 앱 유형이면 localhost 를 등록해야 함)
  * 플레이그라운드 : redirect_uri 가 https://developers.google.com/oauthplayground.
                .env 의 YOUTUBE_REDIRECT_URI 와 일치해야 하며, 코드 복붙이 필요합니다.

인증 후 state/youtube_token.json 이 생성되고, 이후 파이프라인/대시보드는 자동 갱신합니다.
"""

from __future__ import annotations

import sys
import urllib.parse
import webbrowser

import config
from logger import log

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

PLAYGROUND = "https://developers.google.com/oauthplayground"


def _client_config(redirect_uris: list[str]) -> dict:
    return {
        "installed": {
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": redirect_uris,
        }
    }


def _save(creds) -> None:
    config.YOUTUBE_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    config.YOUTUBE_TOKEN_PATH.chmod(0o600)
    log.info("✔ 인증 완료 → %s", config.YOUTUBE_TOKEN_PATH)


def _verify(creds) -> None:
    """인증 후 채널 정보와 권한을 실제 API 로 확인한다."""
    try:
        from googleapiclient.discovery import build

        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        me = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
        items = me.get("items", [])
        if not items:
            log.error("인증은 성공했지만 채널 정보를 조회할 수 없습니다.")
            return
        ch = items[0]
        cid = ch["id"]
        log.info("인증 채널: %s (%s)", ch["snippet"]["title"], cid)
        if config.YOUTUBE_CHANNEL_ID and config.YOUTUBE_CHANNEL_ID != cid:
            log.warning("⚠ .env 의 YOUTUBE_CHANNEL_ID 와 실제 인증 채널이 다릅니다!")
            log.warning("  .env   : %s", config.YOUTUBE_CHANNEL_ID)
            log.warning("  실제   : %s", cid)
        else:
            log.info("✔ 채널 ID 일치 (.env)")

        try:
            up = yt.channels().list(part="contentDetails", id=cid).execute()
            log.info("업로드 가능 상태: %s", up["items"][0]["contentDetails"].get("status", {}))
        except Exception as exc:
            log.warning("업로드 상태 확인 실패: %s", exc)
    except Exception as exc:
        log.error("채널 검증 실패: %s", exc)


def local_flow() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    try:
        flow = InstalledAppFlow.from_client_config(_client_config(["http://localhost"]), SCOPES)
    except Exception as exc:
        log.error("클라이언트 설정 실패: %s", exc)
        return 1

    log.info("브라우저에서 Google 계정 인증을 진행합니다.")
    log.info("브라우저가 자동으로 열립니다. '계속' 을 클릭한 뒤 이 창으로 돌아오세요.")

    # run_local_server 가 redirect_uri(http://localhost:<port>) 생성과 수신 서버를
    # 모두 소유한다. 여기서 authorization_url() 을 따로 호출해 브라우저를 열면
    # redirect_uri 가 빠진 URL 로 열려 'Missing required parameter: redirect_uri' 오류가 난다.
    try:
        creds = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            authorization_prompt_message="브라우저에서 인증을 승인해 주세요…",
            success_message="인증이 완료되었습니다. 이 창을 닫아도 됩니다.",
        )
    except Exception as exc:
        msg = str(exc)
        if "redirect_uri_mismatch" in msg:
            log.error(
                "redirect_uri_mismatch — OAuth 클라이언트에 http://localhost 이\n"
                "  등록되어 있지 않습니다. Google Cloud 콘솔의 '승인된 리다이렉트 URI' 에\n"
                "  http://localhost 을 추가하세요. (또는 --playground 방식 사용)"
            )
        else:
            log.error("인증 실패: %s", msg)
        return 1

    _save(creds)
    _verify(creds)
    return 0


def playground_flow() -> int:
    """OAuth Playground 를 통한 수동 코드 수령 방식."""
    params = {
        "client_id": config.YOUTUBE_CLIENT_ID,
        "redirect_uri": config.YOUTUBE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = PLAYGROUND + "?" + urllib.parse.urlencode(params)

    print("\n" + "=" * 66)
    print("OAuth Playground 수동 인증")
    print("=" * 66)
    print("\n1) 브라우저에서 아래 주소를 여세요:\n")
    print(f"   {url}\n")
    print("2) 우측 '설정'齿轮 아이콘 → 'OAuth 2.0 클라이언트 ID' 에 아래를 입력하세요:")
    print(f"     Client ID     : {config.YOUTUBE_CLIENT_ID}")
    print(f"     Client Secret : {config.YOUTUBE_CLIENT_SECRET}")
    print("\n3) 스코어를 다음으로 교체하세요:")
    print("   " + "\n   ".join(SCOPES))
    print("\n4) '승인 요청' 클릭 후 '코드 승인' → 'YOUR_CODE' 를 아래에 붙여넣으세요.")
    print("   (오디언스가 Authorized URL 에 등록되어 있어야 합니다)")

    code = input("\n인증 코드 입력: ").strip()
    if not code:
        log.error("인증 코드가 입력되지 않아 취소합니다.")
        return 1

    import httpx

    try:
        r = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": config.YOUTUBE_CLIENT_ID,
                "client_secret": config.YOUTUBE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config.YOUTUBE_REDIRECT_URI,
            },
            timeout=30,
        )
        data = r.json()
    except Exception as exc:
        log.error("토큰 요청 실패: %s", exc)
        return 1

    if "access_token" not in data:
        log.error("토큰 발급 실패: %s", data.get("error_description", data))
        return 1

    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        scopes=SCOPES,
    )
    if not creds.refresh_token:
        log.warning("refresh_token 이 없습니다 — 만료 후 자동 갱신이 안 될 수 있습니다.")
        log.warning("Playground 에서 승인 시 '액세스 범위' 를 확인하세요.")

    _save(creds)
    _verify(creds)
    return 0


def main() -> int:
    if not config.YOUTUBE_CLIENT_ID or not config.YOUTUBE_CLIENT_SECRET:
        log.error("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 미설정 (.env 확인)")
        return 1

    try:
        import google_auth_oauthlib  # noqa: F401
    except ImportError:
        log.error("google-auth-oauthlib 미설치 — pip install -r requirements.txt")
        return 1

    if "--playground" in sys.argv:
        return playground_flow()
    return local_flow()


if __name__ == "__main__":
    sys.exit(main())
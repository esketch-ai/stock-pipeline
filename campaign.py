"""대본과 화면이 공유하는 자료 신청 제안 및 유입 식별자."""
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import config

CONTACT_FILE = config.PROJECT_DIR / "contact.txt"

# contact.txt 키 -> 화면 표기. 없는 값은 넣지 않는다.
CONTACT_FIELDS = ("name", "email", "phone", "channel", "url", "offer", "note", "business")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+\-.\s()]{7,20}$")


def load_contact_file(path: Path | None = None) -> dict[str, str]:
    """contact.txt 를 읽는다. 없는 파일·빈 값·형식 오류는 조용히 제외한다."""
    file = path or CONTACT_FILE
    if not file.exists():
        return {}
    values: dict[str, str] = {}
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key in CONTACT_FIELDS and value:
            values[key] = value
    if "email" in values and not _EMAIL_RE.match(values["email"]):
        values.pop("email")
    if "phone" in values and not _PHONE_RE.match(values["phone"]):
        values.pop("phone")
    return values


def _tracking_url(url: str, ticker: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(utm_source="youtube", utm_medium="video",
                 utm_campaign=config.env("LEAD_CAMPAIGN", "stock-analysis"),
                 utm_content=ticker)
    return urlunsplit(parts._replace(query=urlencode(query)))


def _valid_web(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"https", "http"} and bool(parts.netloc)


def contact_payload(ticker: str) -> dict:
    """화면·대본이 함께 쓰는 연락처 정보.

    contact.txt 가 우선이고, 없는 항목만 .env 로 채운다.
    (파일 = 현재 운영 정보, 환경변수 = 이식·기본값)
    자료 신청 CTA 와 QR 은 offer + 유효한 주소가 함께 있을 때만 생긴다.
    전화·이메일 같은 단순 안내는 자료 설정과 무관하게 표시한다.
    """
    from_env = {
        "name": config.env("CONTACT_PROVIDER"),
        "email": config.env("CONTACT_EMAIL"),
        "phone": config.env("CONTACT_PHONE"),
        "channel": config.env("CONTACT_CHANNEL"),
        "url": config.env("CONTACT_URL"),
        "offer": config.env("LEAD_OFFER"),
        "note": config.env("CONTACT_NOTE"),
        "business": config.env("CONTACT_BUSINESS"),
    }
    raw = {k: v for k, v in from_env.items() if v}
    raw.update(load_contact_file())

    url = raw.get("url", "")
    offer = raw.get("offer", "")
    # 주소가 없으면 QR 을 만들 수 없고, 자료명만으로는 신청을 안내할 수 없다.
    enabled = bool(offer and _valid_web(url))
    tracked = _tracking_url(url, ticker) if enabled else ""

    rows = [
        {"label": "문의", "value": v}
        for v in (raw.get("phone", ""), raw.get("email", ""))
        if v
    ]
    return {
        "enabled": enabled,
        "offer": offer if enabled else "",
        "channel": raw.get("channel", ""),
        "url": tracked,
        "displayUrl": raw.get("url", "") if enabled else "",
        "note": raw.get("note", ""),
        # 안내용 표기. 자료 설정이 없어도 연락처가 있으면 화면에 밝힌다.
        "provider": raw.get("name", ""),
        "rows": rows,
        "business": raw.get("business", ""),
        "qrSrc": qr_asset(tracked) if enabled else None,
    }


def qr_asset(url: str, out: Path | None = None) -> str | None:
    """오프라인으로 QR 을 만든다. 실패하면 조환히 None (화면은 텍스트만 표시).

    주소가 바뀌면 기존 QR 을 반드시 다시 만든다. 주소가 바뀐 것을 모르고
    예전 QR 을 그대로 노출하면 시청자가 다른 곳으로 이동한다.
    """
    if not url:
        return None
    target = out or (config.CACHE_DIR / "contact" / "qr.png")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import segno
    except ImportError:
        from logger import log

        log.warning("segno 미설치 — QR 미생성 (pip install segno)")
        return None

    stamp = target.with_suffix(".url")
    stale = (not target.exists()
             or target.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n"
             or not stamp.exists() or stamp.read_text(encoding="utf-8").strip() != url)
    try:
        if stale:
            segno.make(url, error="m").save(
                target, scale=14, border=2, dark="#0B1220", light="#FFFFFF"
            )
            stamp.write_text(url, encoding="utf-8")
    except Exception as exc:  # 생성 실패가 렌더 전체를 막지 않게 한다
        from logger import log

        log.warning("QR 생성 실패: %s", exc)
        return None
    return f"cache/contact/{target.name}"


def scenario_instruction(section_id: str, ticker: str) -> str:
    beats = {
        "hook": "첫 두 문장에 종목명과 확인된 변화 하나를 제시한다. 보유자와 관심자가 궁금해할 질문 하나를 열고, 뒤에서 확인할 근거를 예고한다. 인사와 신청 유도는 생략한다.",
        "setup": "왜 지금 이 종목을 보는지 설명한다. 수급 데이터가 있으면 기간과 순매수 방향을 설명하고, 없으면 가격·거래량 맥락만 말한다.",
        "reveal": "핵심 수치 하나 → 의미 → 해석의 한계 순으로 답한다. 오프닝에서 던진 질문에 첫 답을 준다.",
        "deep_dive": "관찰된 추세와 그에 대한 해석을 구분한다. 보유자와 신규 관심자가 각각 확인할 조건을 설명한다. 확인되지 않은 매수 주체나 재료를 추정해 채우지 않는다.",
        "risk": "상승 유지·횡보·추세 이탈의 조건을 비교한다. 주어진 데이터로 확인할 수 있는 조건만 사용하고 결론을 자료 신청 뒤로 숨기지 않는다.",
        "wisdom": "앞의 분석을 시청자가 다시 확인할 체크리스트 세 항목으로 정리한다. 투자자 원칙을 인용한다면 실제 제공된 인용만 짧게 연결한다.",
        "outro": "오프닝 질문에 한 문장으로 답하고 핵심 확인 조건을 요약한다. 아래 설정에 따른 행동 하나만 제안한다.",
    }
    contact = contact_payload(ticker)
    cta = "신청 제안이 설정되지 않았다. 자료 제공·상담·연락 방법을 임의로 약속하지 않는다."
    if contact["enabled"]:
        if section_id == "deep_dive":
            cta = f"근거 설명을 마친 뒤 한 문장만: '{contact['offer']}' 신청 안내가 설명란에 있다는 사실을 자연스럽게 알린다."
        elif section_id == "outro":
            cta = (f"제공 항목은 '{contact['offer']}'. 영상 분석과 연결되는 활용 이유를 짧게 말하고 "
                   "'설명란의 자료 신청 링크에서 안내를 확인해 주세요'라는 단일 행동으로 마무리한다. URL 자체는 읽지 않는다.")
        else:
            cta = "이 구간에는 신청 유도를 넣지 않는다."
    return (beats.get(section_id, "") + "\n" + cta +
            "\n수익 보장, 미확인 적중률, 허위 후기·마감·한정 인원, 설정에 없는 무료 혜택이나 상담 약속을 만들지 않는다.")
"""자료 신청 설정이 내레이션과 화면에 일관되게 전달되는지 검증."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import campaign
import script_long


class CampaignTest(unittest.TestCase):
    def setUp(self):
        # contact.txt 와 QR 캐시는 내용에 따라 결과가 달라지므로 모두 격리한다.
        patcher = patch.object(campaign, "CONTACT_FILE", Path("/nonexistent/contact.txt"))
        patcher.start()
        self.addCleanup(patcher.stop)
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        cache_patcher = patch.object(campaign.config, "CACHE_DIR", Path(cache.name))
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)

    def test_unconfigured_offer_does_not_promise_delivery(self):
        with patch.dict(os.environ, {"LEAD_OFFER": "", "CONTACT_URL": ""}):
            self.assertFalse(campaign.contact_payload("000650")["enabled"])
            self.assertIn("임의로 약속하지", campaign.scenario_instruction("outro", "000650"))

    def test_offer_and_attribution_share_configuration(self):
        with patch.dict(os.environ, {"LEAD_OFFER": "가격 확인표", "CONTACT_URL": "https://example.com/apply?ref=abc#form"}):
            payload = campaign.contact_payload("000650")
            self.assertTrue(payload["enabled"])
            query = parse_qs(urlsplit(payload["url"]).query)
            self.assertEqual(query["ref"], ["abc"])
            self.assertEqual(query["utm_content"], ["000650"])
            self.assertEqual(urlsplit(payload["url"]).fragment, "form")
            prompt = script_long.build_section_prompt("outro", "정리", 200, "팩트", "추세", "천일고속", "000650")
            self.assertIn(payload["offer"], prompt)
            self.assertIn("단일 행동", prompt)
            self.assertIn("신청 유도를 넣지", campaign.scenario_instruction("hook", "000650"))

    def test_non_web_destination_disables_offer(self):
        with patch.dict(os.environ, {"LEAD_OFFER": "자료", "CONTACT_URL": "javascript:alert(1)"}):
            self.assertFalse(campaign.contact_payload("000650")["enabled"])


class ContactFileTest(unittest.TestCase):
    """contact.txt 로 제공자 정보를 등록하면 화면·QR 로 전달된다."""

    def _write(self, body: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write(body)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_phone_only_shows_contact_without_promising_materials(self):
        file = self._write("name: 민동엽\nphone: 010-8408-0464\nchannel: 전화 문의\n")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(campaign.config, "CACHE_DIR", Path(directory)), \
                patch.object(campaign, "CONTACT_FILE", file):
            payload = campaign.contact_payload("001210")
            instruction = campaign.scenario_instruction("outro", "001210")
        # 자료 신청 안내는 만들지 않는다.
        self.assertFalse(payload["enabled"])
        self.assertIsNone(payload["qrSrc"])
        self.assertIn("임의로 약속하지", instruction)
        # 연락처 자체는 화면에 보여준다.
        self.assertEqual(payload["provider"], "민동엽")
        self.assertEqual([r["value"] for r in payload["rows"]], ["010-8408-0464"])
        self.assertEqual(payload["channel"], "전화 문의")

    def test_contact_file_wins_over_legacy_env(self):
        file = self._write("channel: 전화 문의\n")
        with patch.object(campaign, "CONTACT_FILE", file), \
                patch.dict(os.environ, {"CONTACT_CHANNEL": "채널 메시지로 문의"}):
            self.assertEqual(campaign.contact_payload("000650")["channel"], "전화 문의")

    def test_email_and_phone_are_accepted_by_regex(self):
        for value in ("010-8408-0464", "010 8408 0464", "010.8408.0464"):
            with patch.object(campaign, "CONTACT_FILE", self._write(f"phone: {value}\n")):
                self.assertEqual(campaign.load_contact_file().get("phone"), value)
        with patch.object(campaign, "CONTACT_FILE", self._write("phone: 전화해 주세요\n")):
            self.assertNotIn("phone", campaign.load_contact_file())

    def test_empty_file_disables_everything(self):
        with patch.object(campaign, "CONTACT_FILE", self._write("name:\nurl:\noffer:\n")):
            payload = campaign.contact_payload("000650")
            self.assertFalse(payload["enabled"])
            self.assertIsNone(payload["qrSrc"])
            self.assertEqual(payload["rows"], [])

    def test_provider_details_flow_to_payload_and_qr(self):
        file = self._write(
            "# 안내\n"
            "name: OO 종목분석\n"
            "email: help@example.com\n"
            "phone: 02-1234-5678\n"
            "channel: 채널 메시지\n"
            "url: https://example.com/apply\n"
            "offer: 가격·거래량 확인 체크리스트\n"
            "business: 대표자 홍길동\n"
        )
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(campaign.config, "CACHE_DIR", Path(directory)), \
                patch.object(campaign, "CONTACT_FILE", file):
            payload = campaign.contact_payload("000650")
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["provider"], "OO 종목분석")
        self.assertEqual(payload["business"], "대표자 홍길동")
        self.assertEqual([r["value"] for r in payload["rows"]],
                         ["02-1234-5678", "help@example.com"])
        self.assertTrue(payload["qrSrc"].startswith("cache/contact/"))
        self.assertIn("utm_content=000650", payload["url"])
        # 화면에는 추적 매개변수 없는 원본 주소를 보여준다.
        self.assertEqual(payload["displayUrl"], "https://example.com/apply")

    def test_malformed_values_are_dropped(self):
        file = self._write("email: not-an-email\nphone: 전화번호를 나중에 적습니다\n")
        with patch.object(campaign, "CONTACT_FILE", file):
            values = campaign.load_contact_file()
        self.assertNotIn("email", values)
        self.assertNotIn("phone", values)

    def test_offer_without_url_does_not_promise(self):
        with patch.object(campaign, "CONTACT_FILE", self._write("offer: 체크리스트\nchannel: 채널 메시지\n")):
            self.assertFalse(campaign.contact_payload("000650")["enabled"])

    def test_qr_is_generated_offline_as_png(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "qr.png"
            path = campaign.qr_asset("https://example.com/apply?utm_source=youtube", out)
            self.assertEqual(path, "cache/contact/qr.png")
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(out.stat().st_size, 500)
            self.assertIsNone(campaign.qr_asset("", out))

    def test_qr_is_regenerated_when_address_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "qr.png"
            campaign.qr_asset("https://example.com/first", out)
            first = out.read_bytes()
            campaign.qr_asset("https://example.com/second", out)
            self.assertNotEqual(first, out.read_bytes())
            # 같은 주소면 다시 쓰지 않는다.
            before = out.stat().st_mtime_ns
            campaign.qr_asset("https://example.com/second", out)
            self.assertEqual(before, out.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
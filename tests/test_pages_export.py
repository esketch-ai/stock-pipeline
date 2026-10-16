import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pages_export import discover, pct, public_record, refresh


class TrackingTest(unittest.TestCase):
    def test_snapshot_is_immutable_and_export_contains_no_private_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / '2026-10-12'
            parent.mkdir()
            path = parent / '000650.json'
            item = {'video': '/private/video.mp4', 'audio': '/private/audio.mp3', 'facts': {'close_raw': 100, 'trading_day': '20261012'}, 'long_text': 'private script'}
            path.write_text(json.dumps(item))
            records = {}
            discover(Path(folder), records)
            item['facts']['close_raw'] = 200
            path.write_text(json.dumps(item))
            discover(Path(folder), records)
            record = next(iter(records.values()))
            self.assertEqual(record['baseline'], 100)
            self.assertNotIn('private', json.dumps(public_record(record)))

    def test_change_milestones_and_failure_preserve_history(self):
        record = {'ticker':'000650', 'baseline':100, 'baselineDate':'2026-10-09', 'history':[]}
        refresh(record, lambda *args: [('2026-10-12', 110), ('2026-10-13', 90), ('2026-10-14', 0)], date(2026,10,14), 'now')
        result = public_record(record)
        self.assertEqual(result['latest']['changePct'], -10)
        self.assertEqual(result['milestones']['1'], 10)
        self.assertIsNone(result['milestones']['5'])
        def fail(*args): raise RuntimeError('offline')
        refresh(record, fail, date(2026,10,15), 'later')
        self.assertEqual(record['status'], 'fetch-error')
        self.assertEqual(len(record['history']), 2)
        self.assertEqual(record['checkedAt'], 'now')

    def test_same_day_quote_is_shown_but_not_counted_as_day_one(self):
        record = {'ticker':'000650', 'baseline':100, 'baselineDate':'2026-10-12', 'history':[]}
        refresh(record, lambda *args: [('2026-10-12', 102)], date(2026,10,12), 'now')
        self.assertEqual(public_record(record)['latest']['changePct'], 2)
        self.assertEqual(record['baseline'], 100)
        self.assertIsNone(public_record(record)['milestones']['1'])
        self.assertEqual(record['history'], [])
        self.assertIsNone(pct(100, None))

    def test_prices_before_video_creation_are_excluded(self):
        record = {'ticker':'000650', 'baseline':100, 'baselineDate':'2026-10-01', 'createdAt':'2026-10-12T10:00:00', 'history':[]}
        refresh(record, lambda *args: [('2026-10-08', 105), ('2026-10-12', 110)], date(2026,10,12), 'now')
        self.assertEqual([p['date'] for p in record['history']], ['2026-10-12'])


if __name__ == '__main__': unittest.main()

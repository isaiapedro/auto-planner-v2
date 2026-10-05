import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parent.parent


class MemoEventLinkContractTests(unittest.TestCase):
    def test_upload_creates_observation_before_queue_job(self):
        source = (API_ROOT / "routers/memos.py").read_text()
        helper = source[source.index("async def _create_memo_records"):source.index("@router.post(\"/upload\"")]
        self.assertLess(helper.index("INSERT INTO observations"), helper.index("INSERT INTO memo_jobs"))
        self.assertIn("await _create_memo_records(obs_id, dest, event_title)", source)

    def test_worker_enriches_the_upload_observation(self):
        source = (API_ROOT / "services/pipeline.py").read_text()
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", source)
        self.assertIn("observations.payload || EXCLUDED.payload", source)

    def test_startup_backfills_pre_fix_jobs(self):
        source = (API_ROOT / "database.py").read_text()
        self.assertIn("FROM memo_jobs", source)
        self.assertIn("ON CONFLICT (id) DO NOTHING", source)

    def test_event_memo_id_is_uuid_validated(self):
        source = (API_ROOT / "schemas.py").read_text()
        request = source[source.index("class EventConfirmRequest"):source.index("class CalendarBlockCreate")]
        self.assertIn("memo_id: UUID | None = None", request)


if __name__ == "__main__":
    unittest.main()

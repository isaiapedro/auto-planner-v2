import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parent.parent
MOBILE_ROOT = API_ROOT.parent.parent / "mobile"


@unittest.skipUnless(MOBILE_ROOT.is_dir(), "Mobile source is not mounted in the API image")
class MobileContractTests(unittest.TestCase):
    def test_today_hydrates_from_sqlite_before_network_refresh(self):
        source = (MOBILE_ROOT / "src/screens/Today.tsx").read_text()
        self.assertIn("getEventsForToday", source)
        self.assertLess(source.index("getEventsForToday"), source.index("syncPull()"))

    def test_today_places_standalone_memo_capture_before_timeline(self):
        source = (MOBILE_ROOT / "src/screens/Today.tsx").read_text()
        self.assertLess(source.index('accessibilityLabel="Capture a memo"'), source.index("s.sectionTitle"))
        self.assertNotIn("ListFooterComponent", source)

    def test_custom_memo_title_survives_local_queue_retry(self):
        source = (MOBILE_ROOT / "src/screens/RecordMemo.tsx").read_text()
        self.assertIn("const memoTitle = title.trim() || eventTitle", source)
        self.assertIn("saveMemoLocal(db, memoId, uri, eventId, memoTitle)", source)
        self.assertIn("uploadMemo(uri, memoTitle, memoId)", source)

    def test_calendar_add_block_route_is_absent(self):
        source = (MOBILE_ROOT / "src/navigation/RootNavigator.tsx").read_text()
        self.assertNotIn("AddCalendarBlock", source)

    def test_memos_are_uncapped_for_the_authenticated_owner_app(self):
        client = (MOBILE_ROOT / "src/api/client.ts").read_text()
        router = (API_ROOT / "routers/memos.py").read_text()
        self.assertIn('request<MemoListItem[]>("/memos")', client)
        self.assertIn("async def list_memos(limit: int | None = None)", router)
        self.assertIn("return ordered[:limit] if limit is not None else ordered", router)

    def test_insights_memo_corpus_is_local_model_only(self):
        workspace = API_ROOT.parents[4]
        privacy = (workspace / "personal/planner/PRIVACY.md").read_text()
        self.assertIn("complete local memo", privacy)
        self.assertIn("never be sent to an external LLM provider", privacy)


if __name__ == "__main__":
    unittest.main()

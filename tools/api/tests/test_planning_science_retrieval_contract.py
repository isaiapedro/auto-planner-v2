"""Dependency-free contract checks for Planning Science retrieval coverage."""
from pathlib import Path
import unittest


TESTS_ROOT = Path(__file__).resolve().parent
API_ROOT = TESTS_ROOT.parent
LOCAL_WORKSPACE_ROOT = API_ROOT.parents[4] if len(API_ROOT.parents) > 4 else None
RUNTIME_KNOWLEDGE_ROOT = Path("/knowledge")
KNOWLEDGE_ROOT = RUNTIME_KNOWLEDGE_ROOT if RUNTIME_KNOWLEDGE_ROOT.is_dir() else LOCAL_WORKSPACE_ROOT / "knowledge"
WIKI_ROOT = KNOWLEDGE_ROOT / "planning_science" / "wiki" / "concepts"
PLANNER_MANIFEST = LOCAL_WORKSPACE_ROOT / "services/planner/manifest.yaml" if LOCAL_WORKSPACE_ROOT else Path("/__not_mounted__")

REQUIRED_PAGES = {
    "academic-writing-process-and-feedback.md": "knowledge/media/raw/writing/",
    "problem-solving-practice-and-feedback.md": "knowledge/health/raw/",
    "retrieval-practice-and-spaced-review.md": "knowledge/health/raw/",
    "portfolio-artifacts-and-feedback.md": "knowledge/health/raw/",
}


class PlanningScienceRetrievalContractTests(unittest.TestCase):
    def test_goal_relevant_pages_have_local_provenance_and_bounded_use(self):
        for name, source_prefix in REQUIRED_PAGES.items():
            text = (WIKI_ROOT / name).read_text(encoding="utf-8")
            self.assertIn("## Provenance", text)
            self.assertIn(source_prefix, text)
            self.assertIn("## Bounded claims", text)
            self.assertIn("## Applicability limits", text)
            self.assertIn("## Permitted product use", text)

    def test_pipeline_explicitly_retrieves_the_planning_science_domain(self):
        source = (API_ROOT / "services/planning/orchestrator.py").read_text(encoding="utf-8")
        self.assertIn('domains=["planning_science", "health", "technology", "business", "media", "arts"]', source)
        window = source[source.index("domains="):source.index("categories=")]
        self.assertNotIn('"personal"', window)

    @unittest.skipUnless(PLANNER_MANIFEST.is_file(), "Planner manifest is not mounted in the API image")
    def test_planner_manifest_declares_curated_planning_science_read_access(self):
        manifest = PLANNER_MANIFEST.read_text(encoding="utf-8")
        self.assertIn("- planning_science", manifest)
        self.assertIn("- knowledge/planning_science/wiki/*", manifest)


if __name__ == "__main__":
    unittest.main()

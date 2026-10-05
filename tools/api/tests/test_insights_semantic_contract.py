import importlib.util
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parent
API_ROOT = TESTS_ROOT.parent
LOCAL_WORKSPACE_ROOT = API_ROOT.parents[4] if len(API_ROOT.parents) > 4 else None
# The API image mounts Personal at /personal and does not mount the full
# repository.  Keep the runtime contract runnable in both locations.
RUNTIME_PERSONAL_ROOT = Path("/personal/planner/insights")
INSIGHTS_ROOT = RUNTIME_PERSONAL_ROOT if RUNTIME_PERSONAL_ROOT.is_dir() else LOCAL_WORKSPACE_ROOT / "personal" / "planner" / "insights"
WORKSPACE_ROOT = Path("/") if RUNTIME_PERSONAL_ROOT.is_dir() else LOCAL_WORKSPACE_ROOT
PYDANTIC_AVAILABLE = importlib.util.find_spec("pydantic") is not None
API_RUNTIME_AVAILABLE = all(importlib.util.find_spec(package) is not None for package in ("fastapi", "httpx", "pydantic", "pydantic_settings"))
PUBLISHER_PATH = INSIGHTS_ROOT / "system" / "publish.py"
MOBILE_ROOT = API_ROOT.parent.parent / "mobile"


def load_publisher():
    spec = importlib.util.spec_from_file_location("insights_publisher", PUBLISHER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pillar_taxonomy(path: Path) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    name = None
    topics: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) == {"-"}:
            continue
        if not line.startswith((" ", "\t", "-")):
            if name is not None:
                groups.append((name, topics))
            name, topics = ("household_tasks" if stripped == "household tasks" else stripped), []
        elif stripped.startswith("-"):
            topics.append(stripped[1:].split(":", 1)[0].strip())
    if name is not None:
        groups.append((name, topics))
    return groups


class InsightSemanticContractTests(unittest.TestCase):
    def test_published_review_has_existing_in_scope_evidence_and_full_taxonomy(self):
        review = json.loads((INSIGHTS_ROOT / "synthesized_inferences" / "current_review.json").read_text())
        for source in review["source_files"]:
            self.assertTrue(source.startswith("personal/planner/memos/"))
            self.assertTrue((WORKSPACE_ROOT / source).is_file(), source)
        actual = [
            (group["name"], [topic["name"] for topic in group["topics"]])
            for group in review["inference_bundle"]["life_pillar_review"]["groups"]
        ]
        self.assertEqual(actual, pillar_taxonomy(INSIGHTS_ROOT / "archive" / "pillars.txt"))

    def test_router_uses_the_semantic_gate_for_the_mobile_payload(self):
        router = (API_ROOT / "routers/insights.py").read_text(encoding="utf-8")
        self.assertIn("validate_insight_candidate", router)
        self.assertIn("settings.personal_insights_path", router)

    def test_relationship_contract_is_cited_and_registry_bound(self):
        schemas = (API_ROOT / "schemas.py").read_text(encoding="utf-8")
        validation = (API_ROOT / "services/insights_validation.py").read_text(encoding="utf-8")
        self.assertIn("class GoalRelationship", schemas)
        self.assertIn("evidence_paths: list[str] = Field(min_length=1)", schemas)
        self.assertIn("relationship targets must be distinct", schemas)
        self.assertIn("relationship_kind, relationships", validation)
        self.assertIn("unknown {relationship_kind} target goal ID", validation)

    @unittest.skipUnless(MOBILE_ROOT.is_dir(), "Mobile source is not mounted in the API image")
    def test_mobile_renders_substantive_findings_and_scientific_support(self):
        types = (MOBILE_ROOT / "src/types/index.ts").read_text(encoding="utf-8")
        screen = (MOBILE_ROOT / "src/screens/Insights.tsx").read_text(encoding="utf-8")
        self.assertIn("conflicts?: GoalRelationship[]", types)
        self.assertIn("facilitators?: GoalRelationship[]", types)
        self.assertIn("future.conflicts ?? []", screen)
        self.assertIn("future.facilitators ?? []", screen)
        self.assertIn("Evidence-informed options", screen)
        self.assertIn("item.applicability", screen)

    def test_current_components_are_exact_projections_of_aggregate(self):
        publisher = load_publisher()
        aggregate = json.loads((INSIGHTS_ROOT / "synthesized_inferences" / "current_review.json").read_text())
        expected = publisher.component_payloads(aggregate)
        for name, value in expected.items():
            actual = json.loads((INSIGHTS_ROOT / "synthesized_inferences" / f"{name}.json").read_text())
            self.assertEqual(actual, value, name)

    def test_root_publisher_archives_snapshots_and_promotes_aggregate_last(self):
        publisher = load_publisher()
        aggregate = {
            "schema_version": "1.2",
            "generated_at": "2026-09-10T00:00:00-03:00",
            "source_files": ["personal/planner/memos/records/evidence.md"],
            "example": False,
            "narrative": "Test review.",
            "inference_bundle": {
                "schema_version": "1.2",
                "routine_review": {"summary": "r"},
                "goal_review": {"registry_path": "../archive/long_term_goals.md", "summary": "g"},
                "future_plan_review": {"summary": "f"},
                "life_pillar_review": {"summary": "p", "groups": []},
            },
        }

        class Review:
            def model_dump(self, *, mode):
                self_mode = mode
                return aggregate

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "personal/planner/insights"
            root.mkdir(parents=True)
            published = publisher.publish_candidate(
                aggregate,
                insights_root=root,
                review_id="2026-09-10T00-00-00_test-publication",
                gate=lambda payload, insights_root: Review(),
            )
            self.assertEqual(published, aggregate)
            self.assertTrue((root / "archive/2026-09-10T00-00-00_test-publication/review.json").is_file())
            self.assertTrue((root / "synthesized_inferences/snapshots/2026-09-10T00-00-00_test-publication/current_review.json").is_file())
            with self.assertRaises(publisher.PublicationError):
                publisher.publish_candidate(
                    aggregate,
                    insights_root=root,
                    review_id="2026-09-10T00-00-00_test-publication",
                    gate=lambda payload, insights_root: Review(),
                )

    @unittest.skipUnless(PYDANTIC_AVAILABLE, "Pydantic is installed in the API runtime image, not this minimal verifier")
    def test_semantic_gate_rejects_missing_evidence(self):
        import os
        os.environ.setdefault("PIOS_API_TOKEN", "test-token")
        from services.insights_validation import InsightSemanticValidationError, validate_insight_candidate

        review = json.loads((INSIGHTS_ROOT / "synthesized_inferences" / "current_review.json").read_text())
        review["source_files"][0] = "personal/planner/memos/records/does-not-exist.md"
        with self.assertRaises(InsightSemanticValidationError):
            validate_insight_candidate(review, INSIGHTS_ROOT)

    @unittest.skipUnless(API_RUNTIME_AVAILABLE, "FastAPI runtime dependencies are installed in the API image")
    def test_authenticated_status_and_current_share_the_runtime_validation_path(self):
        os.environ.setdefault("PIOS_API_TOKEN", "test-token")
        token = os.environ["PIOS_API_TOKEN"]
        from httpx import ASGITransport, AsyncClient
        from main import app

        async def request_current_and_status():
            transport = ASGITransport(app=app)
            headers = {"Authorization": f"Bearer {token}"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                current = await client.get("/insights/current", headers=headers)
                status = await client.get("/insights/status", headers=headers)
            return current, status

        current, status = asyncio.run(request_current_and_status())
        self.assertEqual(current.status_code, 200)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "ready")
        self.assertEqual(status.json()["schema_version"], current.json()["schema_version"])


if __name__ == "__main__":
    unittest.main()

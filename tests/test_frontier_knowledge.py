from research_agent_lab.frontier.knowledge import (
    abstract_from_inverted, clean_openalex_work, independent_screen
)
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.model import BudgetedModel
from research_agent_lab.contracts import Snapshot
from pathlib import Path


def demo():
    path = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"
    return Snapshot.model_validate_json(path.read_text(encoding="utf-8"))


def test_openalex_inverted_abstract():
    assert abstract_from_inverted({"urban": [0], "study": [1]}) == "urban study"


def test_openalex_metadata_source_and_retraction():
    record = {
        "id": "https://openalex.org/W123456",
        "title": "Some paper",
        "doi": "https://doi.org/10.1000/example",
        "primary_location": {"source": {"display_name": "Cities"}},
        "abstract_inverted_index": {"Some": [0], "abstract": [1]},
        "is_retracted": False,
    }
    paper = clean_openalex_work(record)
    assert paper.id == record["id"]
    assert paper.venue == "Cities"
    assert paper.abstract == "Some abstract"
    record["is_retracted"] = True
    assert clean_openalex_work(record) is None


def test_independent_paper_screen_keeps_real_ids():
    model = BudgetedModel(FrontierMockModel())
    snapshot, report = independent_screen(demo(), model)
    assert report["retained_count"] == 2
    assert model.usage.calls == 2
    assert {p.id for p in snapshot.papers} == {"demo-paper-1", "demo-paper-2"}

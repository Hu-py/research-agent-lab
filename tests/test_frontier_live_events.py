"""No cloud calls: verify event privacy, ordering and partial failure behavior."""
import uuid
from pathlib import Path

import httpx

from research_agent_lab.frontier.live_events import (
    FrontierEventPublisher, _safe_details, check_frontier_event_store
)
from research_agent_lab.frontier.engine import FrontierConfig, run_frontier
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel


def test_private_event_allowlist_discards_agent_thoughts_and_sensitive_content():
    safe = _safe_details({
        "stage":"supervisor","decision":"evolve",
        "leader":"H003","generation":1, "matches":3,
        "reason":"DO_NOT_STORE_NEW_SCIENTIFIC_HYPOTHESIS",
        "created":["H001","H002"],
        "children":[{"id":"H004","title":"SECRET"}],
        "secret":"SHOULD_NOT_APPEAR",
        "winner":"Personal record",
    })
    assert safe == {
        "generation":1,"matches":3,"leader":"H003",
        "decision":"evolve","created_count":2,"children_count":1,
    }


def test_live_events_emit_each_completed_langgraph_node_without_replaying_model():
    snap = Snapshot.model_validate_json(
        (Path(__file__).resolve().parents[1]/"examples"/"synthetic_snapshot.json").read_text()
    )
    events = []
    memory = MemoryStore(":memory:")
    try:
        result = run_frontier(snap, BudgetedModel(FrontierMockModel(),max_calls=30),
            memory, FrontierConfig(max_generations=0,max_pairs_per_tournament=2),
            event_sink=events.append,run_id="00000000-0000-4000-8000-000000000011")
    finally:
        memory.close()
    assert result["run_id"]=="00000000-0000-4000-8000-000000000011"
    assert [e["stage"] for e in events]==[
        "independent_paper_screen","generate","elo_tournament","supervisor","scientific_gate"
    ]
    assert len(events)==len(result["event_log"])


def test_upload_uses_server_only_key_and_sequential_steps(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://safe.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY","sb_secret_fake")
    payloads=[]
    def handler(request):
        assert request.headers["apikey"]=="sb_secret_fake"
        assert "authorization" not in request.headers
        payloads.append(__import__("json").loads(request.content))
        return httpx.Response(201)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pub=FrontierEventPublisher(run_id=str(uuid.uuid4()),client=client)
        pub.started()
        pub.emit({"stage":"supervisor","reason":"PRIVATE","decision":"verify"})
        pub.finished()
    assert [p["step_index"] for p in payloads]==[0,1,2]
    assert [p["stage"] for p in payloads]==["run_started","supervisor","run_completed"]
    assert payloads[1]["details"]=={"decision":"verify"}
    assert "PRIVATE" not in str(payloads)


def test_stream_fails_open_without_contaminating_model_run(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://safe.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY","sb_secret_fake")
    def fail(request):
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        pub=FrontierEventPublisher(client=client)
        pub.emit({"stage":"generate"})
        assert pub.degraded
        assert pub.next_step==0
        pub.emit({"stage":"scientific_gate"})
        assert pub.next_step==0



def test_live_failure_code_is_opaque_and_privacy_safe():
    from research_agent_lab.frontier.live_events import safe_failure_code
    secret="PRIVATE_RESEARCH_CONCEPT"
    code=safe_failure_code(ValueError(
        "Candidate contract repair failed: INVALID_REQUIRED_FIELD "+secret
    ))
    assert code=="CANDIDATE_SCHEMA_INVALID"
    safe=_safe_details({"stage":"run_failed", "failure_code":code, "reason":secret,
                        "rejected_count":2,"no_valid_children":True})
    assert safe["failure_code"]=="CANDIDATE_SCHEMA_INVALID"
    assert safe["rejected_count"]==2
    assert safe["no_valid_children"] is True
    assert secret not in str(safe)
    assert _safe_details({"failure_code":"arbitrary raw exception"})=={}

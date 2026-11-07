"""Read-only cloud connection checks. NEVER call paid models or write database rows."""
from __future__ import annotations

import os
import sys
from dotenv import load_dotenv

from research_agent_lab.supabase_auth import supabase_url, headers
from research_agent_lab.frontier.storage import check_frontier_supabase
from research_agent_lab.portrait_store import check_profile_store
from research_agent_lab.knowledge_store import check_graph_store
from research_agent_lab.workbench_bridge import fetch_workbench_evidence
from research_agent_lab.catalog_bridge import (
    approved_catalog_from_json, merge_approved_catalog
)
from research_agent_lab.langfuse_preflight import (
    check_langfuse_connection, emit_synthetic_langfuse_trace
)
from research_agent_lab.response_cache import configured_cache
from research_agent_lab.frontier.live_events import check_frontier_event_store


def main() -> int:
    load_dotenv()
    try:
        supabase_url()
        headers()
        print("PASS: Supabase project URL + privileged API key format")
        check_frontier_supabase()
        check_profile_store()
        check_graph_store()
        print("PASS: Supabase frontier, profile and knowledge graph tables (read-only)")
        check_catalog = os.getenv("CHECK_APPROVED_CATALOG", "false").lower() == "true"
        if os.getenv("CHECK_WORKBENCH", "false").lower() == "true" or check_catalog:
            bundle = fetch_workbench_evidence()
            # Only aggregate counts are printed, no private names or source text.
            print("PASS: Workbench authorized export: achievements=" +
                  str(len(bundle.achievements)) + ", datasets=" +
                  str(len(bundle.datasets)) + ", literature=" +
                  str(len(bundle.external_papers)))
            if check_catalog:
                payload = os.getenv("TEAM_DATA_CATALOG_JSON", "")
                if not payload:
                    raise ValueError("APPROVED_CATALOG_SECRET_MISSING")
                _, counts = merge_approved_catalog(
                    bundle, approved_catalog_from_json(payload)
                )
                print(
                    "PASS: approved CUSP catalog metadata; added="
                    + str(counts["newly_added_metadata"])
                    + " skipped_duplicates="
                    + str(counts["existing_name_duplicates_skipped"])
                    + "; no raw data access"
                )
        else:
            print("SKIP: Workbench integration (CHECK_WORKBENCH=false)")
        emit_trace = os.getenv("EMIT_LANGFUSE_SMOKE_TRACE", "false").lower() == "true"
        if os.getenv("CHECK_FRONTIER_LIVE_EVENTS", "false").lower() == "true":
            check_frontier_event_store()
            print("PASS: isolated lab_frontier_events table; no writes or DeepSeek calls")
        else:
            print("SKIP: optional live event storage")
        if os.getenv("CHECK_LLM_REPLAY_CACHE", "false").lower() == "true":
            # This checks only the isolated optional table and server-side role.
            os.environ["LLM_REPLAY_CACHE_ENABLED"] = "true"
            store = configured_cache()
            try:
                print("PASS: optional private LLM response replay cache (read-only)")
            finally:
                if store is not None:
                    store.close()
        else:
            print("SKIP: optional replay cache")
        if os.getenv("CHECK_LANGFUSE", "false").lower() == "true":
            client = check_langfuse_connection()
            print("PASS: Langfuse project credentials and region; tracing enabled")
            if emit_trace:
                url = emit_synthetic_langfuse_trace(client)
                print("SENT: synthetic Langfuse trace (no model calls). "
                      "Look for research-agent-lab-trace-smoke under Tracing.")
                if url:
                    print("SYNTHETIC_TRACE_URL: " + url)
                    summary = os.getenv("GITHUB_STEP_SUMMARY")
                    if summary:
                        with open(summary, "a", encoding="utf-8") as handle:
                            handle.write(
                                "\n### Langfuse synthetic smoke trace\n\n"
                                + "[View private project trace](" + url + ")\n\n"
                                + "Only synthetic metadata; no research inputs. "
                                + "Trace visibility may lag ingestion.\n"
                            )
                else:
                    print("NOTICE: trace URL unavailable; search by "
                          "research-agent-lab-trace-smoke name.")
            else:
                print("SKIP: synthetic trace upload (opt-in unchecked)")
        else:
            if emit_trace:
                raise ValueError("Cannot emit a test trace without checking Langfuse")
            print("SKIP: Langfuse credential check")
        print("All connection checks passed. No paid DeepSeek calls, "
              "OpenAlex requests or Supabase writes were performed.")
        return 0
    except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
        # Sanitized errors from each preflight adapter intentionally omit
        # credentials and untrusted server response bodies.
        print("Connection preflight failed: " + str(exc)[:400], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

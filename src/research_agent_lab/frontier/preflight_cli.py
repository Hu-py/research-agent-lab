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
from research_agent_lab.langfuse_preflight import (
    check_langfuse_connection, emit_synthetic_langfuse_trace
)


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
        if os.getenv("CHECK_WORKBENCH", "false").lower() == "true":
            bundle = fetch_workbench_evidence()
            # Only aggregate counts are printed, no private names or source text.
            print("PASS: Workbench authorized export: achievements=" +
                  str(len(bundle.achievements)) + ", datasets=" +
                  str(len(bundle.datasets)) + ", literature=" +
                  str(len(bundle.external_papers)))
        else:
            print("SKIP: Workbench integration (CHECK_WORKBENCH=false)")
        emit_trace = os.getenv("EMIT_LANGFUSE_SMOKE_TRACE", "false").lower() == "true"
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

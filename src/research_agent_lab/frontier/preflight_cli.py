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
        print("All connection checks passed. No DeepSeek, OpenAlex, Langfuse "
              "inference or Supabase writes were performed.")
        return 0
    except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
        # Sanitized errors from each preflight adapter intentionally omit
        # credentials and untrusted server response bodies.
        print("Connection preflight failed: " + str(exc)[:400], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

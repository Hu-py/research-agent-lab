# Research Agent Lab

Independent multi-agent research experiment using **LangGraph + DeepSeek + Langfuse + Supabase**. This public repository is separate from [Research Opportunity Workbench](https://github.com/Hu-py/research-opportunity-workbench); the original application's code and data are not changed.

> **V0.1: runnable orchestration prototype.** Synthetic examples validate software wiring, not scientific novelty. Real model runs require your own DeepSeek API key and a human-approved, privacy-filtered evidence snapshot.

## What exists

- Three comparable workflows on **exactly the same** frozen paper/portrait/data evidence: single Agent, fixed multi-Agent rounds, dynamically stopped multi-Agent rounds.
- Independent problem / method / data hypothesis generators; adversarial reviewer; iterative revision; independent numeric evaluation.
- Programmatically reject unknown paper/dataset references, invalid model scores and incomplete critiques.
- Per-run hard caps on model calls / conservatively reserved tokens / paper input count.
- Optional Langfuse generation traces, **redacted by default**.
- Optional isolated Supabase run storage with SQL schema.
- Offline deterministic mock mode, unit tests and GitHub Actions CI.

## 1. Install (Python 3.11+)

    git clone https://github.com/Hu-py/research-agent-lab.git
    cd research-agent-lab
    python -m venv .venv
    source .venv/bin/activate
    pip install -e '.[dev,observability]'

For Windows, activate with .venv\Scripts\activate.

## 2. Run offline smoke test (no keys)

    python -m research_agent_lab.cli --snapshot examples/synthetic_snapshot.json --mode all --mock --max-rounds 2 --out outputs/mock-compare.json
    python -m pytest -q

Modes: single, fixed, adaptive, all. The mock outputs are fabricated and clearly marked.

## 3. Run with real DeepSeek

Create .env from .env.example and fill DEEPSEEK_API_KEY. To use the default Langfuse Cloud tracing, fill both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (optional). **Never commit .env.**

Prepare a JSON snapshot with the structure of examples/synthetic_snapshot.json, replacing the synthetic paper citations and metadata with real **human-approved** evidence. Set provenance to approved_export.

    python -m research_agent_lab.cli --snapshot /path/to/approved_snapshot.json --mode adaptive --max-rounds 3 --out outputs/real-run.json

By default, DEEPSEEK_MODEL=deepseek-flash. Set DEEPSEEK_MODEL=deepseek-v4-pro for more advanced evaluation. The implementation uses current DeepSeek model identifiers, not retired deepseek-chat/reasoner aliases.

## 4. Optional Supabase test project

Create a **separate** Supabase test project, execute sql/001_lab_tables.sql in its SQL editor, and set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in local .env. Then run with --persist. This flag explicitly writes the **result** JSON to public.lab_runs. Never expose the service-role key in a client/browser. Supabase is not required for local runs.

## 5. Interpret the results

The JSON output includes agent candidates, objections, score trajectory, final selected hypothesis, evidence IDs, invocation counts, token reservations and (if provided by DeepSeek) real input/output token usage. All ideas retain novelty_verified=false, data_access_verified=false and human_review_required=true.

### Important scope limits

V0.1 **does not yet** connect live OpenAlex, automatically read the original Supabase database, schedule daily 80-paper jobs, implement human feedback-driven learning, or deploy a web UI. Those require safe integration and experimental evaluation, not an implicit side effect of running this prototype. The current MAX_MODEL_CALLS ceiling is **per run**, not an atomic daily budget.

Full integration and security notes: docs/architecture.md.

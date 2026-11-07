# Research Agent Lab V2.0 — Meta Supervisor × four nested loops

**Status: executable architecture rehearsal, not a deployed paid research workflow.**
This release adds actual compiled nested LangGraph graphs and deterministic
safety contracts. It is opt-in and does NOT replace the existing
frontier/engine.py, live-frontier.yml GitHub Actions workflow, or Vercel UI.

## Architecture / 总体设计

~~~mermaid
flowchart TB
  Start[Authorized Research Context] --> Meta{Meta Supervisor}
  Meta -->|EVIDENCE| L
  subgraph L[Loop 1 - Evidence / 文献小循环]
    L1[Search] --> L2[Independent Review] --> L3{Evidence Diagnose}
    L3 -->|No usable papers, bounded| L4[Rewrite Query] --> L1
  end
  L --> Meta
  Meta -->|FORMULATION| F
  subgraph F[Loop 2 - Formulation / 选题小循环]
    F1[Generate hypotheses] --> F2[Deterministic Feasibility] --> F3{Feasibility Diagnose}
    F3 -->|Unmet verified schema| F4[Targeted Reviser] --> F2
  end
  F --> Meta
  Meta -->|COMPETITION| C
  subgraph C[Loop 3 - Competition / 竞争小循环]
    C1[Reversed-Order Debate] --> C2[Scientific Critic] --> C3{Critique Diagnose}
    C3 -->|Substantive critique| C4[Evolve] --> C5[Feasibility Recheck] --> C1
  end
  C --> Meta
  Meta -->|VERIFICATION| V
  subgraph V[Loop 4 - Verification / 验证小循环]
    V1[Experiment Design] --> V2[Allowlisted Executor] --> V3[Result Critic]
    V3 -->|Transient failure, bounded| V1
  end
  V --> Meta
  Meta -->|REFRAME| R[Reframe research question] --> Meta
  Meta -->|Verified enough| Out[Research Decision Report]
  Meta -->|Budget or missing rights| Stop[Actionable safe-stop report]
~~~

The *global backtracking loop* belongs to the Meta Supervisor:
- Literature exhausted: one controlled research-query reframe and retry;
  if still empty, safe stop, NEVER fabricate references.
- Feasibility failure: bounded local data/field-plan revisions; unverified
  data permission is a hard stop, NEVER infer raw-data access from a catalog.
- Competition evolution: immediate feasibility recheck. Invalid evolution
  returns to formulation rather than automatically receiving Elo.
- Scientific refutation: global return to formulation, preserving prior
  hypotheses and the contradictory observation.
- Every route has a stable reason_code, issue_codes, stage input/output
  signals and strictly bounded local/global attempts.

## Source files and what is implemented now

- frontier/v2/state.py — shared typed state and four independent repair
  budgets, global backtrack ceiling, execution cap, append-only safe events.
- frontier/v2/supervisor.py — deterministic Meta Supervisor hard guard,
  explicit cross-loop routing, stagnation and repeated-state protection.
- frontier/v2/graph.py — four **compiled nested LangGraph subgraphs**, local
  retry edges and a parent graph with global backtracks and safe termination.
- frontier/v2/driver.py — injected Agent/Tool driver contract with synthetic
  scenario implementation (zero network/model calls).
- frontier/v2/cli.py — free dry-run execution.
- tests/test_v2_architecture.py — deterministic graph and recovery tests.

Production frontier/engine.py, live-frontier.yml, Supabase tables and
Next.js launch endpoint are deliberately unchanged until the architecture
has passed independent dry-run evaluation and an authorized live adapter
is completed. V2 does NOT automatically store its fictional papers or
experiments as scientific evidence.

## Free offline rehearsal / 离线测试

~~~bash
python -m research_agent_lab.frontier.v2.cli --scenario happy_path --events
python -m research_agent_lab.frontier.v2.cli --scenario all_papers_rejected --events
python -m research_agent_lab.frontier.v2.cli --scenario recover_retrieval
python -m research_agent_lab.frontier.v2.cli --scenario recover_feasibility
python -m research_agent_lab.frontier.v2.cli --scenario experimental_refutation
python -m research_agent_lab.frontier.v2.cli --scenario executor_unavailable
pytest -q tests/test_v2_architecture.py
~~~

These scenarios use fictional papers, synthetic dataset identifiers,
and scripted scientific outputs. They prove *routing and safe termination*,
NOT that proposed research topics are correct or novel.

## Deliverable levels

A — Audited pilot: requires independent audited real execution, approved
data rights and verified findings. Cannot be achieved by the dry-run driver.

B — Synthetic method prototype: a controlled synthetic execution, not
evidence that a real-world research hypothesis is true.

C — Actionable research plan: specific next steps for permissions, data
schema, baselines and protocols; no false Elo winner.

## Next engineering gate before any paid activation

1. Build an explicitly approved ResearchDriver adapter around the existing
   OpenAlex fetcher, paper jurors, candidate generation, feasibility gate,
   Elo Judge, Critic and Scientific Validator. Separate the read-only
   bibliography from trusted raw-data access.
2. Add durable LangGraph checkpoints and idempotency keys for external model
   calls and writes. Otherwise resume could accidentally double-spend.
3. Version the objective, evidence snapshot, decisions, candidates and
   experimental protocols; render loop-level traces in protected frontend.
4. Add a read-only preflight and explicit administrator opt-in for V2.
5. Freeze data/evidence and run offline scenario comparisons vs V1, then
   separately authorize real paid A/B trials.

No loop architecture can guarantee a novel feasible empirical study in
the absence of necessary data. It can guarantee a bounded, honest and
actionable scientific work product.

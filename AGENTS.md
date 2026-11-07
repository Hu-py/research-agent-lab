# Research Agent Lab: coding-agent instructions (Hu-py)

## System boundaries
- This repository contains the production V1 Frontier research workflow and a
  separate opt-in V2 nested LangGraph architecture. Do not activate V2 for
  paid/live work as part of a routine test fix.
- Preserve data permissions, model-call budgets, scientific uncertainty,
  independent Task Evaluator checks, and the Meta Supervisor's ability to
  abstain. Never turn a synthetic pass into a real scientific claim.
- Do not use real team datasets or Supabase credentials in tests or logs.
  Do not print secret values or add credentials to Git/GitHub issues.
- If a broken test encodes a correct invariant, fix the code rather than
  weakening the assertion, suppressing a test, or increasing a budget.
- Do not change V1 production workflows, SQL schemas, or live-frontier.yml
  unless the task explicitly authorizes it.

## Local verification commands (free, no LLM/API keys)
- python -m pip install -e '.[dev]'
- python -m pytest -q
- python -m research_agent_lab.frontier.v2.benchmark
- python -m research_agent_lab.frontier.v2.stress
- python -m research_agent_lab.frontier.v2.cli --scenario all_papers_rejected --task-audit

## Continuous repair protocol
1. Reproduce a specific failure with the smallest available test.
2. Identify one root cause and record a falsifiable diagnosis.
3. Implement a minimal patch and an adversarial regression test.
4. Rerun the targeted test, the full suite, benchmark and stress suite.
5. Report: failing behavior, root cause, exact files changed, tests passed,
   remaining limitations and whether any safety assertion was modified.
6. Stop without a code change if no failure is reproducible; do not invent
   an improvement or optimize for higher Elo alone.

## Review and deployment
- Work through a dedicated branch and pull request; never force-push main,
  merge without review, or auto-approve production deployment.
- GitHub Actions Codex fixes must keep the model key isolated from
  repository-write permissions. Test and PR promotion run without that key.

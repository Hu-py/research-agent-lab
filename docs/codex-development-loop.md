# Automated development loop — Research Agent Lab

## Two separate loops

**Free evaluation.** Every code push/PR runs the current unit tests, 11
scripted control cases and a new 33-case stress suite (11 scenarios ×
minimal/default/exploratory resource envelopes). Machine-readable JSON
reports are published as GitHub CI artifacts. These tests check architecture
and resource invariants, NOT real scientific topic quality.

**Optional coding repair.** The workflow
`.github/workflows/codex-v2-repair.yml` invokes
`openai/codex-action@v1` to reproduce a deterministic failure, propose
a bounded change in V2 source/tests, and serialize a patch. A distinct
job with no model API key reruns tests and opens a review-only PR.
No automatic merge, no real research data, no DeepSeek experiment.

## Enable a manual Codex test

1. GitHub Settings → Secrets and variables → Actions → Secrets:
   configure `OPENAI_API_KEY` (OpenAI API key, not a Plus login or
   DeepSeek token). Never paste it into chat or Git.
2. GitHub Settings → Actions → General → Workflow permissions:
   enable **Allow GitHub Actions to create and approve pull requests**
   for the PR job. If forbidden at the organization level, inspect the
   patch artifact and use an authorized GitHub App instead.
3. Actions → Codex V2 CI Repair (opt-in; PR only) → Run workflow.
   Codex is instructed to leave files unchanged if no failure is
   reproducible; in that case the workflow makes no PR.

## Optional automatic repair of failed main CI

Set repository Actions **Variable** `CODEX_AUTOFIX_ENABLED=true` only
after the key is installed and budgets are understood. The trigger
requires the Python smoke tests workflow to FAIL on the SAME repo's
main branch. PR/fork failures never invoke the repair, and the auto
repair PR cannot recurse into another Codex invocation.
Unset or change this variable to `false` to disable automatic billing.

## Why Codex previously may not have pushed

Codex Cloud must use a published environment that explicitly checks out
`Hu-py/research-agent-lab`, with the correct GitHub account connected
and permission to push branches. Connecting GitHub in normal ChatGPT does
not automatically connect a separate Codex Cloud environment.

See `AGENTS.md` for coding-agent instructions and accepted tests.

## Scientific honesty

A green CI proves a **controlled software contract** only. Published
academic novelty, data rights, team capability and empirical study
feasibility require independent evidence. Codex's test-fix loop is
not authorized to run any paid scientific discovery experiment.

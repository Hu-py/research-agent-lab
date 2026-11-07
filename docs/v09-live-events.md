# V0.9: private per-node live observation

The existing Research Atlas dashboard currently replays completed runs from
`lab_frontier_runs`. V0.9 adds optional real-time **completed-node** streaming
for new paid Research Agent Lab runs.

## Mandatory one-time isolated Supabase setup

Run [007_frontier_live_events.sql](../sql/007_frontier_live_events.sql) in
the **Research Agent Lab** Supabase SQL Editor. This is a new table; no existing
data or profile tables are changed. It must not be run on the separate
Research Opportunity Workbench database.

Then run [Verify Research Lab Connections (no AI calls)](
../.github/workflows/verify-connections.yml) with
`check_frontier_live_events=true`. This is read-only.

## Enable real live run telemetry

Run [Live Research Agent Lab](
../.github/workflows/live-frontier.yml) with
`stream_live_events=true`, `save_supabase=true`, and your usual approved
`workbench_sync` evidence. Default is **false** for safety.
Existing experiments are not changed or charged.

The isolated `lab_frontier_events` table stores:
- Stable run UUID created **before** model calls begin.
- Sequential completed node stages (and run_started/completed/failed markers).
- Server-recorded time for each write and a fixed allowlist of safe counters,
  candidate IDs and Supervisor *action type*.
- No model prompts, reasoning text, paper abstracts, team data descriptions,
  sources, or research titles.

The writer records the phase immediately after LangGraph reports its
completion via `stream_mode="values"`; it is **not** synthetic progress.
A node with several agent calls is updated after the whole node completes,
not after each internal call. There is no need to invoke extra DeepSeek
models for monitoring.

Event upload is best-effort. A temporary telemetry outage cannot
throw away a successfully completed paid scientific experiment. A failed
upload produces a generic warning and disables further telemetry attempts
in that run. SQL preflight prevents a missing table from reaching inference.

## Frontend access

In Vercel, set these **server-only** env vars:
- `RESEARCH_LAB_SUPABASE_URL` (separate lab project root)
- `RESEARCH_LAB_SUPABASE_SECRET_KEY` (separate project's private secret key)

Vercel's team-authenticated route reads recent `lab_frontier_events`
records every few seconds; these entries are not anonymous Supabase
or public GitHub artifacts. Client-side field allowlisting prevents
model outputs or raw CUSP files from being delivered.

## Notes on interpretation

The view records actual node-completion order with database timestamps,
but not token-level progress or private chain-of-thought. It should not
call this streaming during portrait synthesis, which happens before the
frontier graph starts. For older V0.6/V0.7/V0.8 runs, only historical
replay is possible.

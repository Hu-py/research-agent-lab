# V0.4 — Evidence-first research portrait

## Existing workbench findings

The original research-opportunity-workbench repository has:

- backend/profile_database.py: database_draft and matched_evidence use existing
  research lines, tags, titles and keyword/topic matching. This is NOT a
  scientifically verified research capability analysis.
- backend/profile_intelligence.py: optional LLM portrait drafts and version
  reviews, but these inherit any mistakes or missing evidence in input.
- backend/repository.py: team_achievements has verified outputs and references,
  but abstracts/method details are not systematically verified there.
- backend/cusp.py: dataset catalogue includes description, spatiotemporal
  coverage and prior_research, but lacks a verified complete field inventory.

Do not describe model-inferred expertise from paper titles as verified skills.

## New evidence-first multi-agent process

1. Curator: re-cluster OWN verified team outputs and PUBLIC, authorized dataset
   metadata into evidence-linked research problem lines.
2. Independent critic: find unsupported method claims, missing historical
   outputs, data access uncertainty and anchoring to the old team profile.
3. Reviser: correct the portrait, keep exact achievement and asset source IDs.
4. Selector: choose the next promising, testable line based on prior research.
5. Existing frontier graph: OpenAlex research -> independent literature jurors
   -> Elo competition -> Supervisor -> hypothesis revisions & science validation.
6. Historical portrait versions: save to isolated Supabase
   lab_profile_versions, never overwrite the source workbench's official profile.

The output explicitly distinguishes title_based_inference,
described_in_verified_team_outputs and data_only_unverified. A registered
dataset never implies guaranteed legal access or complete fields.

## Actual database access is currently blocked

The original Render PostgreSQL instance blocks external connections through
an empty IP allowlist. Never weaken security just to create an AI portrait.
This development has reviewed the source code and a PUBLIC curated example
bibliography but has not read the LIVE team's official portrait rows.

The repo includes a read-only authorized exporter:

    python scripts/export_workbench_evidence.py \
      --source-repo /authorized/path/research-opportunity-workbench \
      --out /private/place/team-evidence.json \
      --bundle-id research-team

Run it only in the original database's trusted environment with DATABASE_URL
set and original source repo available. It uses a read-only application
Session, does NOT call session_factory/create_all, does not mutate original
records, and emits no raw data rows or confidential file paths.

The first export has sharing_approved=false and is INELIGIBLE for cloud LLM.
Inspect it carefully and ONLY if publication-safe metadata are approved, rerun
with --approve-public-safe-export.

The exporter automatically excludes internal/restricted datasets and all
unknown field lists, data holders, file paths and raw data records. Full
database tables with sensitive information must NEVER be pasted into a
public GitHub repository or added to a browser client.

## Cloud integration after a separately authorized export

In GitHub Actions Secrets, set TEAM_EVIDENCE_JSON to the JSON content of the
explicitly approved exporter output. GitHub's per-secret size cap applies.
Do not add the file to the repository.

In the isolated Supabase research-agent-lab project execute once:

    sql/003_profile_versions.sql

Your earlier 002_frontier_tables.sql remains unchanged.

Run Actions -> Live Research Agent Lab (manual):
- evidence_source: team_evidence
- max_generations: 0 (first real test)
- max_papers: 4
- max_pairs: 1
- save_supabase: true

The workflow first validates both Supabase tables, creates/reuses a versioned
research portrait, selects a line, and continues through the existing frontier
hypothesis competition. Private team data and the full report are not uploaded
as public GitHub artifacts. Only minimal status and run identifiers appear in
Actions logs. This does NOT push anything to a human automatically.

Stored portraits are provisional and never silently overwrite the original
workbench. Expert review happens AFTER generated opportunities have completed.

## Continuous review conditions

If new team evidence arrives and the approved JSON Secret is updated, the
evidence hash changes and the next run regenerates the portrait, preserving
previous versions. If evidence has not changed, the previous version is reused
to reduce repeat DeepSeek charges. New external papers are discovered on every
frontier --discover execution.

At V0.4 there is NOT YET a secure automatic synchronization from the original
Render database into GitHub Actions. A stable administrator-authorized export
bridge should be developed before claiming autonomous team database refresh.

## Current scientific limits

The code does not read paper full text by default, verify that the team
implemented methods that appear in abstract/keywords, guarantee a dataset's
legal access, establish originality, or demonstrate that adaptive agents
outperform a controlled single-agent baseline.

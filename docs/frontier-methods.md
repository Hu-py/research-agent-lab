# Frontier Lab V0.2 — Methods, limits, and reproducibility

## Research inspirations (not a reproduction)

- Co-Scientist: specialized hypothesis generation, reflection, proximity, pairwise
  debates with Elo ranking, version evolution, supervisor and meta-review.
  https://www.nature.com/articles/s41586-026-10644-y
- EvoScientist: ideation and experimentation memories, including failures, used
  to help later runs avoid repeating poor strategies.
  https://arxiv.org/abs/2603.08127
- The Agentic Scientist: supervisory control of research stages, scientific
  verification and sandboxed experimentation.
  https://arxiv.org/abs/2610.18933

## Four-layer graph

    START -> [optional OpenAlex discovery] -> paper juror A/B [+ adjudicator]
          -> problem / method / data hypothesis generation
          -> proximity -> two-sided Elo comparison
          -> supervisor -> [evolve | expand | rollback | verify]
             evolve -> immutable refine/fuse descendants -> Elo -> supervisor
             expand -> new contrasting idea -> Elo -> supervisor
             rollback -> archive latest generation -> science gate
             verify -> science gate -> optional fixed-code CSV pilot
          -> final research package + local experience memory
          -> optional isolated Supabase summary

Programmatic checks enforce budgets, rounds, evidence IDs, data field names,
required baselines, and final scientific review. The supervisor is NOT allowed
to execute arbitrary code, bypass gates, or set unlimited budgets.

## Evidence and scientific validity

- OpenAlex bibliographic metadata is obtained via a bounded external request only
  if the operator explicitly supplies --discover and a valid OPENALEX_API_KEY.
  The provider supplies paper IDs, DOIs, venues and retraction flag. A metadata
  match does NOT verify scientific claims, novelty, causal inference or datasets.
- Two independent Agent assessors vote on each paper; disagreement is sent to a
  third LLM. Unverifiable/unsupported entries remain untrusted.
- Each hypothesis references registered paper and dataset IDs. A generated
  experiment field mapping cannot reference unregistered fields.
- The Elo score measures pairwise **model preference**, NOT scientific merit.
  The same pair is judged in reversed presentation order to reduce position bias.
- Previous hypotheses remain available as immutable ancestry, and rolled-back
  candidates are archived instead of erased.
- The optional CSV pilot uses fixed Python and train-only fitting with a stable
  grouped holdout. It supports only a single numeric feature and group column.
  It is not a full experiment or evidence for a publication-grade claim.
- Even candidates eligible for human review always have
  novelty_verified=false, experimental_claim_verified=false, and no automatic
  human push. Human input comes only AFTER the package is produced.

## Experience adaptation

Local ignored SQLite stores summarized ideation/failure/experimental outcomes,
the last runs and human review. UCB chooses balanced/novelty/feasibility policy
from explicit **human** novelty, feasibility and decision feedback, never from
an LLM self-grade. This is not neural fine-tuning or RL.

Supabase V0.2 persists compact result summaries only; remote memory retrieval,
cross-machine synchronization and authenticated human-review GUI are future work.
Model calls / tokens are bounded **per run**, not globally per day.

## Validation protocol before making scientific claims

Run all three V0.1 baselines (single/fixed/adaptive) and the V0.2 frontier with
the same fixed, non-sensitive paper set. Equalize model IDs and inference budgets
as much as possible, randomize output presentation, and use independent blinded
domain experts. Compare relevance, novelty, feasibility, falsifiability,
reference correctness, and actual cost. Add ablations for Elo, proximity,
memory, supervisor and cross-role diversity. The existing mock tests validate
program behavior, not empirical superiority of V0.2 over any baseline.

## Public repository security

Never commit .env, API credentials, Supabase service-role tokens, raw team
research data, private profiles, pilot CSV or full model traces. Local outputs
and memory are ignored. Langfuse defaults to redacted metadata-only observations.
All bibliographic content must be treated as untrusted reference text.

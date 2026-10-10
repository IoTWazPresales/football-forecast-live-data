# HBT operational closeout — 10 October 2026

Evaluation: 2026-10-10T18:07:46.421843Z (UTC). Research branch only.

## Verified outcome

NO_EXECUTABLE_BETS. The refresh discovers 345 fixtures and reconciles all 25 previously scored fixtures. It exposes 368 modelled selections: 200 main markets and 168 event selections. Six scored fixtures are still before kickoff at the evaluation time; all six have a new immutable capture. Two have independently checked official kickoffs. Zero markets have verified current bookmaker prices; zero funded singles or chains.

The count fell from 392 after the forward run refreshed the live intelligence. Missing or unvalidated event lines are excluded; the higher earlier count is not a coverage target. Every previously scored fixture remains accounted for.

## Repairs in this continuation

- Date-scoped scanner and quote files prevent a forward run from replacing today’s inputs. Compatibility latest files remain available. Every desk includes source paths and SHA-256 input hashes.
- Provider requests run in a bounded six-thread pool; output preserves configured source priority regardless of completion order. Unknown timezone timestamps remain unknown.
- Two explicit senior Eredivisie provider aliases preserve the frozen model’s existing Ajax/NEC identity. Original provider names remain recorded. No model state, coefficients, parameters or runtime payloads were changed.
- The official Ajax schedule confirms 21:00 Amsterdam = 19:00 UTC = 21:00 Johannesburg. The new exact export now uses the agreeing ESPN kickoff. The original 21:00 UTC historical capture is preserved byte-for-byte.
- The official Real Madrid announcement confirms 21:00 CEST = 19:00 UTC. Proofs retain URLs, retrieval timestamps, response hashes and limited extraction text. Official-source coverage is explicitly limited to these adapters.
- Same-provider relabelling, future proof clocks, post-start evidence, duplicate/conflicting proof and disagreement with forecast kickoff cannot pass execution checks.
- Refreshes write new immutable files in captures/ and a hash-verified current pointer. They exclude started matches and bind the exact frozen export hash. The original prospective card is not overwritten.
- Historical learning cannot use an execution surface from a different capture. Original-card forensics remain historical; refreshed versions are retained for subsequent version-aware analysis and are not silently counted as new independent clean training examples.
- Research writers share a concurrency group. The publisher replays disjoint upstream updates in an isolated worktree, checks staged desk provenance, rejects conflicting generated outputs and protected capture/parameter edits, and never force-pushes. Daily evidence is archived before publishing.

## Current upcoming scored fixtures

| Fixture | UTC kickoff | Johannesburg | Official independent proof |
|---|---|---|---|
| 1. FC Nürnberg vs VfL Wolfsburg | 18:30 | 20:30 | Missing |
| AS Monaco vs Toulouse | 18:45 | 20:45 | Missing |
| Lorient vs Paris FC | 18:45 | 20:45 | Missing |
| Paris Saint-Germain vs Le Mans | 18:45 | 20:45 | Missing |
| AFC Ajax vs NEC | 19:00 | 21:00 | Verified |
| Real Madrid vs Villarreal | 19:00 | 21:00 | Verified |

All rows are WATCH/R0. Timing verification is one prerequisite, not a funded recommendation.

## External blockers and scientific work still required

1. Current attributable Betway quotes. ODDS_API_IO_KEY is still unconfigured. Configure it as a GitHub Actions secret, or provide audited current quote rows under the documented quote contract. Prices never become football model features.
2. The complete Forecast Lab/Fusion and goal-distribution runtime or project source. The accessible HBT repository contains only the recovered L0 snapshot bridge; a scoped GitHub repository search found no other accessible HBT/football source repository. BTTS/totals cannot be reconstructed from 1X2 probabilities.
3. Both confirmed XIs and regenerated final model probabilities with matching feature lineage. Future fixtures are still PRE-XI or lack captured match intelligence. Four of the six also lack independent official kickoff coverage.
4. HBT-1.4 chronological full-stack interaction training, family ablation and untouched holdout/reliability evidence. A collection registry entry is not evidence that a feature has been implemented, causally validated or promoted.
5. A validated dependence/portfolio model and per-market prospective calibration. Chains remain research only; maximizing payout is not maximizing win probability.

## Validation

- 42 regression tests pass, including a real bare-Git publication race test, conflict rejection, source-hash drift, immutable capture preservation, pointer tampering, model identity, timezone and proof lineage.
- Frozen runtime and snapshot hash verification pass. Golden maximum absolute error is 1.11e-16 against the unchanged 1e-9 limit.
- All ten desk input hashes are verified. The original October 10 capture and event/player parameter artifacts match the saved research revision byte-for-byte.
- Workflow YAML parses; forensic v2/v3 self-tests pass.
- The local target-date pipeline completed: scanner, exact bridge, reconciliation, official crosscheck, quote status, immutable refreshed capture, governed execution surface and betting desk.
- Research workflow changes do not change workflow definitions on the default branch. Default-branch scheduled definitions require a separate reviewed promotion before these orchestration safeguards apply there.

HBT scope only. No data or model assumptions from CIP, EIF, Reclaim, ASUS, Growbox or Power BI were used.

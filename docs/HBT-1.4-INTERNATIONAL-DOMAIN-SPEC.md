# HBT-1.4 International / Domain Adapter

Status: research challenger. This extension does not modify HBT-1.1.2, the exact frozen runtime, or domestic HBT probabilities.

## Objective

Treat HBT as a football-intelligence engine with domain-specific calibration rather than a model permanently limited to a small league allow-list. Senior men's internationals are the first new domain.

## Domain taxonomy

Every discovered fixture is classified before predictive eligibility:

- `CLUB_LEAGUE_OR_UNRESOLVED`
- `CLUB_CUP`
- `CLUB_FRIENDLY`
- `NATIONAL_COMPETITIVE`
- `NATIONAL_FRIENDLY`
- `NATIONAL_YOUTH`
- `NATIONAL_WOMEN`
- `CLUB_YOUTH`
- `CLUB_WOMEN`

Domain identity and predictive promotion are separate decisions. Reclassifying a fixture as a senior international does not automatically make it a funded HBT bet.

## International structural challenger v1

The first international challenger supplies the missing domain-specific structural layer while preserving the HBT-1.4 intelligence architecture.

Inputs:

- pinned senior-men's full-international match history;
- causally prior completed international results used to refresh the current team state;
- tournament importance for sequential team-strength updates;
- neutral/home context where known;
- opponent-adjusted structural strength;
- recent international goals, results, opponent strength and freshness.

The output is a three-way H/D/A probability vector plus 1X, X2, 12 and DNB derived R0 markets.

No bookmaker price is read by this model.

## Validation

Chronology is mandatory:

- pre-2023 history establishes the evolving structural state and fixed historical baseline;
- 2023-2024 is the parameter-selection window;
- 2025 onward is the untouched holdout window for the selected calibration;
- competitive and friendly internationals are reported separately.

Metrics:

- multiclass log loss;
- multiclass Brier score;
- top-pick accuracy;
- top-pick calibration error.

The challenger must improve proper probabilistic scores on holdout before it can advance. That is necessary but not sufficient.

## Promotion gates

International rows remain `R0_SHADOW_RESEARCH` until all of the following are true:

1. chronological holdout improves the defined proper scoring metrics against the frozen comparison baseline;
2. current domain identity is verified as senior men's international football;
3. causal feature generation is audited;
4. clean prospective slates accumulate and confirm calibration;
5. HBT-1.4 interaction/ablation work establishes which universal intelligence families transfer safely;
6. bookmaker prices remain downstream of the frozen football probability;
7. execution policy is explicitly promoted by a governed change.

No workflow may auto-promote or auto-fund this challenger.

## Intelligence expansion roadmap

The structural adapter is phase 1. The following HBT families are then transferred into the international domain with missing kept as missing, never zero:

- expected/confirmed XI and squad continuity;
- club-to-country player contribution transfer;
- tactical matchup;
- goalkeeper / shot-stopping context;
- set pieces;
- referee;
- weather/venue and neutral-site handling;
- workload, travel and camp-arrival congestion;
- competition-state / qualification pressure;
- bench/substitution depth;
- team-to-score attribution.

Each family remains subject to standalone, interaction, leave-one-family-out and missing-data tests before receiving predictive weight.

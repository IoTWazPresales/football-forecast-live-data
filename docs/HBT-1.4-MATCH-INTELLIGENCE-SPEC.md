# HBT-1.4 Match Intelligence

Status: research/challenger only. HBT-1.1.2 remains the frozen deployed football model until HBT-1.4 passes the gates below.

## Objective

Build a single pre-match intelligence stack that preserves every existing HBT signal, adds the missing football-intelligence families, tests each family both alone and in interaction with the rest of the stack, and only then exposes a new challenger forecast for prospective R1 testing.

The betting layer remains downstream. Bookmaker odds are never model inputs.

## Non-negotiable rules

1. Point-in-time causality: a target match may never use information created after kickoff.
2. Missing is not zero.
3. Existing HBT layers must remain available and parity-tested.
4. A family that fails alone is not deleted. It remains in the feature registry and is tested inside the full interaction model and through leave-one-family-out ablation.
5. A family is allowed a zero predictive weight if the full-stack evidence says it harms unseen forecasts. Presence is mandatory; non-zero influence is not.
6. Expected-XI forecasts are provisional. Confirmed-XI forecasts are final when both official starting XIs are available.
7. Player shots/SOT/goalscorer recommendations require confirmed starters.
8. Odds, line movement, vig and bookmaker consensus belong to the decision layer only.

## Intelligence families

### Existing / preserved
- structural team strength / league priors
- recent performance and non-penalty xG
- PRE-XI and confirmed-XI continuity/replacement quality
- availability and lineup continuity research
- workload/rest/short-turnaround context
- score distribution / 1X2 / totals / BTTS / team totals
- corners
- yellow cards
- team shots
- team shots on target
- player shots / SOT / anytime scorer
- formation context
- travel context
- manager tracking

### HBT-1.4 additions
- tactical matchup: PPDA, PPDA allowed, deep entries, deep allowed, npxG/npxGA interaction, formation-role interaction
- shot-stopping / goalkeeper context: confirmed GK identity plus team/GK shot-stopping residual where history supports it
- set pieces: corner/set-piece shot and xG creation/concession where source data identifies shot situation
- referee: historical card-rate and foul/card environment with shrinkage to league priors
- weather/venue: pre-kickoff forecast for live use; historical weather is not promotion-eligible unless the historical source is point-in-time forecast data
- congestion/fatigue: rest, 7/14/21-day load, short turnarounds and travel interaction
- motivation/competition state: pre-match table position, points gaps, title/Europe/relegation pressure proxies
- bench/substitution behaviour: confirmed bench depth plus prior substitution timing/attacking response where causally available
- deeper player-to-team impact: expected/confirmed XI attacking contribution, defensive continuity and goalkeeper continuity
- team-to-score attribution: explicit component-level explanation of each team's scoring probability

## Validation design

Every candidate family is evaluated in four ways:

1. **Standalone residual test** against the frozen HBT baseline.
2. **Full-stack interaction test** with all intelligence present.
3. **Leave-one-family-out ablation** to measure contribution conditional on the rest of the stack.
4. **Missing-data test** to confirm neutral degradation rather than missing-as-zero contamination.

Primary metrics:
- multiclass log loss
- Brier score
- top-pick accuracy
- calibration error / reliability
- team-to-score binary log loss and Brier
- market-family log loss for totals/BTTS/event/player markets

Chronology:
- earlier block: model fitting
- middle block: feature/regularisation selection
- latest untouched block: final promotion decision

No feature family may be promoted solely because it improves accuracy while worsening proper probabilistic scoring on both selection and holdout.

## Readiness states

- `PRE_XI_PROVISIONAL`: expected XI only; recommendations may be shown as WATCH.
- `CONFIRMED_XI_PARTIAL`: one or both official XIs present but a high-impact source is missing.
- `CONFIRMED_XI_READY`: both official XIs detected, player model refreshed, market scan rerun.
- `CONTEXT_ONLY`: collected but not validated for probability changes.
- `REJECTED_STANDALONE_RETAINED`: failed standalone promotion; retained for interaction/ablation.
- `PROMOTED`: improved the defined chronological gates and is allowed predictive influence.

## Definition of done before live betting resumes

HBT-1.4 is not ready for another R1 test until:
- all intelligence families are represented in the registry;
- historical feature generation is causal and audited;
- full-stack interaction training completes;
- leave-one-family-out ablations complete;
- untouched holdout metrics are produced;
- old HBT layer parity checks pass;
- confirmed-XI state transition works in the live collector;
- current market probabilities are regenerated after lineup confirmation;
- recommendation output includes source/readiness and explanation of why the bet is preferred.

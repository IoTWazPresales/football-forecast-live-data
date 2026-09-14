# HBT L5 real-money test log

Research-only betting/value evidence. This file does **not** modify HBT-1.1.2 football probabilities.

## Observed live slip — 13 Sep 2026 — R1 multibet

Status: **observed, not pre-registered**. Do not retrofit a selection rule to this ticket.

Betway slip observed from user screenshot, placed 2026-09-13 19:28:

| Leg | Betway odds | Frozen HBT-1.1.2 state | Result |
|---|---:|---|---|
| Napoli win vs Bologna | 1.15 | C tier · PRE-XI/Fusion · P(win)=0.5704017524 | WON 1-0 |
| Getafe win vs Deportivo La Coruna | 2.95 | Avoid tier · P(win)=0.4668553805 | LOST 1-1 |
| PSG win at Brest | 1.22 | C tier · PRE-XI/Fusion · P(win)=0.5000946612 | WON 1-0 |
| Como win vs Parma | 1.21 | A tier · PRE-XI/Fusion · P(win)=0.7716480675 | pending at observation time |

Ticket odds: 5.00. Stake: R1.00. Potential return displayed: R5.01 (Betway return display R5.04). The accumulator is already lost because Getafe drew, but Como remains useful prospective model evidence and must still be settled in the research log.

Frozen-model joint probability under a simple independence approximation: ~0.10276 (fair odds ~9.73). This is descriptive only; same-ticket independence is not treated as validated betting logic.

## Real-money protocol — registered 14 Sep 2026 before today's Serie A kickoffs

Purpose: start clean prospective **real-money** evidence without contaminating the football model.

Rules:
1. Football probabilities remain frozen HBT-1.1.2 outputs; bookmaker prices never enter the football model.
2. Only current clean Fusion rows may enter the primary live-money selection pool; stale/C1/L0-fallback rows are excluded from the primary protocol.
3. Do not chase raw HBT-vs-bookmaker EV longshots. The historical EPL audit showed this rule was badly miscalibrated.
4. A/B tier plus market directional agreement is necessary but not sufficient: price quality is checked separately through L5.
5. A valid test outcome can be **NO BET**. No bet is forced merely to generate action.
6. One market per fixture in the primary protocol; no same-game correlation multiplication.
7. Stake remains nominal (R1 test scale) until a prospectively validated betting rule exists.

### Frozen HBT candidates for 14 Sep Serie A

- Como vs Parma: A · PRE-XI FUSION · H 0.7716480675 / D 0.1562329762 / A 0.0721189563.
- Torino vs Roma: B · PRE-XI FUSION · Roma 0.6223830854.
- Inter vs Udinese: A · PRE-XI FUSION · Inter 0.8425259182.

Current price audit at registration time: public Betway comparison feeds show approximately Como 1.22, Roma 1.50, Inter 1.25. All three directions agree with HBT, but the prices are shorter than the contemporaneous de-vig market fair estimates (approximately Como 1.32, Roma 1.67, Inter 1.35). Therefore the **primary value protocol is NO BET at current prices**. This is a valid live-money test decision, not a failed attempt to find a bet.

If a real-money wager is placed despite the value gate, it must be logged separately as a **forecast-only/action test**, not relabelled as a validated value bet.

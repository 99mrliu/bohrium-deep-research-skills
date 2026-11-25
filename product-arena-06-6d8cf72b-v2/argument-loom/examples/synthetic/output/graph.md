# Argument graph

**合成示例 / non-official / SYNTHETIC EXAMPLE — not an official answer.**

Source `synthetic-lumen-beads`; graph `synthetic-lumen-argument-v1`. Edges preserve typed argument relations and source section order.

| Edge | Type | From | To | From section → To section |
|---|---|---|---|---|
| S0 | supports | E1 | C0 | results → abstract |
| S1 | supports | E1 | C1 | results → results |
| S2 | supports | E1 | C2 | results → conclusion |
| S3 | supports | E2 | C1 | results → results |
| S4 | supports | E2 | C2 | results → conclusion |
| W0 | warrants | W1 | C0 | methods → abstract |
| W3 | warrants | W1 | C1 | methods → results |
| W4 | warrants | W1 | C2 | methods → conclusion |
| W5 | warrants | W2 | C2 | discussion → conclusion |
| L0 | limits | L1 | C0 | discussion → abstract |
| L3 | limits | L1 | C1 | discussion → results |
| L4 | limits | L1 | C2 | discussion → conclusion |
| M0 | motivates | B1 | C1 | introduction → results |
| T0 | transitions_to | T1 | C1 | introduction → results |
| M1 | motivates | C1 | C2 | results → conclusion |

## Core-claim coverage

| Claim | Section | Evidence | Warrants | Limit status | Limitations | Semantic status |
|---|---|---|---|---|---|---|
| C0 | abstract | E1 | W1 | reported | L1 | reviewer_confirmed |
| C1 | results | E1, E2 | W1 | reported | L1 | reviewer_confirmed |
| C2 | conclusion | E1, E2 | W1, W2 | reported | L1 | reviewer_confirmed |

## Audit boundary

A structural PASS is not a semantic-truth certificate. Read the anchored quotes and notes for the recorded human/agent review status.

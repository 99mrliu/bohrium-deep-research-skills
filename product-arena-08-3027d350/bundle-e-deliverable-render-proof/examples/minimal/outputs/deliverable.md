# Deliverable (rendered reading view)

> Each block carries an inline anchor tag `[[p{page}-b{seq}]]` mapping back to page/column/bbox in the source PDF. Header/footer blocks are relocated to the appendix below; nothing is dropped.


## Page 1

### [[p1-b2]] A Fully Synthetic Paper Used Only to Exercise the Render-Proof Pipeline

<sub>kind=heading, page=1, col=0, bbox=[72.0, 70.0, 523.0, 96.0]</sub>

[[p1-b3]] Ada Sample, Ben Fixture — Institute of Fabricated Examples. This line is synthetic author metadata, not a real affiliation.

<sub>kind=body, page=1, col=0, bbox=[72.0, 104.0, 523.0, 118.0]</sub>

### [[p1-b4]] 1. Introduction

<sub>kind=heading, page=1, col=0, bbox=[72.0, 140.0, 300.0, 158.0]</sub>

[[p1-b5]] This paragraph is invented text standing in for an introduction. Its only job is to be parsed into a typed, anchored block and then rendered into the deliverables with its anchor intact.

<sub>kind=body, page=1, col=0, bbox=[72.0, 166.0, 523.0, 226.0]</sub>

[[p1-b6]] This synthetic body block intentionally has bbox=null: the renderer must still render it, and QC must warn about the missing geometry instead of crashing or dropping the block.

<sub>kind=body, page=1, col=0, bbox=n/a</sub>

[[p1-b7]] `E_render = sum over blocks of |anchors_out - anchors_in| = 0`

<sub>kind=equation, page=1, col=0, bbox=[120.0, 240.0, 475.0, 262.0]</sub>

[[p1-b8]] Figure 1 (synthetic): schematic of anchor flow from parsed blocks to rendered deliverables. No real figure exists.

<sub>kind=caption, page=1, col=0, bbox=[72.0, 270.0, 523.0, 288.0]</sub>


## Page 2

### [[p2-b2]] 2. Methods

<sub>kind=heading, page=2, col=0, bbox=[72.0, 60.0, 250.0, 78.0]</sub>

[[p2-b3]] Column one of a fabricated methods section. The two-column layout here exists only to prove that the column field survives into the anchor map and the deliverables.

<sub>kind=body, page=2, col=0, bbox=[72.0, 86.0, 285.0, 160.0]</sub>

[[p2-b4]] Column two continues the invented methods text. Every sentence is synthetic; nothing here describes real research.

<sub>kind=body, page=2, col=1, bbox=[310.0, 86.0, 523.0, 140.0]</sub>

[[p2-b5]] `recall(anchors) = |out ∩ in| / |in| = 1.0`

<sub>kind=equation, page=2, col=1, bbox=[330.0, 150.0, 500.0, 172.0]</sub>

[[p2-b6]] Table 1 (synthetic): reconciliation counters. The table itself is not included in this example.

<sub>kind=caption, page=2, col=1, bbox=[310.0, 180.0, 523.0, 198.0]</sub>

[[p2-b7]] *[UNRESOLVED — text unavailable; reason: synthetic vector figure region; upstream parse could not recover text]*

<sub>kind=unresolved, page=2, col=0, bbox=[72.0, 210.0, 285.0, 250.0]</sub>

[[p2-b8]] [1] Sample, A. and Fixture, B. (2026). Fabricated references for testing only. Synth. J. Demo 0, 1-2.

<sub>kind=reference, page=2, col=0, bbox=[72.0, 260.0, 285.0, 300.0]</sub>

[[p2-b9]] [2] Placeholder, C. (2025). Another invented citation; do not look it up.

<sub>kind=reference, page=2, col=0, bbox=[72.0, 306.0, 285.0, 340.0]</sub>

[[p2-b10]] *[UNRESOLVED — text unavailable; reason: synthetic rotated text strip; orientation not handled by upstream parse]*

<sub>kind=unresolved, page=2, col=1, bbox=[310.0, 260.0, 523.0, 290.0]</sub>


## Appendix: running headers and footers

These blocks belong to the page furniture (kind=header|footer). They are rendered here, still anchored, rather than dropped.

- [[p1-b1]] SYNTHETIC JOURNAL OF DEMO STUDIES — VOL. 0 (FABRICATED EXAMPLE) — <sub>kind=header, page=1, col=0, bbox=[72.0, 30.0, 523.0, 44.0]</sub>
- [[p1-b9]] — 1 — — <sub>kind=footer, page=1, col=0, bbox=[72.0, 760.0, 523.0, 774.0]</sub>
- [[p2-b1]] SYNTHETIC JOURNAL OF DEMO STUDIES — VOL. 0 (FABRICATED EXAMPLE) — <sub>kind=header, page=2, col=0, bbox=[72.0, 30.0, 523.0, 44.0]</sub>
- [[p2-b11]] — 2 — — <sub>kind=footer, page=2, col=0, bbox=[72.0, 760.0, 523.0, 774.0]</sub>

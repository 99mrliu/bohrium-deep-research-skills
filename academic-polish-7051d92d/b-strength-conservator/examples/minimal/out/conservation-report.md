# Conservation Report

Source: `source.md` (sha256 ebf7e5b800a84ede)

## Summary

- frozen units: 12
- edits applied: 10
- edits reverted by gates: 4
- edits rejected in review: 0
- authorized strength changes: 1
- heavy-rewrite warnings: 1

## Applied edits (what changed)

- `u0003` (agreement, batch grammar-fixes, sim 0.94, drift none)
  - orig: Methods: Primary hepatocytes was isolated from wild-type and NLRP3-knockout mice.
  - rev : Methods: Primary hepatocytes were isolated from wild-type and NLRP3-knockout mice.
  - reason: subject 'hepatocytes' is plural; 'was' -> 'were'
- `u0004` (agreement, batch grammar-fixes, sim 0.89, drift none)
  - orig: Cells was exposed to palmitic acid for 24 hours, and inflammasome activation were measured by immunoblotting.
  - rev : Cells were exposed to palmitic acid for 24 hours, and inflammasome activation was measured by immunoblotting.
  - reason: 'Cells was' -> 'Cells were'; 'activation were' -> 'activation was'
- `u0006` (tense, batch grammar-fixes, sim 0.95, drift none)
  - orig: In vivo, NLRP3-deficient mice shows reduced liver fibrosis after eight weeks of high-fat feeding.
  - rev : In vivo, NLRP3-deficient mice showed reduced liver fibrosis after eight weeks of high-fat feeding.
  - reason: 'mice shows' -> 'mice showed' (past tense, plural subject)
- `u0007` (grammar, batch grammar-fixes, sim 0.95, drift none)
  - orig: The treatment may improves insulin sensitivity in some animals, although the effect did not reach statistical significance.
  - rev : The treatment may improve insulin sensitivity in some animals, although the effect did not reach statistical significance.
  - reason: modal 'may' requires bare infinitive: 'improves' -> 'improve'
- `u0009` (grammar, batch grammar-fixes, sim 0.71, drift none)
  - orig: There is several evidences that oxidative stress amplify inflammasome signaling in vitro.
  - rev : There are several pieces of evidence that oxidative stress amplifies inflammasome signaling in vitro.
  - reason: 'There is several evidences' -> 'There are several pieces of evidence'; 'stress amplify' -> 'stress amplifies'
- `u0010` (agreement, batch grammar-fixes, sim 0.85, drift none)
  - orig: Our findings suggests that NLRP3 contribute to liver injury under these conditions.
  - rev : Our findings suggest that NLRP3 contributes to liver injury under these conditions.
  - reason: 'findings suggests' -> 'findings suggest'; 'NLRP3 contribute' -> 'NLRP3 contributes'
- `u0011` (grammar, batch grammar-fixes, sim 0.92, drift none)
  - orig: These data may has implications for the design of future therapeutic strategies.
  - rev : These data may have implications for the design of future therapeutic strategies.
  - reason: modal 'may' requires bare infinitive: 'has' -> 'have'
- `u0012` (agreement, batch grammar-fixes, sim 0.93, drift none)
  - orig: Conclusion: Further studies is needed to confirm these observations in human samples.
  - rev : Conclusion: Further studies are needed to confirm these observations in human samples.
  - reason: 'studies is' -> 'studies are'
- `u0011` (clarity-restructure, batch adversarial, sim 0.46, drift none) [warning: heavy_rewrite]
  - orig: These data may have implications for the design of future therapeutic strategies.
  - rev : This work could open new directions for the design of future therapies.
  - reason: recast the closing sentence for flow while keeping the hedged modality
- `u0010` (word-choice, batch adversarial, sim 0.92, drift strengthened) [AUTHORIZED strength change: User instructed: align claim strength with the confirmatory knockout data (suggest -> demonstrate).]
  - orig: Our findings suggest that NLRP3 contributes to liver injury under these conditions.
  - rev : Our findings demonstrate that NLRP3 contributes to liver injury under these conditions.
  - reason: user asked to align claim strength with the confirmatory knockout data

## Reverted by gates (what was refused)

- `u0007` gate=strength-gate (batch adversarial)
  - attempted: The treatment improves insulin sensitivity in all animals, although the effect was significant.
  - detail: strength drift 'negation-changed' without authorization (strength_change.authorized_by task|user + explanation); edit reverted
  - evidence: negation-changed (negation-set-changed) orig=["not"] rev=[]
  - evidence: strengthened (level-0-to-2) orig={"may": 0} rev={}
  - evidence: scope-broadened (quantifier-rank-2-to-5) orig={"some": 2} rev={"all": 5}
- `u0008` gate=strength-gate (batch adversarial)
  - attempted: Biomarker Y causes disease severity.
  - detail: strength drift 'causality-changed' without authorization (strength_change.authorized_by task|user + explanation); edit reverted
  - evidence: causality-changed (correlational-to-causal) orig={"causal_hits": [], "classes": ["correlational"], "correlational_hits": ["is associated with", "associated with"]} rev={"causal_hits": ["causes"], "classes": ["causal"], "correlational_hits": []}
  - evidence: scope-broadened (scope-condition-removed) orig=["in this cohort"] rev=[]
- `u0009` gate=strength-gate (batch adversarial)
  - attempted: There are several pieces of evidence that oxidative stress amplifies inflammasome signaling.
  - detail: strength drift 'scope-broadened' without authorization (strength_change.authorized_by task|user + explanation); edit reverted
  - evidence: scope-broadened (scope-condition-removed) orig=["in vitro"] rev=[]
- `u0001` gate=review-gate (batch adversarial)
  - attempted: Inflammation plays a central role in the progression of metabolic liver disease, but the underlying mechanisms remain poorly understood.
  - detail: missing or incomplete review record (decision + reason required); edit reverted

## Conserved hedges (what was protected)

- `u0002` kept level-2 (reporting); cues: in this study
- `u0006` kept level-2 (reporting); cues: showed, in vivo (hedge reworded at same level: shows -> showed)
- `u0007` kept level-0 (speculative); cues: may, some, not
- `u0008` kept level-2 (reporting); cues: in this cohort
- `u0009` kept level-2 (reporting); cues: several, in vitro
- `u0011` kept level-0 (speculative); cues: could (hedge reworded at same level: may -> could)
- `u0012` kept level-3 (strong); cues: confirm, in human

## Honesty boundary

Strength cues are heuristic word/phrase matches. This report
shows which edits tripped the gates and which hedges survived;
it does NOT prove that the polished text is semantically
equivalent to the source. Read the final pass yourself.

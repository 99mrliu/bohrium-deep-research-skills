# Gap patterns — deriving the research gap from the matrix

The gap paragraph is the payoff of the comparison matrix. It must be
*derivable*: a reader with the matrix in hand should be able to point at the
limitation cells that force each gap sentence. All examples below are
**SYNTHETIC** (invented PermaLig demonstration material).

## The four-link gap chain

Every gap claim should close all four links, in order:

1. **Source-supported prior capability.** What the nearest prior work
   demonstrably does, with citation and quote backing in the matrix.
   *Synthetic:* "ConsenSite scores pockets by unweighted consensus across
   homologous experimental structures, improving precision by 0.07 over
   single-structure scoring [4]."
2. **Specific remaining requirement.** The concrete condition that
   capability does not cover — drawn from a stated_limitation cell.
   *Synthetic:* "…but it requires multiple experimental structures of the
   target itself, which are unavailable for most prediction targets [4]."
3. **Why it changes the outcome.** The consequence under this manuscript's
   conditions, not a generic "this is important".
   *Synthetic:* "…so on targets whose best template is below 30% identity,
   no provided method gets consensus scoring's precision benefit."
4. **Own mechanism and actual evidence.** The contribution that closes the
   requirement, with an anchor and only the numbers the fact base states.
   *Synthetic:* "PermaLig votes each candidate pocket across up to 5
   templates weighted by per-template local quality (Fig 1), reaching 0.61
   top-1 pocket precision on the hard subset (Fig 2)."

A gap sentence that skips link 1 is an unsupported claim; one that skips
link 3 is a summary, not a gap; one that skips link 4 leaves the
contribution unmotivated.

## Counterexample-bounded gap writing

Before declaring anything "open", find the strongest counterexample: the
reference whose capability cells share the most distinctive vocabulary with
your gap (the matrix marks the top closeness-ranked references as
closest-alternative candidates — start there). Then:

1. **State its strongest relevant capability fairly** (link 1), with its
   citation.
2. **Scope it**: name the condition under which that capability does not
   apply, quoting its own stated limitation.
3. Only then claim the residual gap.

*Synthetic pattern:* "The strongest consensus alternative, ConsenSite,
gains its 0.07 precision only from multiple experimental structures of the
target itself, unavailable for most prediction targets [4]; what remains
open is consensus scoring across *template* structures, weighted by
per-template local quality."

`gap_check.py` mechanically flags references whose capability cells overlap
the gap on distinctive terms but which the gap paragraph never mentions —
treat every such flag as a reviewer asking "what about X?".

## Anti-patterns (synthetic before/after)

**AP1 — Importance-as-gap.**
Before: "Binding-site prediction is very important, yet more research is
needed."
After: "TemplateTransfer's precision drops to 0.41 for targets below 30%
identity because a single template often carries a partially mismatched
pocket [2]; no provided method restores that precision."

**AP2 — Strawman chronology.**
Before: "In 2020 GeoScore was published. In 2021 TemplateTransfer appeared.
In 2022 SeqPocket…"
After: route-grouped same-axis comparison: "Both template-transfer methods
share the task but differ at the integration stage: TemplateTransfer trusts
one template [2], MultiTempl pools eight but weights them equally [3]."

**AP3 — Unbounded novelty claim.**
Before: "No prior work uses consensus scoring for binding-site prediction."
(dies to the ConsenSite counterexample)
After: "ConsenSite already applies consensus scoring, but only across
experimental structures of the target itself [4]; consensus scoring across
*templates* on low-identity targets remains unevaluated."

**AP4 — Limitation invention.**
Before: "SeqPocket is slow and inaccurate." (not in the provided text)
After: "SeqPocket lags template-based methods by 0.10 top-1 precision on
template-rich targets and cannot localize pockets that lack sequence
motifs [5]."

**AP5 — Anchorless contribution.**
Before: "We significantly improve low-identity prediction."
After: "On the hard subset of SynBench-60, PermaLig reaches 0.61 top-1
pocket precision versus 0.48 for the best single-template baseline (Fig 2)."

Each "after" is checkable: the claim cites a reference, the numbers come
from provided text, and the contribution carries an anchor from
`constraints.available_anchors`.

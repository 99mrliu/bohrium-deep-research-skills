# SYNTHETIC EXAMPLE — invented material, interface demonstration only. Not a real manuscript and not an answer to any organizer case.

# PermaLig — draft Introduction (synthetic demo)

## Background

Knowing where a ligand binds a protein constrains downstream design. A recent
survey groups predictors into template-based, geometry-based and
sequence-based families and observes that low-identity template transfer
remains the weakest setting across template-based methods [1].

## Related work

**Template-based transfer.** TemplateTransfer transplants the pocket of the
single highest-identity template; it reaches 0.55 top-1 pocket precision above
40% identity but drops to 0.41 below 30%, since one template often carries a
partially mismatched pocket [2]. MultiTempl pools pockets from up to
8 templates and ranks them by pocket frequency, raising recall by 0.15 over
single-template transfer, yet precision on low-identity targets stays flat
because low-quality templates vote with equal weight [3]. On the same
low-identity task, one template is too brittle and unweighted pooling too
permissive. **Consensus scoring.** ConsenSite, the nearest alternative,
scores pockets by unweighted consensus across homologous experimental
structures of the same protein, improving precision by 0.07 over
single-structure scoring; but it requires multiple experimental structures of
the target itself — unavailable for most prediction targets — and was not
evaluated on template-based transfer [4]. **Other
routes.** SeqPocket predicts binding residues from sequence alone, matching
template-based methods when no usable template exists but lagging them by 0.10
top-1 precision on template-rich ones, and cannot localize pockets lacking
sequence motifs [5]. GeoScore ranks candidate pockets by geometric
descriptors without any template; its abstract reports no comparison
against template-based predictors and no low-identity evaluation [6].

## Research gap

No provided method combines multiple template structures with quality-weighted
consensus scoring for low-identity targets: TemplateTransfer depends on one
template whose mismatches dominate below 30% identity [2], MultiTempl lets
low-quality templates vote with equal weight so low-identity precision stays
flat [3], and the strongest consensus alternative, ConsenSite, gains its 0.07
precision only from multiple experimental structures of the target itself,
unavailable for most prediction targets [4]. What remains open is
consensus scoring across template structures, weighted by per-template local
quality, and evaluated on targets whose best template is below 30% identity.

## Contributions

- We introduce an LQS-weighted multi-template consensus scoring scheme where
  each candidate pocket is voted on by up to 5 templates (Fig 1).
- On the hard subset of SynBench-60 (template identity below 30%), PermaLig
  reaches 0.61 top-1 pocket precision versus 0.48 for the best single-template
  baseline (Fig 2).
- An ablation on the hard subset attributes +0.09 top-1 precision to consensus
  scoring over simple template ranking (Fig 2).

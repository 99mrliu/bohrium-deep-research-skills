# Introduction (SYNTHETIC EXAMPLE — invented material, interface demonstration only)

## Background

Computational prediction of ligand binding sites underpins structure-based
ligand design, and methods are commonly grouped into template-based,
geometry-based and sequence-based families [1]. Across the template-based
family, the low-identity setting — where the best available template shares
little sequence with the target — remains the weakest surveyed setting [1].

## Related work

Template-based transfer is the most direct route: TemplateTransfer transplants
pockets from the single highest-identity template and reaches 0.55 top-1 pocket
precision when template identity exceeds 40%, but precision drops to 0.41 below
30% identity because a single template often carries a partially mismatched
pocket [2]. Sequence-only prediction removes the template requirement:
SeqPocket matches template-based methods on targets with no usable template but
lags them by 0.10 top-1 precision on template-rich targets [3]. Geometry-based
ranking is likewise template-free — GeoScore ranks candidate pockets by
geometric descriptors — but its abstract reports no comparison against
template-based predictors and no low-identity evaluation [4]. Using several
templates at once raises recall: MultiTempl pools pockets from up to 8 template
structures and gains 0.15 recall over single-template transfer, yet precision
on low-identity targets stays flat because low-quality templates vote with
equal weight [5]. ConsenSite improves precision by 0.07 through unweighted
consensus across homologous experimental structures, but it requires multiple
experimental structures of the target itself [6].

## Research gap

Thus, methods that exploit multiple structures either weight all templates
equally regardless of local quality [5], or require experimental structures of
the target that are unavailable in prediction settings [6]. Quality-weighted
consensus across template structures for low-identity targets remains
unestablished.

## Contributions

We present PermaLig, which scores each candidate pocket by consensus vote
across the top 5 templates, weighted by a per-template local quality score
(Fig 1). On the hard subset of SynBench-60, PermaLig reaches 0.61 top-1 pocket
precision versus 0.48 for the best single-template baseline (Fig 2), and an
ablation attributes +0.09 top-1 precision to consensus scoring (Fig 2). Our
evaluation is limited to single-chain soluble proteins.

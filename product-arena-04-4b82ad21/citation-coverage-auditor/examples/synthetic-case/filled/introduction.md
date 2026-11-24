# Introduction (SYNTHETIC EXAMPLE — invented content, interface demonstration only)

Computational prediction of ligand binding sites underpins molecular docking,
yet accuracy depends on whether a suitable structural template exists.
Template-based transfer is the dominant route: TemplateTransfer transplants
pockets from the single highest-identity template and reaches 0.55 top-1
pocket precision above 40% template identity, but drops to 0.41 below 30%
identity because a single template often carries a partially mismatched
pocket [1].

SeqPocket removes the template requirement, predicting binding residues with
a residue-attention network; it matches template-based methods on
template-free targets but lags them by 0.10 top-1 precision on template-rich
ones and cannot localize pockets without sequence motifs [2]. MultiTempl
pools pockets from up to 8 templates and ranks them by frequency, raising
recall by 0.15 over single-template transfer, but low-identity precision
stays flat because low-quality templates vote with equal weight [3].
GeoScore ranks pockets geometrically without any template, but reports no
comparison against template-based predictors and no low-identity evaluation
[4]. ConsenSite scores pockets by unweighted consensus across homologous
experimental structures, gaining 0.07 precision, but requires multiple
structures of the target itself and was not evaluated on template transfer
[5]. A survey groups these methods into template-based, geometry-based and
sequence-based families and identifies low-identity template transfer as the
weakest setting [6].

Taken together, existing routes either depend on a single template, ignore
structure, weight all templates equally, or assume experimental structures
of the target; none combines multiple templates with quality-weighted
consensus scoring for the low-identity setting.

Here we present PermaLig, which transfers putative pockets from the top 5
template structures and scores each candidate by a consensus vote weighted
by per-template local quality (LQS) (Fig 1). On the hard subset of
SynBench-60 (template identity below 30%), PermaLig reaches 0.61 top-1
precision versus 0.48 for the best single-template baseline, with +0.09
attributed to consensus scoring by ablation (Fig 2).

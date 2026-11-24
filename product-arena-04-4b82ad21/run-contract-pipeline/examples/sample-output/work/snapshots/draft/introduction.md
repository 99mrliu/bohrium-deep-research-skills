# Introduction — PermaLig (SYNTHETIC EXAMPLE — invented content, interface demo only)

> This draft exists only to demonstrate the run-contract-pipeline skill. Every
> fact, reference, number and result below is invented; nothing here is a real
> scientific claim.

## Background

Template-based binding-site prediction transfers known pockets from homologous
structures and remains the dominant strategy when a good template exists [1].
Where no usable template is available, sequence-only binding-site prediction
offers a template-free fallback [2], and geometry-based ranking scores pockets
without any template at all [3]. A recent survey observes that transfer at low
template identity is the weakest setting across template-based methods [4].

## Related work

TemplateTransfer transplants pockets from the single highest-identity template;
its top-1 precision falls from 0.55 above 40% identity to 0.41 below 30%
because one template often carries a partially mismatched pocket [1]. SeqPocket
predicts binding residues from sequence alone with a residue-attention network,
matching template-based methods when no template is usable but lagging them by
0.10 top-1 precision on template-rich targets, and it cannot localize pockets
that lack sequence motifs [2]. MultiTempl pools pockets from up to eight
templates and ranks them by frequency; pooling raises recall by 0.15 over
single-template transfer, yet precision on low-identity targets stays flat
because low-quality templates vote with equal weight [5]. GeoScore ranks
pockets by geometric descriptors, but the available abstract reports no
comparison against template-based predictors and no low-identity evaluation
[3]. ConsenSite applies multi-structure consensus scoring across homologous
experimental structures of the same protein, gaining 0.07 precision over
single-structure scoring, but it requires multiple experimental structures of
the target itself and was not evaluated on template-based transfer [6].

## Research gap

Pooling multiple templates raises recall [5] and unweighted consensus raises
precision [6], yet no cited method combines multi-template transfer with
quality-weighted consensus for the low-identity regime that the survey
identifies as the weakest setting [4].

## Contributions

We present PermaLig, which transfers putative pockets from the top five
template structures and scores each candidate by a consensus vote weighted by
a per-template local quality score, LQS (pipeline in Fig 1). On the hard
subset of our 60-target benchmark SynBench-60, PermaLig reaches 0.61 top-1
pocket precision versus 0.48 for the best single-template baseline, and an
ablation attributes +0.09 of this gain to consensus scoring (Fig 2).
Evaluation is limited to single-chain soluble proteins.

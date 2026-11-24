# Manuscript fact base — PermaLig (SYNTHETIC EXAMPLE, invented content)

> All statements below describe an invented manuscript. They exist only so that a
> skill can demonstrate its full pipeline end to end. Nothing here is a real
> scientific result.

## Present work

- Title: PermaLig: consensus scoring across multiple template structures improves protein-ligand binding-site prediction on low-identity targets.
- Problem: predicting ligand binding sites on proteins whose best available template shares less than 30% sequence identity with the target.
- Setting: benchmark of 60 invented target proteins (SynBench-60), split into an easy subset (template identity >= 30%) and a hard subset (< 30%).
- Method summary: PermaLig collects the top 5 template structures per target, transfers putative pockets from each, and scores each candidate pocket by a consensus vote weighted by per-template local quality (measured by an invented local quality score, LQS).
- Contribution 1: a multi-template consensus scoring scheme in which each candidate pocket is voted on by up to 5 templates weighted by LQS (Fig 1 shows the pipeline).
- Contribution 2: on the hard subset of SynBench-60, PermaLig reaches 0.61 top-1 pocket precision versus 0.48 for the best single-template baseline (Fig 2, invented numbers for demo).
- Contribution 3: an ablation showing that consensus scoring contributes +0.09 top-1 precision over simple template ranking on the hard subset (Fig 2).
- Limitations stated by the authors: evaluation is limited to single-chain soluble proteins; no membrane proteins were tested; LQS weights were tuned on the same benchmark.
- Data availability: SynBench-60 targets, predictions and scripts are stated to be available in an invented repository.

## Available anchors for contributions

- Fig 1: pipeline diagram of PermaLig (template selection, pocket transfer, LQS-weighted consensus voting).
- Fig 2: benchmark results and ablation bar chart on SynBench-60 easy/hard subsets.

## Facts the authors explicitly refuse to claim

- No claim of superiority on membrane proteins.
- No claim that LQS is better than other quality scores; no comparison with other quality scores was run.

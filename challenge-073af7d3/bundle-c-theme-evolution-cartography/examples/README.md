# examples/ — SYNTHETIC / 合成示例

Everything under this directory is **synthetic demonstration data** (合成示例数据),
not a real literature corpus. It exists only to prove the pipeline end-to-end.

- `synthetic_case/corpus.jsonl` — 30 planted records (2010–2024) in a 3-phase
  structure on one evolving theme (sentiment text classification methods):
  - phase 1 (2010–2015): "support vector machine" / "kernel method"
  - phase 2 (2016–2020): "deep neural network" / "convolutional network"
  - phase 3 (2021–2024): "transformer" / "self-attention" /
    "pretrained language model"
  - planted **term drift**: 2021–2022 records say "pretrained language model",
    2023–2024 records say "foundation model" for the same kind of work.
  - planted **citation trap**: the global citation top-5 (in fact top-8) are all
    phase-2 papers, so raw citation top-N leaves phases 1 and 3 uncovered.
- `synthetic_case/synonyms.json` — the synonym/drift map applied before counting.
- `run_example.sh` — GOOD path (full pipeline, must exit 0, asserts phases,
  drift and per-phase representatives) and BAD path (`--baseline top-citations`,
  must exit 1 with a coverage violation). Run:
  `bash examples/run_example.sh`
- `example_output/` — real artifacts produced by the last run of
  `run_example.sh` (`good/` full pipeline outputs, `bad/` baseline failure
  evidence). Regenerate any time with the script; do not hand-edit.

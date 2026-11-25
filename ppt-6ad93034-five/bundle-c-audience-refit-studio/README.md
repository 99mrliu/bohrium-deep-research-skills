# audience-refit-studio

Skill bundle for the 学术 PPT 生成与编辑 competition, official direction 2:
**内容编辑 / CONTENT EDITING & AUDIENCE REFIT**.

Center of gravity: surgical re-voicing of an *existing* academic deck —
switch the audience (导师 advisor / 评审 reviewer / 同行 peer), switch the
language (zh ↔ en), compress or expand the slide count — under three hard
guarantees:

1. **Locked terminology table** (`terms.json`) — extracted from the paper,
   every locked surface must survive the refit byte-identically unless an
   op explicitly declares the loss.
2. **Numeric-conservation auditing** (`refit_audit.json`) — every new
   number must exist verbatim in the paper text or be declared in the op's
   `introduced_numbers`; dropped numbers must be declared or live on
   deleted slides.
3. **Surgical scope** — slides not named by an op remain byte-identical;
   only `presentation.xml` / rels / content types move structurally.

## Layout

```
skill/
├── SKILL.md                 # skill definition + runtime contract
├── README.md                # this file
├── GITHUB_URL.txt
├── scripts/
│   ├── deck_io.py           # pptx <-> JSON model, XML surgery
│   ├── term_table.py        # locked terminology extraction
│   ├── audience_brief.py    # deterministic editing brief
│   ├── refit_apply.py       # apply ops (with reasons) -> new pptx
│   ├── conserve_check.py    # conservation audit, exit 1 on FAIL
│   └── result_make.py       # merge-safe result.json builder
├── references/
│   └── refit_policies.md    # full op/audit policy
└── examples/
    ├── make_fixture.py      # SYNTHETIC fixture builder
    ├── run_example.sh       # end-to-end demo incl. negative demo
    ├── README.md
    └── expected_output.md
```

## Quick start (synthetic demo)

```bash
cd examples && bash run_example.sh
```

All demo content is invented ("SynGraph" study) and marked SYNTHETIC.

## Boundary

This bundle is **not** a from-scratch deck builder. If an edit/adapt task
arrives without `starting-deck.pptx`, it refuses politely and delivers a
plan-only partial result.

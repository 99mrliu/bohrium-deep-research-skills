# table-rebind-lab (bundle d)

学术 PPT 生成与编辑 skill whose center of gravity is **figure/table data
rebinding** (官方方向3: 图表插入):

- printed tables are mined from the paper PDF into **provenance-carrying
  CSVs** (`tables/table-N.csv` + `tables.json`);
- result slides get **native editable pptx tables** (real `<a:tbl>` XML), not
  screenshots;
- charts are **replotted from the mined CSVs** in the template palette with an
  in-chart source note and a `*.provenance.json` that keeps the raw printed
  strings;
- bitmap figures are embedded **only as visually-verified crops** — data is
  never estimated from pixels;
- a **fail-closed number audit** checks every number, reference, and unit on
  every slide against the paper text and CSVs before the deck is built.

## Layout

```
skill/
├── SKILL.md                  # skill definition (frontmatter + workflow)
├── README.md                 # this file
├── GITHUB_URL.txt            # source URL
├── scripts/
│   ├── table_mine.py         # PDF text layer -> provenance CSVs / worksheets
│   ├── figure_harvest.py     # bbox captions -> verified pdftoppm crops
│   ├── replot.py             # verbatim matplotlib replots + provenance
│   ├── number_audit.py       # fail-closed number/ref/unit checker
│   ├── build_deck.py         # pure-stdlib pptx writer (native tables)
│   └── result_make.py        # early-partial + final result.json
├── references/
│   └── rebind_policy.md      # normative policy (verbatim, classification, audit)
└── examples/
    ├── make_fixture.py       # synthetic "SynNet" paper PDF + case/task/plans
    ├── run_example.sh        # end-to-end demo incl. negative audit demo
    ├── README.md             # how to run the example
    └── expected_output.md    # artifacts + proofs (synthetic)
```

## Quick start

At evaluation the skill lives at `/skills/weekly-skill`; inputs under
`/input`, work under `/app/work`, deliverables under `/app/output`. See the
6-step workflow in `SKILL.md`. Locally, run the synthetic demo:

```bash
cd examples && bash run_example.sh
```

## Guarantees and limits

- Pure stdlib core, no network; `matplotlib` optional (exit 3 → tables+crops
  fallback, exception noted); `pdftotext`/`pdftoppm`/`soffice` detected via
  `shutil.which` with graceful degradation.
- Template support is slide-size adoption only (full theme inheritance is
  declared in exceptions).
- No OCR: scanned PDFs without a text layer cannot be mined; the number audit
  then fails closed rather than inventing values.

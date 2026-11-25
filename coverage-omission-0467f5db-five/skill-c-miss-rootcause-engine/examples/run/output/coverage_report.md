# 漏检根因诊断报告

- case_id: `synthetic-demo-rootcause-001`
- 覆盖：分母 8 / 命中 5 / 漏检 3（0.6250）
- 诊断：3 条漏检全部完成五探针扫描；证据均为 file+locator+excerpt
- 补检：生成 8 条定向补检式；遗漏下降量测量：已测量

## 逐条诊断

### R005 Halide electrolytes with high voltage cathodes
- **query_term_missing**（P1_vocabulary）
  - distinctive token 'halide' absent from all query strings
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 2 — {"status": "ok", "message": {"DOI": "10.8888/synth.s005", "title": ["Halide electrolytes with high v
  - distinctive token 'electrolytes' absent from all query strings
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 1 — {"status": "ok", "message": {"DOI": "10.8888/synth.s001", "title": ["Sulfide solid electrolytes for 
- **source_not_covered**（P4_source）
  - venue 'J. Synth. Solid State' not observed in searched-source material; searched sources: Crossref, EuropePMC
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 1 — {"status": "ok", "message": {"DOI": "10.8888/synth.s001", "title": ["Sulfide solid electrolytes for 

### R006 Polymer ceramic composite separators
- **query_term_missing**（P1_vocabulary）
  - distinctive token 'polymer' absent from all query strings
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 3 — {"status": "ok", "message": {"DOI": "10.8888/synth.s006", "title": ["Polymer ceramic composite separ
  - distinctive token 'ceramic' absent from all query strings
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 3 — {"status": "ok", "message": {"DOI": "10.8888/synth.s006", "title": ["Polymer ceramic composite separ
- **time_window_cutoff**（P3_time_window）
  - record year 2017 outside window [2019,2024] of query Q1
    - 证据：`examples/input/materials/search_results.json` query_id:Q1 — sulfide solid electrolyte lithium battery
- **source_not_covered**（P4_source）
  - venue 'Old Synth. Mater.' not observed in searched-source material; searched sources: Crossref, EuropePMC
    - 证据：`examples/input/materials/crossref_ssb.jsonl` line 3 — {"status": "ok", "message": {"DOI": "10.8888/synth.s006", "title": ["Polymer ceramic composite separ

### R007 Preprint note on argyrodite moisture sensitivity
- **query_term_missing**（P1_vocabulary）
  - distinctive token 'preprint' absent from all query strings
    - 证据：`examples/input/materials/reference_list.csv` line 8 — ,Preprint note on argyrodite moisture sensitivity,2023,SynthRxiv
  - distinctive token 'argyrodite' absent from all query strings
    - 证据：`examples/input/materials/reference_list.csv` line 8 — ,Preprint note on argyrodite moisture sensitivity,2023,SynthRxiv
- **source_not_covered**（P4_source）
  - venue 'SynthRxiv' not observed in searched-source material; searched sources: Crossref, EuropePMC
    - 证据：`examples/input/materials/reference_list.csv` line 8 — ,Preprint note on argyrodite moisture sensitivity,2023,SynthRxiv
- **identifier_missing**（P5_identifier）
  - reference record carries neither DOI nor PMID; cannot be resolved or matched by identifier


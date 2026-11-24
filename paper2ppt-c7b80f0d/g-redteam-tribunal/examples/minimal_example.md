# 最小调用示例

> **合成示例，非平台案例结果。** 以下输入由 `make_synthetic_case.py` 现场生成，
> 所有论文内容（"Synth et al."、数值、图表）均为虚构。

```bash
# 1. 生成合成输入（paper.pdf / target-template.pptx / data.csv / case.json / task.md / figs/）
python3 examples/make_synthetic_case.py --out /tmp/demo/input

# 2. 事实池
python3 scripts/extract_facts.py /tmp/demo/input/paper.pdf --out /tmp/demo/facts.json

# 3. 写 deck v1（Agent 手写；此处给最小骨架示意）
cat > /tmp/demo/deck_v1.json <<'JSON'
{
  "version": 1,
  "title": "Synthetic Gradient Harmonizers",
  "slides": [
    {"slide": 1, "role": "title", "title": "Synthetic Gradient Harmonizers",
     "bullets": ["A. Synth, B. Fabric"], "figures": [], "table": null,
     "notes": "Opening: state that everything shown is synthetic.",
     "notes_time_sec": 45, "claims": []},
    {"slide": 2, "role": "results", "title": "Experimental Results",
     "bullets": ["The harmonizer reaches 99.9 % accuracy (Figure 2)."],
     "figures": ["Figure 1", "Figure 2"], "table": null,
     "notes": "The harmonizer reaches 99.9 % accuracy. Figure 2.",
     "notes_time_sec": 60,
     "claims": [{"text": "The harmonizer is state of the art.",
                 "sources": [{"kind": "pdf", "ref": "paper.pdf",
                              "locator": "p3",
                              "quote": "this quote does not exist in the paper"}]}]}
  ]
}
JSON

# 4. Round 1 扫描 -> 检出 R1(99.9 %) R2(Figure 2) R3(假 quote) R4(栏目名标题) R6(复读) R7(无局限页)
python3 scripts/redteam_scan.py /tmp/demo/deck_v1.json /tmp/demo/facts.json --round 1 --report /tmp/demo/findings_round1.json
python3 scripts/tribunal_log.py --findings /tmp/demo/findings_round1.json --ledger /tmp/demo/tribunal.json

# 5. 自动修 R1/R2；人工修其余后销账（见 README 完整闭环）
python3 scripts/apply_fixes.py /tmp/demo/deck_v1.json --ledger /tmp/demo/tribunal.json --out /tmp/demo/deck_auto.json --report /tmp/demo/fixes_report.json
# ... 人工修 deck_auto.json -> deck_v2.json，tribunal_log --fix / --disposition ...
python3 scripts/redteam_scan.py /tmp/demo/deck_v2.json /tmp/demo/facts.json --round 2 --report /tmp/demo/findings_round2.json
python3 scripts/converge_gate.py --ledger /tmp/demo/tribunal.json --prev /tmp/demo/findings_round1.json --cur /tmp/demo/findings_round2.json --report /tmp/demo/convergence.json

# 6. 构建 + 交付
python3 scripts/build_deck.py /tmp/demo/deck_v2.json --template /tmp/demo/input/target-template.pptx --fig-dir /tmp/demo/input/figs --out /tmp/demo/presentation.pptx --report /tmp/demo/build_report.json
python3 scripts/make_result.py --case /tmp/demo/input/case.json --task /tmp/demo/input/task.md --deck /tmp/demo/deck_v2.json --pptx /tmp/demo/presentation.pptx --build-report /tmp/demo/build_report.json --convergence /tmp/demo/convergence.json --outdir /tmp/demo/output
```

预期：round 1 检出 ≥4 类缺陷；修复+裁决后 round 2 无 error；
converge_gate 退出码 0；result.json 的 `compliance_checks` 含
`redteam_converged` 且 actual="pass"。

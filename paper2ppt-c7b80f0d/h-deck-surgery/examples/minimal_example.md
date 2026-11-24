# 最小调用示例

> **合成示例，非平台案例结果。** 以下输入由 `make_synthetic_case.py` 现场生成，
> 论文、数据、结论全部为虚构（"Synth et al." / "fictional" / "synthetic"），
> 仅用于演示 ppt-deck-surgery 的 edit 模式全流程。

## 场景

`runs/e/input/` 下有一份 6 页起始稿 `starting-deck.pptx`，含两处待修问题：

- P2 标题是栏目名 `SECTION_HEADER`（占位标题）；
- P3 写着 "coherence time of 99.9 ms"，与合成论文（42.7 ms，page 2）不符。

任务（task.md）：10 分钟、≤8 页、保留模板主题、每页要有备注、Figure 1/Table 1 可溯源。

## 命令序列

```bash
BUNDLE=skill
python3 $BUNDLE/examples/make_synthetic_case.py --out runs/e/input
python3 $BUNDLE/scripts/evidence_scan.py runs/e/input/paper.pdf \
    --report runs/e/work/evidence.json
python3 $BUNDLE/scripts/deck_probe.py runs/e/input/starting-deck.pptx \
    --report runs/e/work/probe_report.json
python3 $BUNDLE/scripts/plan_ops.py --probe runs/e/work/probe_report.json \
    --task runs/e/input/task.md --evidence runs/e/work/evidence.json \
    --suggest runs/e/work/ops_suggested.json

# Agent 阅读 ops_suggested.json 的诊断后，手工填写 runs/e/work/ops_journal.json
#（本仓库 runs/e/work/ops_journal.json 是填好的实例：13 个 op，覆盖
#  set_title / replace_text / set_bullets / add_figure / insert_slide / set_notes）

python3 $BUNDLE/scripts/deck_ops.py runs/e/input/starting-deck.pptx \
    --ops runs/e/work/ops_journal.json --out runs/e/output/deck_final.pptx \
    --versions-dir runs/e/work/versions --log runs/e/work/ops_log.json
# 幂等验证：同一命令再跑一次 → 13 个 op 全部 skipped，versions/ 不增加

python3 $BUNDLE/scripts/deck_diff.py runs/e/work/versions/v1.pptx \
    runs/e/output/deck_final.pptx --report runs/e/work/deck_diff.json
python3 $BUNDLE/scripts/surgery_lint.py runs/e/work/versions/v1.pptx \
    runs/e/output/deck_final.pptx --ops runs/e/work/ops_journal.json \
    --log runs/e/work/ops_log.json --report runs/e/work/surgery_report.json
python3 $BUNDLE/scripts/render_check.py runs/e/output/deck_final.pptx \
    --out-dir runs/e/output/render --report runs/e/work/render_report.json --profile-key e
python3 $BUNDLE/scripts/make_result.py --case runs/e/input/case.json \
    --task runs/e/input/task.md --deck runs/e/output/deck_final.pptx \
    --evidence runs/e/work/evidence.json --ops-log runs/e/work/ops_log.json \
    --diff runs/e/work/deck_diff.json --render runs/e/work/render_report.json \
    --out runs/e/output/result.json
```

## 实测结果（本机合成运行）

- deck_ops run1：13 ops 全部 applied，快照 v1–v14；run2：13 ops 全部 skipped，无新版本。
- deck_diff：6→7 页；added=1（P5 "Table 1 Summary"）、modified=6、removed=0、moved=0。
- surgery_lint：5 项检查全过（未涉及页哈希不变、主题 sha1 一致、13 条 change_records 完整）。
- render_check：soffice 真实渲染，PDF 7 页 = deck 7 页，7 张 PNG 预览。
- result.json：status=success；compliance_checks 5 项全 pass（slide_count 7≤8、
  export_page_match 7==7、placeholder_free 0、evidence_coverage 1.0、notes_coverage 1.0）；
  change_records 13 条，形态 {version, slide, change, reason, rollback}。

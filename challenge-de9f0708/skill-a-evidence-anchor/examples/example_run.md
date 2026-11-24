# 合成示例运行说明（example_run）

> 本目录全部是**合成示意案例**：论文（mock_paper.txt）、案例（mock_case.json）、findings
> 草稿与全部输出均为虚构演示，**非正式测评结果**。机构、人物、药物 ZX-101、文献均不存在。

## 1. 示例内容

- `mock_paper.txt`：约 3 页的合成论文全文（用 `\f` 分页模拟 pdftotext 物理页），
  埋入 4 个已知问题：
  1. **参考文献元数据可疑**（第 3 页 References）：`Nature. 1897;512(7515):45-52.` ——
     Nature 第 512 卷对应 2014 年，年份 1897 与卷号 512 不可能同时成立；
  2. **样本量前后不一致**（第 2 页）：Methods 写 `We enrolled 120 adult participants`，
     而 Results 的 Table 1 写 `analysis population (n = 102)`；
  3. **涉及人受试者但全文无伦理审批/知情同意声明**（Methods 2.1 明确成人受试者每日
     口服研究药物 12 周，全文检索不到 ethics/consent/IRB 等任何声明）；
  4. **结论段无引用支撑的强因果论断**（第 3 页 Conclusion）：
     `ZX-101 definitively causes durable remission`，且与 Discussion 自述的
     open-label 因果局限冲突。
- `findings_draft.json`：Agent 视角的草稿，共 6 条 finding（F-001~F-005 对应上述
  4 个埋入问题，其中样本量问题拆为 F-002/F-003 两条）；**F-006 是故意写错的 quote**
  （"We enrolled 130 adult participants"，原文是 120），用于演示锚定失败自动降级。
  F-002 与 F-005 的 quote 故意按"换行变空格"书写，用于演示 `normalized` 匹配级；
  F-004 为 absence 类 finding（quote 为空），演示 `skipped_absence_claim`。

## 2. 如何复跑

```bash
cd <本 bundle 目录>/examples
bash run_example.sh
```

脚本依次执行（全部输出写入 `examples/output/`，幂等可反复跑）：
1. `audit_skeleton.py --case mock_case.json --out output/result.json --force` —— 保底骨架；
2. `extract_text.py mock_paper.txt --out output/pages.json` —— 按 `\f` 分页 + 章节粗切分；
3. `quote_bind.py --pages output/pages.json --findings findings_draft.json
   --out output/findings_bound.json --stats output/anchor_stats.json` —— 锚定机械核验；
4. 内联 Python 汇总 `result.json` 并渲染 `report.md`。

## 3. 输出如何解读

- `output/pages.json`：3 页，识别出 8 个章节标题（Abstract p1 / Introduction p1 /
  Methods p2 / Results p2 / Discussion p3 / Conclusion p3 / Acknowledgements p3 /
  References p3），页码与 mock_paper.txt 的 `\f` 分页一致。
- `output/anchor_stats.json`：`verified=4（exact=2, normalized=2）`，
  `skipped_absence_claim=1`，`downgraded=1, downgraded_ids=["F-006"]`。
- `output/findings_bound.json` / `report.md`：
  - F-001（可疑文献，第 3 页）exact 命中，4 个埋入问题全部如数抓出且页码正确；
  - F-002/F-003（n=120 vs n=102，均在第 2 页）normalized/exact 命中；
  - F-004（缺伦理声明）quote 为空 → `skipped_absence_claim`，不降级但标注需人工复核全文；
  - F-005（强因果论断，第 3 页）normalized 命中；
  - **F-006（故意写错的 quote）match_level=none → verdict_status 被自动改为
    `待复核`，并追加理由"锚定核验未通过：quote 未逐字出现在声称位置"** ——
    这就是本 skill 的核心机制：编造的定位在交付前被脚本强制拦下。
- `output/result.json`：因存在 1 条降级 finding，status=partial（诚实保底），
  `output_contract.required_fields` 8 个字段全部齐全。

## 4. 注意

- 修复 F-006 的正路不是把状态改回"确认"，而是按 `anchor.found_on_pages` 提示核对原文、
  把 quote 改成逐字摘录后重跑 quote_bind；若原文根本没有这句话，应删除该 finding。
- 若在本机跑 PDF 输入，需要 poppler 的 `pdftotext`；缺失时 extract_text.py 会输出
  空 pages + warnings 并 exit 0（优雅降级），不会崩溃。

# 示例运行说明（合成示例，非正式测评结果）

本目录是 `exp-source-reconciler` 的**合成示例**：`mock_case.json` 为手工构造的
MAPbI3 钙钛矿退火工艺优化示意案例（其 `note` 字段已标明"合成示意案例"），
用于演示 extract / reconcile / pdfscan 三件套的对账能力。

## 埋入的对账陷阱

mock_case.json 故意埋入以下陷阱，全部应由脚本（而非肉眼）发现：

1. **total_cost 算术错误（v1）**：5 行成本小计之和为 3200+320+1000+900+240=5660，
   但候选宣称 total_cost=5760（虚报 100 CNY）。
2. **参数越域（v2）**：`spin_coating_rpm=5000` 不在枚举域 `[2000,3000,4000,6000]` 内。
3. **文本内嵌设备**：`equipment_domain_note` 文本里内嵌了 EQ-HP 精密加热台的 JSON 片段，
   它不在 `resource_contract.equipment` 列表中；v2/v3 的"加热台"成本行只有解析该片段后才能对账通过。
4. **合同外试剂（v2）**：成本行 `PCBM` 不在合同试剂清单内。
5. **周期超限（v2）**：`est_days=35 > deadline_days=30`（并伴随预约窗口 WARN）。
6. **依据不可定位（WARN）**：`n2_flow_rate_slm` 参数域的 `source: case:pre_experiment.report`
   在 case 内不存在。
7. **未登记参数（WARN）**：v3 使用 `antisolvent_drip_s`，parameter_domains 中无此条目。

## 如何复跑

```bash
bash examples/run_example.sh
```

脚本依次执行：

```bash
python3 ../scripts/case_reconcile.py extract   --case mock_case.json --outdir output
python3 ../scripts/case_reconcile.py reconcile --case mock_case.json --facts output/facts.json --out output/reconcile_report.json
python3 ../scripts/case_reconcile.py pdfscan   --inputdir . --case mock_case.json --out output/pdf_excerpts.md
```

然后给 output 下每个文件头部注入"合成示例输出，非正式测评结果"标注
（正式运行时脚本输出不含此标注）。

## 输出解读（本次真实运行结果）

- `output/facts.json` / `output/facts.md`：138 条事实，统一设备表 3 行，
  其中 **EQ-HP origin=text_embedded**——内嵌设备被正确合并。
- `output/reconcile_report.json`：**PASS=64, FAIL=4, WARN=4**。
  - FAIL@v1 `A-total`：5660 ≠ 5760（差额 100 CNY）——陷阱 1 命中；
  - FAIL@v2 `B-param`：5000 ∉ 枚举域——陷阱 2 命中；
  - FAIL@v2 `C-ref`：PCBM 无法匹配——陷阱 4 命中；
  - FAIL@v2 `D-deadline`：35 > 30 天——陷阱 5 命中；
  - WARN：v3 未登记参数 antisolvent_drip_s（陷阱 7）、v2 est_days 超两台设备预约窗口、
    n2_flow_rate_slm 的 source 无法定位（陷阱 6）；
  - v2/v3 的"加热台"成本行 **PASS 且注明 origin=text_embedded**——陷阱 3 被正确化解
    （若漏解析内嵌片段，这两行会误报 FAIL）。
  - `revision_targets` 字段直接给出修订靶点：`A-total@v1, B-param@v2, C-ref@v2, D-deadline@v2`。
- `output/pdf_excerpts.md`：examples 目录无 PDF，脚本如实报告"未发现 PDF 文件"，
  不捏造摘录与页码。（另在 /tmp 用 cupsfilter 生成的真实 PDF 验证过 pdfscan：
  能给出真实页码与上下文摘录。）

## 后续动作（真实任务中）

把 4 条 FAIL 作为修订靶点改写候选方案（修正总价、把 5000 rpm 改回域内、剔除或替换 PCBM、
压缩排期到 30 天内），按 `references/plan_citation_rules.md` 给方案每个数字标注 fact id，
自检后写 result.json。

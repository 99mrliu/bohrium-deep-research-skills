# EXPECTED — 合成示例的预期输出说明

> 本目录（examples/）全部是**合成示例**（synthetic example）：paper.txt 为虚构论文，
> claims.json 为配套虚构论断，case.json 为演示用输入结构。
> 与它们配套的输出均标注为示意输出，**不构成评测正式案例的答案**。

## 运行方式

```bash
bash examples/run_example.sh
```

实际已在 macOS (Python 3.12.14) 端到端跑通，最终退出码 **0**。
产物写入 `examples/out/`。

## 预期输出（已实测验证的状态）

| 步骤 | 命令 | 预期 | 实测 |
|---|---|---|---|
| 1 | `extract_pages.py -i paper.txt -o pages.jsonl` | exit 0，页数=4，疑似扫描页=0 | ✅ exit 0 |
| 2 | 构造 sample_result.json（quote 摘自 paper.txt 原文） | — | ✅ |
| 3 | `quote_audit.py -r sample_result.json -p pages.jsonl` | exit 0，4 条证据全部 verbatim_ok（C2 直引号经归一化匹配弯引号原文，C4 跨行 quote 经归一化匹配） | ✅ exit 0，通过=4 失败=0 |
| 4 | `num_drift.py -c claims.json -r sample_result.json` | exit 1，恰检出 2 项设计好的漂移：C2 的"90%"（原文无此值，属 contradicted 论断的数值外推）与 C4 的"78.2%"（原文为 78%，value_mismatch） | ✅ exit 1，漂移项=2 |
| 5 | 保真门拦截演示：sample_result_bad.json 含捏造 quote "转化率高达 99%…" | `quote_audit.py` 判 not_found（ratio≈0.57），exit 1 | ✅ exit 1，拦截成功 |

## 关键产物说明

- `pages.jsonl`：4 行页记录 + 1 行 `_meta`；每页含 `page/chars/text/printed_page/header_lines/footer_lines`。
- `fidelity-report.json`：4 条 evidence 的机检结果（ratio=1.0、found_pages、verdict=verbatim_ok）。
- `num-drift.json`：2 条 drift 明细（kind、claim_id、论断数值、原文最近值）。
- `fidelity-report-bad.json`：捏造 quote 的 not_found 记录，演示"不过门即拦截"。
- `sample_result.json`：满足 case.json 中 output_contract 全部 8 个字段的示意结果。

## 判定与证据的对应（合成示例）

| 论断 | 支持度 | 证据位置 | 机检结论 |
|---|---|---|---|
| C1（280 °C、2.0 MPa 下转化率 78%） | supported | paper.txt 第 2 页 3.1 节 | quote verbatim，数值 78%/280/2.0 全对 |
| C2（350 °C 下转化率超过 90%） | contradicted | paper.txt 第 3 页 3.2 节 | quote verbatim，原文 54% 与 90% 直接冲突 |
| C3（含 SO2 烟气中稳定） | insufficient_evidence | paper.txt 第 3 页 3.3 节 | quote verbatim，原文写明"未考察"；未报告≠反驳 |
| C4（62%→78.2%） | partially_supported | paper.txt 第 2 页 3.1 节 | quote verbatim，但 78.2% 被 num_drift 判 value_mismatch |

## 脚本通用行为（已实测）

- 全部脚本 `python3 <script> --help` 可用；缺参数 / 互斥参数冲突 → exit 2。
- 输入文件不存在 / JSON 损坏 → exit 1（清晰错误信息到 stderr）。
- quote_audit：存在 not_found 或 page_drift → exit 1；仅 near_match 警告 → exit 0。
- num_drift：存在 drift 项 → exit 1；无漂移 → exit 0。
- extract_pages：PDF 走 `pdftotext -layout`（`\f` 分页），chars<50 页标
  `suspect_scan: true`；pdftotext 缺失时仅支持 .txt 输入并报错退出 1
  （本机 Poppler 存在，PDF 分支已用最小自制 PDF 实测 exit 0）。

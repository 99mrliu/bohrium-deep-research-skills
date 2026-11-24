# 合成示例说明（examples/）

**本目录全部数据为合成示例（synthetic, illustrative）**：R001/R002/R003
三篇"研究"、全部数据（跌倒率 12.3% vs 18.7%、OR=0.72 等）与题录均为虚构，
仅用于演示 slr-claim-backlink 的论断回链审计流程，不得冒充正式案例结果。

## 目录

- `input/case.json`、`input/task.md`：合成案例输入（运动干预与老年人跌倒风险）。
- `sources/R001.txt`、`R002.txt`、`R003.txt`：三篇合成研究短文本（各 15 行）。
- `sources/records.json`：合成题录（3 条，建索引后每条约一个 span）。
- `extractions.jsonl`：筛选提取阶段登记的证据片段（含 1 个故意不被引用的
  孤儿 span `R003.txt#L10-14`，用于演示 C7 警告）。
- `claims.jsonl`：6 条合成论断（2 fact + 2 inference + 1 uncertain 带 note +
  1 fact 观察性证据，全部合规）。
- `conflicts.jsonl`：1 对冲突登记（CL-02 × CL-06）。
- `negative/`：四个埋雷 claims 文件，各自只触发一条规则。

## 运行命令

```bash
SKILL=..   # 本目录上一级（bundle 根）
# 1) 解析案例 + 落 result.json 骨架
python3 $SKILL/scripts/parse_case.py --case input/case.json --out /tmp/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --case-summary /tmp/case_summary.json --out /tmp/result.json
# 2) 建 span 索引（重跑输出逐字节一致）
python3 $SKILL/scripts/index_sources.py --sources sources --out /tmp/spans.json
# 3) 论断审计（正例）
python3 $SKILL/scripts/audit_claims.py --claims claims.jsonl --spans /tmp/spans.json \
  --out /tmp/audit_report.json --extractions extractions.jsonl --conflicts conflicts.jsonl
# 4) 生成矩阵制品
python3 $SKILL/scripts/build_matrix.py --claims claims.jsonl --spans /tmp/spans.json \
  --audit /tmp/audit_report.json --out-dir /tmp/products
```

## 预期退出码

| 运行 | 预期 |
|---|---|
| parse_case / scaffold_result / index_sources 正例 | exit 0 |
| audit_claims 正例（6 条论断） | exit 0，另打印 1 条 C7 孤儿警告与 1 对冲突登记 |
| audit_claims + `negative/claim_bad_quote.jsonl` | exit 3（C2：quote 非 verbatim 子串，附最相似行提示） |
| audit_claims + `negative/claim_dangling_span.jsonl` | exit 3（C3：span_id 悬空） |
| audit_claims + `negative/claim_firm_inference.jsonl` | exit 3（C5：inference 含"证明"） |
| audit_claims + `negative/claim_fact_noevidence.jsonl` | exit 3（C4：fact 无证据） |
| 缺 spans 文件 / 空材料目录 / 空 claims | exit 2（E-INPUT 诚实降级） |

一键全量自检：`python3 ../scripts/selfcheck`（断言以上全部行为，exit 0 通过）。

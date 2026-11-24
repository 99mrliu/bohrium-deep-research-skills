# 示例运行说明（合成示例，非正式测评结果）

## 这是什么

`mock_paper.txt` 是一篇**合成**论文文本（改性生物炭吸附 Cd(II)，约 2 页），
`mock_case.json` 是**合成示意案例**。论文中埋入了 4 类已知问题：

| # | 埋入问题 | 位置 | 期望捕获处 |
|---|---|---|---|
| ① | DOI 形态非法 `10.1021`（缺后缀） | 文献 [3] | lint `doi_format_invalid` |
| ② | 两条标题近乎重复（相似度 0.992） | 文献 [4] vs [5] | lint `duplicate_reference` |
| ③ | 年份 2031（未来年） | 文献 [6] | lint `year_anomaly` |
| ④ | 正文 [2] 语境句（催化剂焙烧）与文献 [2]（青花瓷釉料 XRF）主题无关 | 引言 | lint `claim_citation_mismatch` + refs.json `citations` 语境句 |

## 如何复跑

```bash
cd examples
bash run_example.sh
```

脚本依次执行（输出均写入 `examples/output/`，头部带 `_note: 合成示例输出，非正式测评结果`）：
1. `extract_refs.py --input mock_paper.txt --output output/refs.json`
2. `lint_refs.py --input output/refs.json --output output/lint.json`
3. `crossref_check.py --offline --max-queries 12 …` —— **离线模式**，演示优雅降级；
4. 汇总 `output/result.json`（status=partial，诚实标注外部核验未执行）；
5. 可选在线核验 `crossref_check.py --max-queries 12` → `output/crossref_online.json`
   （文件头 `generated_at_utc` 注明检索时间；网络失败不阻断主流程）。

## 本次真实运行的观察（2026-11-24，macOS，python3 stdlib）

**离线（主流程）**：
- `refs.json`：6 条文献全部切出，字段初值完整；5 个正文引文标记的语境句全部抓取
  （含 `[4,5]` 多编号解析）。
- `lint.json`：4 类埋入问题**如数**出现（4 candidates），无多余误报；
  人文期刊文献 [2] 无 DOI 仅记入 `info_notes`（不判违规）；
  跨语种引文（[1][3][6]）自动跳过主题重叠判定，防止误报。
- `crossref_offline.json`：预算 used=0/12，6 条全部 `pending_review`，
  rationale 如实写明 "offline mode：……绝不以'未检索'代替'不存在'"。
- `result.json`：status=partial，4 条 findings 均为"待复核"候选，
  外部核验面列入 `not_reviewed`。

**在线（可选演示，真实 Crossref/doi.org 检索，预算 used=10/12）**：
- 文献 [1]：Crossref 404 + doi.org 404 → **两信号齐备 → fabrication_suspected /
  critical / 待人工终裁**（合成 DOI 为虚构，符合预期）。
- 文献 [4][5]：虚构 DOI 恰好指向**真实的其他论文**（Crossref 返回的标题与著录
  完全不同）→ `metadata_mismatch / major / 确认`，检索记录原文存于
  `retrieved_records`。
- 文献 [6]：同样两信号齐备 → fabrication_suspected / critical。
- 文献 [2]（无 DOI 人文期刊）与 [3]（DOI 非法仅做书目检索）：仅"检索无结果"
  单一信号 → `not_found → 待复核`，**未判不存在**——两信号规则生效。

## 输出如何解读

- lint 的 `candidates` 与 result.json 的 findings 全部是**候选**（verdict_status
  字段），最终结论需结合 crossref 检索记录与人工复核（见
  `references/verification_protocol.md` 与 `references/severity_rubric.md`）。
- `query_log` 记录每次真实请求的 URL/状态码/错误，可用于审计预算与复跑。
- 在线结果随网络与 Crossref 数据库变化可能与上文略有出入（如 doi.org 偶发
  连接重置 → 该条目单信号待复核、后续条目降级 pending_review），属预期的
  诚实降级行为。

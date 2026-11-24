# 审计包规范（audit pack specification）

## 1. 何为"可独立复核"

一名不了解本任务、不接触模型与语料原文以外的任何内部状态的评审，仅凭交付目录中的文件即可：

1. **定位**：从任意一条综述论断句出发，找到它所引用的全部证据行。
2. **核对**：看到每条证据行的逐字摘录、来源文档、`p<页>.¶<段>` 页锚点与强度标记。
3. **追源**：凭文档的 SHA-256 与抽取方法确认证据来自哪一份原始材料。
4. **查漏**：看到哪些文档未被任何主题覆盖、哪些证据行从未被引用、哪些实质句没有任何证据标记。
5. **验契约**：凭 validation_report.json 确认 result.json 满足手写 schema 且镜像了 output_contract 全部字段。

任何一环需要"问作者"或"重跑模型"才能回答，即不满足可独立复核。

## 2. 必含产物与复核入口

| 产物 | 生成脚本 | 复核入口 |
| --- | --- | --- |
| `out/audit_report.html` | compile_audit.py | 浏览器直接打开；自包含（内联 CSS、零外部资源）；论断句块内每条 `[E#]` 可点击跳转至证据明细锚点 |
| `out/evidence_matrix.csv` | compile_audit.py | Excel/Numbers 直接打开（UTF-8 带 BOM）；一行一条证据，含 `referenced_in_draft` 列 |
| `out/coverage_map.json` | compile_audit.py | 文档×主题证据计数矩阵 + `uncovered_documents` 清单 |
| `out/link_check_report.json` | link_check.py | `ok` 布尔；`unresolved_markers`、`unused_evidence`、`unsupported_sentences` 三个清单 |
| `out/result.json` | build_result.py | 镜像 output_contract 全部字段；含 case_id/status/sources/uncertainties/change_log |
| `out/validation_report.json` | validate_result.py | `ok` 布尔 + 逐条错误；非零退出即未交付 |
| `work/pages/<doc_id>.jsonl` | ingest.py | 逐字摘录的最终核对基准（页文本） |
| `work/docs.jsonl` | ingest.py | 每篇文档的 sha256、tier、extract_method 留痕 |

## 3. 渲染规则

1. HTML 模板只允许使用 `{{PLACEHOLDER}}` 文本占位符，由 compile_audit.py 做纯字符串替换；
   所有动态文本必须经 HTML 转义，禁止把未转义的摘录/句子直接拼入模板。
2. 每个论断句渲染为一个块：句子原文（`[E#]` 标记高亮且为页内链接）+ 一张证据表
   （证据号、文档、锚点、逐字摘录、supports、theme、strength）。
3. 未被引用的证据行、无标记实质句必须**展示而非删除**，分别进入
   `{{ORPHAN_SECTION}}` 与 `{{UNSUPPORTED_SECTION}}`。
4. 覆盖矩阵中文档计数为 0 的主题-文档单元格以样式标出；`uncovered_documents` 单列一节。

## 4. 闸口规则

- `link_check.py`：`[E#]` 指向不存在的证据行、证据表 id 重复、证据行缺必填字段 →
  失败（退出码非零）；未用证据与无标记实质句 → 警告（只报告，不阻断）。
- `validate_result.py`：schema 必填键缺失、类型不符、status/strength/tier 越枚举、
  output_contract 字段缺失、case_id 不一致 → 失败（退出码非零）。
- 两道闸口任一失败，任务不得宣称完成；修复后必须**重跑**对应命令，禁止手改报告文件。

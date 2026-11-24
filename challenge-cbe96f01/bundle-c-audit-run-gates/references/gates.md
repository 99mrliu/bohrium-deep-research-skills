# 门控定义（G0–G9）与通过判据

每道门的机器判据由对应脚本实现；本文件是语义基准，脚本与之冲突时以本文件为准并修正脚本。

| 门 | 位置 | 判据 | 失败处置 |
|-|-|-|-|
| G0 | 阶段 0 末 | 解析成功（extract_status=ok）且 anchors 非空 | blocked 流程；记录已尝试方法 |
| G1 | 阶段 1 末 | claims.jsonl 每条 quote 逐字落在所声称页文本内 | 从 anchors.json 重取真实文本修复，或丢弃该条 |
| G2 | 阶段 2 末 | findings draft schema 完整、词表合法、anchor 存在 | 修复后重查 |
| G3（交付总门） | 阶段 3 | G1–G8 全量通过（见下） | 修复重跑；预算耗尽则 partial 交付并注明未过之门 |
| G9 | 阶段 4 | 确定性产物重放逐字节一致 | 定位不确定性来源并修复，或在 uncertainties 声明 |

## 交付总门 G1–G8（gate_check.py）

- **G1 身份**：result.json 含 `case_id`；提供 case.json 时必须与 `case_id`/`id`/`caseId` 一致。
- **G2 契约**：case.json 的 `output_contract`（dict 取键、list 取元素）全部出现在 result.json 顶层。无法填充的字段允许为 `null` 但**必须存在**且在 uncertainties 说明。
- **G3 覆盖**：六类（事实核验、引用支持、方法设计、统计报告、论证链、学术规范）键齐全，取值 ∈ {checked, partial, unchecked}。
- **G4 结构**：每条 finding 含 id、category、issue_type、severity、location、claim、verdict、basis、suggestion、confidence。
- **G5 位置真实**：每条 finding 的 `location.quote` 折叠空白后是所声称页文本的子串；页码在解析范围内。
- **G6 词表**：category ∈ 六类；issue_type ∈ {事实错误， 证据不足， 规范问题， 建议性意见}；severity ∈ {critical, major, minor, advisory}；confidence ∈ {high, medium, low}。
- **G7 诚实一致性**：completed ⇒ 无 unchecked 覆盖；partial ⇒ unchecked_items 非空；blocked ⇒ findings 为空；status 取值合法。
- **G8 日志**：run_log.jsonl 存在、逐行 JSON、每行含 t/action/status。

## 附录：六类审查要点（产出形态约束，不替代专业判定）

1. 事实核验：数值、名称、转述与原文位置一致；外部事实无法核实时标 待复核 + 复核路径。
2. 引用支持：四态判定；重点"结论超出引文范围"。
3. 方法设计：样本量与统计方法匹配、对照、可复现参数。
4. 统计报告：摘要/正文/表格数字交叉一致；可重算的必须重算并写过程。
5. 论证链：跳跃、循环、以偏概全、相关当因果；写明缺失环节。
6. 学术规范：署名、重复发表、数据/代码可用性兑现、伦理与利益冲突声明。

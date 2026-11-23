# 上游数据真实性：方法与字段变体说明

## 方法论证

文献问答类任务最常见的失败模式有三类，且都发生在"答题"之前：

1. **解析失败被静默吞掉**：案例包字段名稍有变体（`paragraphs` vs `sections` vs
   `content.paragraphs`），基础 Agent 往往按一个名字读，拿不到就猜结构，
   随后把猜测当成材料来答。
2. **坏输入被当成真材料**：空段落、重复编号、含 U+FFFD 的编码损伤段，
   被原样引用成"证据"，证据本身不可信。
3. **自述覆盖率失真**：模型说自己"通读了全文"，但运行记录里只读了三段；
   `coverage` 与真实行为脱节，可靠性直接归零。

本 Skill 的对策全部落在确定性脚本中，不占模型预算：

- **宽容解析**：`load_case` 依次尝试 `case_id/caseId/id`、`paper_id/paperId/paper`、
  `material_version/materialVersion/version`、`paragraphs/sections/passages`、
  `content.paragraphs/material.paragraphs`、`questions/question_list/queries`，
  段落条目支持纯字符串（自动剥前缀编号）或对象（`paragraph_id/id/pid` +
  `text/content/body`）。`tables/figure_captions/references` 若独立给出则并入清单。
- **完整性审计**：四类机械检查（空文本、控制字符/U+FFFD、段尾无终止标点、
  重复编号），全部可复核。
- **版本坐标**：每段 SHA-256 前 8 位写入材料清单；同编号多段时消歧依据。
- **读取留痕**：`mark` 只追加、幂等去重；`coverage` 输出可直接并入 result.json。

## audit 输出文件

- `case_norm.json`：归一化案例，含每段的 `section`（abstract/body/table/caption/reference）与 `sha256`。
- `inventory.md`：材料清单表，第一行即完整性统计。

## 退出码约定

| 退出码 | 含义 |
|-|-|
| 0 | 正常 |
| 2 | 输入损坏；input_error 骨架已写出 |
| 1 | check 子命令发现 ERROR（引文不逐字、字段缺失、枚举非法等） |

## 与其他路线的边界

本 Skill 不重复做检索排序（另有证据地图路线）、不重复做审计循环（另有
对抗审核路线）、不重复做契约拼装（另有渲染路线）。它只保证一件事：
**下游消费的一切"原材料"与"读取记录"都是真的**。

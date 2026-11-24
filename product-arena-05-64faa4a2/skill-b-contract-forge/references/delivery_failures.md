# 交付错位失败模式集（contract-forge 的对治清单）

按发生频率与危害排序。每条给出：症状 → 后果 → 本 Skill 的对治环节。

## F1 result.json 缺契约字段

- 症状：output_contract 声明 5 个字段，result.json 只有 3 个；或字段名被"规范化"改写
  （`needs_human_review` → `review`）。
- 后果：评测按字段名取数，缺字段直接零分，正文再好也无效。
- 对治：contract_probe 逐字段提取 → 骨架含全部字段 → 门禁 G3 逐字段验收。

## F2 case_id 串案例

- 症状：批量运行时沿用了上一案例的骨架，case_id 与 case.json 不一致。
- 后果：整案判错，且属于难以自查的静默错误。
- 对治：骨架的 case_id 只来自 contract.json（即 case.json 实际值）；门禁 G2 逐字符比对。

## F3 路径冒充正文

- 症状：`artifact` 字段填了 `chapter.md` 路径，但 /app/output 下没有该文件；
  或文件存在但为空/只有标题。
- 后果：评测打开产物为空，按未交付处理。
- 对治：门禁 G4 校验引用文件真实存在于 /app/output（材料引用回查 /input）；
  G3 对空值判 FAIL。

## F4 预览缺失或伪造

- 症状：契约要求可编辑产物附渲染预览，但只交了 md；或截图/SVG 与正文不符、
  是手工拼的占位图。
- 后果：判"不可核验"。
- 对治：preview_render 从 chapter.md 真实渲染 SVG；门禁 G5 检查预览文件存在。
  预览必须由脚本生成，禁止手工绘制冒充。

## F5 把示例当正式结果

- 症状：直接复制 examples/ 下的合成骨架或示例文案进 /app/output。
- 后果：合成数据污染正式交付，属学术不端级错误。
- 对治：examples/ 所有产物带"合成示例，非正式案例结果"标注；正式交付的 result.json
  不得含 `skeleton_meta.warnings` 未消除的保守默认字段；填充时逐字段对照材料。

## F6 pending 残留

- 症状：预算耗尽或遗忘，result.json 里仍有 `status: "pending"` 的骨架字段。
- 后果：评审视为未完成的半成品，且暴露流程失控。
- 对治：尽早保存（骨架先行 + 增量填充），门禁 G3 对 pending 判 FAIL。

## F7 partial 不说明局限

- 症状：`status: "partial"` 但 uncertainty 为空，评审无法知道缺什么。
- 后果：诚实性存疑，从严判为不合格。
- 对治：门禁 G3 要求 unavailable/partial/unknown/failed 必须附原因；
  写法见 references/contract_patterns.md 第三节。

## F8 正文数值不可回溯

- 症状：章节里写"准确率 0.87"，但所有材料中找不到 0.87；sources 列了文件却给不出定位。
- 后果：判编造数据。
- 对治：门禁 G6 抽样正文数值、在 sources 指向的材料中定位；定位不到记 WARN 要求人工确认；
  写作时每处数值当场记录来源 locator。

## F9 产物放错目录

- 症状：result.json 写在 /app/work，或正文写在 /app/output 而 result.json 里引用 /app/work 路径。
- 后果：评测只读 /app/output，等于未交付。
- 对治：路径约定写入 SKILL.md 运行时契约与 WORKSPACE.md；门禁 G4 以 /app/output 为基准校验。

## F10 result.json 非法 JSON

- 症状：手工编辑引入尾逗号、未闭合引号、混入注释。
- 后果：解析失败，全部字段取不到。
- 对治：始终用脚本/结构化方式写 result.json；门禁 G1 首先校验 JSON 合法性，
  非法时后续检查全部无法执行，优先修复。

# 异常分类学（anomaly taxonomy）

科研成果转化写作管线的输入异常分四类。每条异常登记为
`{kind, locator, evidence, disposition, note}`，`disposition ∈ proceed / mark-gap / halt`。

## 1. missing_input（材料缺失）

- **证据**：case.json 任一字符串值或 task.md 文本中引用到的文件路径
  （按扩展名白名单识别：md/csv/txt/json/pdf/docx/xlsx/cif/dat/png/jpg）
  在磁盘上不存在，或存在但大小为 0 字节。
- **处置**：
  - 个别缺失 → `mark-gap`：相关字段留空，缺口写入 result.json 的 limitations，
    管线继续；
  - 全部被引用文本输入均缺失/为空 → `halt`：无可加工材料，停止管线，
    `anomaly_triage.py` 退出码 2，result.json 定 failed。
- **对 result.json 的影响**：mark-gap 时对应交付字段必须留空并列入
  limitations（禁止编造内容填坑）；halt 时 status=failed 并附原因。

## 2. conflict（跨文件数值冲突）

- **证据**：同一锚点语境出现不同数值。锚点提取：数字前 ±10 字符窗口内
  最后一个长度≥2 的中文/英文词；锚点间最长公共子串 ≥4 字即归并为同一
  指标语境（容忍"电芯后能量密度"与"能量密度以"之类前缀/系词差异）。
  年份（1900–2100）降噪剔除。仅跨文件冲突上报。
- **处置**：`mark-gap`。保守误报可接受，**一律列入人工确认**；确认前
  冲突数值不得写入任何交付物，草稿中保留缺口占位。
- **对 result.json 的影响**：limitations 记录"锚点 + 各文件取值 +
  待人工确认口径"；确认后修改源材料并重跑受影响阶段。

## 3. confidentiality（涉密/未发表标记）

- **证据**：命中关键词 保密、机密、confidential、未发表、embargo、
  内部资料、不得外传（英文关键词大小写不敏感）。
- **处置**：`proceed` —— 允许本地继续处理，但 **仅本地处理、禁止外发**，
  限制必须显式写入登记条目与 result.json 的 limitations。
- **对 result.json 的影响**：limitations 追加"仅本地处理，禁止外发"
  限制项；该限制不阻断 complete 之外的判定，但属于交付元数据的一部分，
  交付前须由人确认发布渠道合规。

## 4. length_conflict（篇幅约束冲突）

- **证据**：task.md 中解析出字数上限（"不超过 N 字 / N 字以内 / ≤N 字"等），
  且上限低于源文关键信息所需下限的启发式估计：
  `下限 = (数值个数 + 标题数 + 列表项数) × 25 字`。
- **处置**：`mark-gap`。与需求方确认或主动删减覆盖范围；禁止超字数硬塞，
  也禁止为凑字数丢弃已声明的关键信息而不留痕。
- **对 result.json 的影响**：limitations 声明"篇幅约束冲突，已删减覆盖
  范围 X/Y/Z"；word_count 字段必须如实填写。

## 通用规则

- 同一事实只登记一次，按 `(kind 序, locator)` 排序输出，保证确定性。
- `halt` 优先级最高：存在任一 halt 项即整体停管线（退出码 2）。
- 所有 mark-gap 项必须在 result.json 的 limitations 中有对应条目；
  finalize 时 limitations 非空即不得标 complete。

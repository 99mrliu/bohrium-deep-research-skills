# 渲染风格规则（style rules）

## 命名

- 答案卡文件名：`q_<question_id>.md`（非字母数字替换为下划线）。
- 不复制、不重命名库内原文件；交接包通过 catalog.csv 的 file_id ↔ relpath
  映射引用原文件，避免在输出目录制造第二份事实。

## 语言与措辞

- 交接文档使用书面语；状态词只用枚举：ok / unreadable / empty /
  unsupported_type / 待答 / 库中无依据。
- 版本判断措辞："依据文件名标记 v2"或"依据行政备注（坐标）"；禁止无依据
  的"应该是最新版"。
- 每个数字都要带出处坐标；没有坐标的数字宁可不写。

## 索引页结构（knowledge_index.md）

1. 文件树（带 file_id 标注）；
2. 版本与重复（链到 version_notes.md）；
3. 问题与答案卡索引（逐题链接）；
4. 编目（链到 catalog.csv）。
四段缺一不可，link_check 只验链接，结构完整由本规则自查。

## 何时不要渲染

库内 0 个可读文件时，仍生成交接包，但 knowledge_index.md 顶部写明
"本库当前无可读文件（原因见 version_notes.md）"，result.json 标 partial。
禁止渲染一个看似正常实则空心的交接包。

# 字段字典（field dictionary）

metadata_registry.jsonl 中 `field` 的规范取值。字段集合为缺省 9 个，可被 case.json 的 `metadata_fields|extra_fields|fields` 或 task.md 约定**防御式合并**扩展（仅接受 `[A-Za-z][A-Za-z0-9_]{0,31}` 新名，非法名忽略）。

| 字段 | 含义 | 别名（伴随表列名/备注键名/内容模式，大小写不敏感） | 示例值 |
|---|---|---|---|
| project | 项目/课题编号 | project, project_id, project_code, grant, grant_no, 项目, 项目号, 课题, 课题号, 项目编号 | NSFC-22173001 |
| year | 年份（4 位） | year, 年份, 年度 | 2021 |
| data_type | 数据类型 | data_type, datatype, type, 数据类型, 类型 | raw_data / summary / notes / report |
| author | 作者/负责人 | author, authors, owner, 作者, 负责人 | 张三 |
| instrument | 仪器型号 | instrument, device, 仪器, 仪器型号, 设备 | Thermo Orbitrap Exploris 480 |
| version_note | 版本备注 | version_note, version, 版本备注, 版本说明 | v1 / 最终版 |
| retention | 保存期限 | retention, retention_period, 保存期限, 保存期 | 长期 |
| access_scope | 访问权限范围 | access_scope, access, 访问权限, 权限范围, 权限 | 内部 |
| source_party | 来源单位/提供方 | source_party, source, 来源, 来源单位, 提供方 | 分析测试中心 |

## 取值规则

- 值一律为字符串，落盘前 strip；空值不入 registry（即"诚实留空"）。
- 伴随表中无法映射到任何字段的列被忽略（不静默发明字段名）；扩展字段以原名直接使用。
- **强文件属性**（project、year、data_type、version_note）必须有文件级证据（L1 随行记录 / L2 内容 / L3 文件名 / L4 裁定），不接受全局行政备注默认。
- **可全局默认**（GLOBAL_NOTE_FIELDS）：instrument、retention、access_scope、source_party、author；且全局备注只下发给已有至少一条文件级证据的文件（避免给毫无关联的便条贴仪器型号）。
- 每个字段值在 registry 中的形态：
  `{"file", "field", "value", "level", "source_kind", "locator", "pattern_id", "confidence", "note"}`
  缺 locator 的字段值**不允许存在**——元数据没有 provenance 就等于没有元数据。

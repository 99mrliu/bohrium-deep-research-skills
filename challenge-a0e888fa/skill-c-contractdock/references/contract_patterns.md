# output_contract 常见形态与填写规范

## 形态

合同中字段声明常见三种（contract_extract.py 均已兼容）：

1. 字典型：`{"output_contract": {"cleaned_table": {"type":"string","description":"清洗表路径"}, ...}}`
2. 列表型：`{"output_contract": [{"name":"cleaned_table","type":"string"}, ...]}`
3. 嵌套型：字段路径带层级，如 `{"outputs": {"tables": {"cleaned": {...}}}}`
   → 字段路径记为 `outputs.tables.cleaned`，骨架按同层级生成。

## 填写规范

| 合同类型 | 填法 | 常见错误 |
|---|---|---|
| string（文件路径） | 相对 /app/output 的路径，文件必须真实存在 | 写了路径但没生成文件（验收项 2 拦下） |
| string（说明文字） | 一句话，含依据定位 | 长篇散文、与数字矛盾 |
| integer/number | 实测值；来自重算而非手抄 | 布尔 true 被当 1（验收按类型拦下） |
| array | 每项一个对象/字符串，宁可空数组也要在 | 缺键（验收项 1 拦下） |
| object | 子字段齐全 | 只填一部分子字段 |

## status 与不确定性

- `status`: success（全部完成）/ partial（部分完成，必须配 limitations）/
  failed（硬失败，说明断点与已保住的中途产物）。
- 不确定性字段填法：每条 `{item, reason, action_taken}`——例如未知单位保留原值、
  键冲突全部保留待复核、千分位/小数逗号歧义列未转换。
- 材料缺失、无法判断、运行失败**分开说明**，不混写。

## 时间不够时的降级顺序

1. 保 result.json 结构合法 + status=partial + limitations；
2. 保 cleaned.csv 与 ledger.csv（哪怕是中间态，命名如实）；
3. 保报告三件套（重算很快，总是跑得完）；
4. 放弃美化与额外分析。

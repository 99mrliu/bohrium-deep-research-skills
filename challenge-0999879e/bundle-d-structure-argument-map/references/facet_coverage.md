# 六分面最低检查点（facet_coverage）

本 bundle 的深查面是**整体质量 / 结构完整性与论证链**；其余五个分面按下列最低检查点
轮查登记，不做深查。状态值只允许：
`checked_clean` / `issues_found` / `partially_checked` / `unable_to_check`。

| 分面 | 最低检查点（本 bundle 内机械可及） | 典型状态 |
|---|---|---|
| 事实核验 | 结论节数值与结果节数值跨节一致性（X1 扫描复用）；稿件版本 SHA-256 已记录 | partially_checked（外部事实不核） |
| 引用支持 | 参考文献小节存在性（角色矩阵）；文中引文标记 [n]/(Author, year) 形式存在性 | 有参考文献小节 → partially_checked；无 → issues_found；无法抽取文本 → unable_to_check |
| 方法设计 | 设计类型关键词抽取（横断面/观察性/RCT/队列），供因果判定与链边 L2→L3 核对 | partially_checked（样本量、偏倚控制不深查） |
| 统计报告 | 结果节是否出现最低统计量报告（p 值 / 置信区间 / ±标准差 / 相关系数） | 出现 → checked_clean；完全无 → issues_found；结果节缺位 → unable_to_check |
| 论证链 | 六环登记 + C1/C2/X1/Q1 候选扫描 + Agent 处置 | 本 bundle 深查面：有 confirmed 问题 → issues_found；扫描完成且无确认问题 → checked_clean；登记或扫描缺失 → partially_checked |
| 学术规范 | 声明性文字（伦理/利益冲突/数据可得性）存在性粗查；不查重、不核署名 | partially_checked |

## 登记规则

1. 每个分面必须在 result.json 的 `facet_coverage` 字段中有一条记录，含 status 与
   一句话 note，禁止留空。
2. 深查面之外的分面即使发现明显问题，也只登记 finding 并标注 `facet` 与
   `severity`，不展开深查；在 note 中写明"超出本 bundle 深查范围"。
3. 文本抽取失败时，除"事实核验"（SHA-256 仍可记录）外所有分面标 unable_to_check，
   并在 uncertainty 中说明。
4. 状态升级方向只能从严：机械检查未覆盖的子项一律视为未查，不得因"没扫到问题"
   就把 partially_checked 写成 checked_clean。

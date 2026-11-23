# 版本模型（version model）

本 Skill 把"两篇论文的图谱"建模为 **一次封存 + 一次增量变更**：

```
primary 论文 --(baseline-candidates)--> [verify] --> graph v1（sealed，永不改写）
graph v1 + secondary 论文 --(changeset)--> [verify] --> [apply] --> graph v2（current）
```

## 版本语义

- **v1（baseline，封存）**：只含 primary 论文的实体、关系与证据。`sealed: true`。
  `kg_apply.py apply` 只读它、绝不回写；负向测试 T4 实测 apply 前后该文件逐字节不变。
- **v2（current）**：v1 的深拷贝 + 变更集应用结果。`base_version: "v1"`。
  v2 可作为下一次增量的新基线（再封存为 v2'，依此类推）。
- 两个版本同时交付（`graph-baseline.json`、`graph-current.json`），查询器对两个版本
  都可执行，`node_history` / `diff_summary` 做跨版本对比。

## 稳定语义 ID

- **节点 ID**：`n_<类型缩写>_<sha1(类型|规范化标签)[:8]>`。规范化 = 小写、去标点、
  压缩空白。ID 只取决于语义内容，与候选顺序、运行次数、机器无关。
- **边 ID**：`e_<关系缩写>_<sha1(起点|终点|关系|value|condition)[:8]>`。
  因为 value/condition 参与哈希，**不同论文的不同数值天然落在不同的边上**，
  从机制上杜绝"把 158 和 149 合并成一条边"。
- **撞键（同名不同对象）**：规范化标签相同但锚点（source_id+paragraph_id）不同
  （典型如两篇都用通用术语 "commercial carbon black"），按确定性顺序
  （来源在 manifest 中的次序 → 段落 ID）追加 `_2`、`_3` 后缀。
  因为 baseline 来源永远排在最前，**既有记录的 ID 永不改号**；新记录只追加。
- **锚点复用**：同一锚点再次出现（重跑、重复应用同一变更集）时复用原 ID，
  不新建记录——幂等性的基础（负向测试 T1 实测两次运行输出逐字节一致）。

## MERGE 与 ID

MERGE 不创建新节点再删除旧节点，而是：幸存者保留原 ID，`aliases` 追加被吸收标签
及其证据与合并依据，`evidence` 只增不删，`history` 追加一条 MERGE 记录。
被吸收标签登记进注册表，后续同标签引用（如 secondary 的边端点 "LFP/C"）自动解析到
幸存者。没有任何记录被删除或改号。

## history 字段

每个节点/边带 `history` 列表：`{version, op, note}`，只追加。版本差异器
（`kg_diff.py`）对比时忽略 history，只报告语义字段的 before/after。

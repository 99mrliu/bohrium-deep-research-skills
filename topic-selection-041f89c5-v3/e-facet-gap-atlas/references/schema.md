# 记录模式（records.jsonl schema）

每行一个 JSON 对象，字段如下（全部必填；取不出填 `unreported`）：

| 字段 | 类型 | 说明 |
|-|-|-|
| record_id | 字符串 | 唯一 ID，建议 `来源文件名` 的短写 |
| title | 字符串 | 文献标题（或材料中的等效标识） |
| year | 整数 1900–2100 | 发表年份 |
| venue_kind | journal / conference / preprint / report | 载体类型（受控枚举） |
| task | 字符串 | 该文献解决的任务（受控词表） |
| method_family | 字符串 | 方法族（受控词表，如 机器学习/物理建模/高通量实验） |
| data_domain | 字符串 | 数据或体系（如 数据集D / 钠电正极） |
| metrics | 非空字符串数组 | 报告了哪些指标（原名照抄，不做单位换算） |
| headline_result | 字符串 | 一句话主结果（含数字与方向） |
| limitations | 字符串 | 自述或可见的局限 |
| comparability_class | 字符串 | 可比性类别：同一类的记录才可直接比数字 |

## 受控词表规则

1. 提取前先起草 vocabulary.md：task、method_family、data_domain 三个字段
   各自的合法取值；提取过程中发现新概念才允许增补，增补即记录。
2. 同一概念只许一个词（"ML"/"机器学习" 二选一）；同义词会让空白格
   计算失真——机器分不清它们，会把同一格拆成两格。
3. `unreported` 是保留字：材料确实没写时填它，不许猜；它在矩阵中
   会形成自己的"格子"，本身就是可比性问题的信号。

## 校验规则（atlas.py validate）

- 必填字段缺失、year 越界、venue_kind 越枚举、metrics 为空或非字符串数组
  → 错误（exit 1）；
- (task, method_family, data_domain) 三元组重复 → 警告（人工核对是
  独立研究还是重复登记）。

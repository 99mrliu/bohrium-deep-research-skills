# 审计口径与解释边界

## 文件身份与表格观测

- SHA256 对文件原始字节计算；manifest 中的 `sha256` 是声明值，`actual_sha256` 是本次计算值。一致仅证明本次文件与所声明字节一致，不证明来源真实、作者身份或科学有效性。
- CSV 第一行是表头，完全空白行忽略，其余每行是一条记录。列名必须唯一且非空，所有记录必须与表头等宽。默认只把空字符串视为缺失；可用 `missing_values` 显式增加字面值。比较使用单元格字符串的精确值，不擅自做数值归一化、大小写折叠或缺失插补。
- 类型是在非缺失观测上的描述：`integer`、`number`、`boolean`、`string`、`mixed` 或 `empty`。它不改写原始 CSV，也不证明语义类型。
- 全行重复组按文件内整行所有列的精确值定义；`duplicate_excess_rows` 是每组重复行数减一的总和。`target_distribution` 同时报告缺失 target。

## train/test 交叉重复

split 的 train/test 文件集合由 manifest 的 `split.train_file_ids` 和 `split.test_file_ids` 指定，与文件名无关。

1. **full-row 交叉重复**：两端列名集合相同，以所有列名和值作键；同键至少各出现一次即一组。schema 不同则标为不可比，不能偷偷改成共同列比较。
2. **feature-only 交叉重复**：只使用 manifest 的 `features.names`，保持其声明顺序；同键至少各出现一次即一组。target、额外 ID 或其他非 feature 列不参与键。
3. **target-conflicting feature group**：同一 feature-only 键在 train/test 合并后出现超过一个 target 字面值。它是审计线索，不是自动泄露判据。
4. 重复详情最多列 100 组以免报告膨胀，但总计数基于全部行。缺失值也参与精确键；高缺失造成的碰撞应谨慎解释。

## 论文声明

`n_rows`：对 locator 的 `file_ids` 行数求和。`n_features`：使用 locator 的 `feature_names`，未给出时使用 manifest features；同时在指定文件中验证这些列存在。`split`：期望对象是 `{"train": 非负整数, "test": 非负整数}`，locator 可覆盖 train/test 文件 ID。

只有 `page`、非空 `quote`、有效 `locator` 都存在才计算 `verified` 或 `mismatch`。缺任一证据返回 `unverifiable`。这里的 `verified` 仅表示记录的预期数值与本次文件计算一致，不表示 quote 已经与 PDF 原件逐字核对，更不证明论文数据就是当前文件。

## 不允许的自动结论

重复、分布偏移、整数比例、缺失模式或 target 冲突均不能单独证明数据合成、伪造、切分泄露或标签泄露。需要仓库历史、生成代码、采集时间、字段语义、作者材料或其他独立证据才能加强结论。原始数据不可得时，只能描述本次提供物。

对本 Skill 的 synthetic 示例，这些重复是人为设计的测试装置，不是正式案例发现。

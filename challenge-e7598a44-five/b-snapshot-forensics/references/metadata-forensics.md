# 元数据法证与夹具处理纪律

## 署名清单的定位

按序尝试：`case.json` 顶层键（`attributed_papers` / `reference_list` /
`references` / `refs` / `paper_list`）→ 输入目录内 JSON 文件中的同名嵌套键。
找不到时 `metadata_forensics.json` 记 `status=no_reference_list` 并写入
uncertainty——**清单缺失是事实声明，不是错误**，筛查照常进行。

## 匹配与逐字段比对

匹配是"找得到"的问题，比对是"对不对"的问题，分开报告：

1. **匹配**：清单 DOI 与快照记录 DOI 精确相等（大小写归一）→ 直接命中；
   否则用标题拉丁词重叠度（`|交| / min(|清单|, |快照|)`），最高分 ≥0.5 判
   找到，否则判 `absent`。
2. **比对**：对找到的记录逐字段核验，每个字段独立判 `match` / `diff` /
   `snapshot_missing`（清单给了但快照没有该字段，不算矛盾，算信息缺口）：

| 字段 | 判据 | 备注 |
|-|-|-|
| doi | 归一化后字符串相等 | 清单未给 DOI 则跳过该字段 |
| year | 整数相等 | 差异是最常见的清单错误（预印本/正式版年份） |
| first_author | 姓氏（最后一个空白分隔 token）小写相等 | 对 "Zhang, Wei" 类倒装写法会误判，见"已知局限" |
| venue | 归一化后字符串相等 | 期刊缩写差异会报 diff，需人工看一眼 |

3. **判定**：所有被检字段无 `diff` → `authentic`；任一 `diff` → `mismatch`
   并逐项列出"清单值 vs 快照值"；未找到 → `absent`。
4. 匹配目标**包括隔离中的记录**（法证面向快照事实：记录存在与否与是否可信
   是两回事），命中隔离记录时 `matched_record_quarantined=true` 提示人工。

## 三值判定的承诺

- `authentic`：清单所述与快照证据在可比字段上完全一致——可信，不是"已联网
  验证"（本技能零网络，快照之外的世界不存在）。
- `mismatch`：清单与快照在同一字段上给出不同值。逐项列出差异，**不替用户
  裁决哪边对**；写入 uncertainty，状态降为 partial。
- `absent`：有限快照内无任何记录可对应。不补造、不猜测出处，如实报告。

## 夹具标记处理纪律

| 标记 | 处置 | 纪律 |
|-|-|-|
| `synthetic_duplicate` / `duplicate_of` | 隔离登记 | 是输入事实不是待生成答案；不参与计数与筛查 |
| `conflict_opinion` | 隔离登记 + uncertainty 提示 | 登记为争议证据，**不做学术裁决**，留待人工 |
| `fixture` / `is_fixture` / `synthetic` | 隔离登记 | 同上 |
| 无标记但结构残缺（无标题） | 隔离登记 | `malformed_no_title`，与夹具区分登记 |

任何"把夹具记录悄悄筛掉/删掉"的做法都违反本纪律：隔离集合必须完整出现在
`quarantine_register` 中，可逐条复核。

## 已知局限（如实声明）

- 第一作者比对按"最后一个 token 是姓氏"假设，对倒装写法与单名作者会误判
  diff——此时 diff 是"需要人工看一眼"的信号，不是终审结论。
- 标题重叠度只用拉丁词，纯中文标题间的匹配能力弱；清单文献通常有 DOI，
  DOI 路径不受影响。

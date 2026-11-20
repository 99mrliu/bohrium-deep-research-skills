# 理由码简表（reason_code）

每条标注必须填一个理由码；可在码后附一句短注（填 note 字段）。
标注者不得空码（validate_annotations.py 强制）。

## 纳入类

| 码 | 含义 |
|---|---|
| INC-CRIT | 人群/干预/结局/设计整体满足纳入标准 |
| INC-POP | 目标人群匹配（含亚组可单独提取） |
| INC-DES | 研究设计匹配（如 RCT） |
| INC-OUT | 目标结局有报告 |

## 排除类

| 码 | 含义 |
|---|---|
| EXC-POP | 人群不符（病种、年龄段等） |
| EXC-INT | 干预/暴露不符 |
| EXC-OUT | 未报告目标结局 |
| EXC-DES | 设计类型不符（综述、社论、病例报告等） |
| EXC-LANG | 语言限制 |
| EXC-TYPE | 文献类型不符（会议摘要/预印本等，按案例标准） |
| EXC-DUP | 重复记录（仅说明用；精确去重已由脚本完成） |
| EXC-INFO | 信息不足按排除处理（需说明依据，可能触发仲裁） |

## 不确定类（uncertain 时 note 必填，说明缺什么信息）

| 码 | 含义 |
|---|---|
| UNC-META | 摘要/元数据缺失，无法判定 |
| UNC-AMBIG | 标准解释存在歧义，需仲裁 |
| UNC-BOUND | 边界情形（人群部分重叠、仅摘要可及等），需仲裁或全文 |

## 仲裁溯源码（adjudicate.py 自动生成）

| 码 | 含义 |
|---|---|
| ARB-D1 / ARB-D2 / ARB-D3 / ARB-D4 | 经仲裁的终判，类型见 disagreement_taxonomy.md |

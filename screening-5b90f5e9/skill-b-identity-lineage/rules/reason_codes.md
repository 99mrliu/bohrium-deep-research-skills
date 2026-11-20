# 筛选理由码简表（reason_codes）

理由码前缀必须与 decision 一致（screen_canonical.py 强制校验）：
`include → IN-*`、`exclude → EX-*`、`needs_human → BND-*`。

## IN-*（纳入）

| 码 | 含义 |
|---|---|
| IN-POP | 符合目标人群/问题范围 |
| IN-INT | 符合目标干预/暴露/技术主题 |
| IN-DESIGN | 符合研究设计要求（如原始临床研究） |
| IN-OUT | 报告了目标结局 |

## EX-*（排除）

| 码 | 含义 |
|---|---|
| EX-POP | 人群/研究对象不符（含纯计算、体外、动物，视案例标准） |
| EX-INT | 干预/主题不符 |
| EX-OUT | 未报告目标结局 |
| EX-DESIGN | 研究类型不符（综述、社论、方案、评论等，视案例标准） |
| EX-LANG | 语言不符 |
| EX-NODATA | 题录损坏到无法判定且无法获取（慎用，优先 BND-*） |

## BND-*（边界，需人工；禁止冒充已裁定）

| 码 | 含义 |
|---|---|
| BND-ABSTRACT-ONLY | 摘要缺失或信息不足，需人工获取全文 |
| BND-CONFLICT | 输入标注/元数据冲突，需人工裁定 |
| BND-UNCLEAR | 标准适用性不明确，需人工裁定 |

## 使用规则

- include/exclude 必须附 `evidence_quote`：title/abstract 的原文片段
  （脚本按 NFKC+小写+压缩空白归一化后做子串锚定，失败 exit 3 重锚）。
- needs_human 可免引用，但 `note` 必填，说明为什么无法自动判定。
- 一条判定一个主理由码；次要理由写入 note。

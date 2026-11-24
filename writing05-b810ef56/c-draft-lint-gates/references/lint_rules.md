# 草稿静态检查规则（Lint Rules）

## 标注约定（成稿必须遵守）

- 论断标记：每个事实句以 `〔C编号〕` 结尾，编号对应证据登记中的
  `claims[].id`；
- 引文标记：`[n]` 对应 `refs[].n`；
- 数字纪律：成稿中每个数字必须能在某条证据的 `quote` 原文中逐字
  找到，或列入 `number_allowlist` 并写明理由（如"第 3 节"这类结构
  性数字）。四位年份（19xx/20xx）与引文标记 `[n]` 内的数字自动豁免。

## 证据登记表结构（evidence_registry.json）

```json
{
  "claims":    [{"id": "C1", "text": "论断原文", "evidence_ids": ["E1"]}],
  "evidence":  [{"id": "E1", "source": "paper_a.txt",
                 "quote": "逐字摘录", "strength": "high|moderate|low"}],
  "refs":      [{"n": 1, "title": "...", "authors": "...", "year": 2024}],
  "number_allowlist": [{"value": "3", "reason": "章节编号"}]
}
```

`strength` 由模型按研究设计判定：多项一致证据/指南=high，单项研究
=moderate，初步/间接证据=low。判定理由写入证据表。

## 规则清单

| 规则 | 严重度 | 含义 | 触发条件 |
|---|---|---|---|
| PLACEHOLDER | error | 占位符残留 | TODO/TBD/待补充/（略）等 |
| CITE-ORPHAN | error | 引文悬空 | [n] 无对应 refs 登记 |
| NUM-UNTRACE | error | 数字无源 | 数字不在任何 quote 中且不在豁免表 |
| CLAIM-UNKNOWN | error | 论断未登记 | 〔C#〕无对应 claims 登记 |
| OVERCLAIM | error | 措辞越级 | 强结论词 + 证据最高 non-high |
| CAUSAL-SLIP | error | 相关写成因果 | 因果动词 + 证据原文为相关性表述 |
| OVERCLAIM-NOMARK | warning | 强措辞无标记 | 强结论词但无论断标记，无法核验 |
| REF-UNUSED | warning | 文献未引用 | refs 登记但正文未引 |
| UNMARKED-FACT | warning | 事实句无标记 | 含数字但无〔C#〕 |

## 与门禁的关系

lint 只负责"找出来"，裁决在 `gate_check.py`：默认策略（见
`references/gate_policy.json`）为 error 级全部阻断、warning 上限
10 条。确需例外的，在策略文件 `waivers` 中按 规则+行号 豁免并写
理由——豁免记录会进入门禁报告，供评审复核，不允许静默放过。

## 已知边界

- 数字匹配是逐字的：`1.8 mmol/L` 写成 `1.80 mmol/L` 会触发
  NUM-UNTRACE——这正是设计意图（数字必须与原文一致），确属等价
  写法时在 allowlist 说明；
- OVERCLAIM/CAUSAL-SLIP 基于措辞表，存在漏报；模型在写作时仍须
  自觉遵守强度纪律，lint 是兜底不是替代；
- 规则词表集中在 `draft_lint.py` 顶部常量，扩展时同步更新本表。

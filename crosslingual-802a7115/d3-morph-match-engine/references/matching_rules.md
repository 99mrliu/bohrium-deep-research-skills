# 跨语言形态匹配规则（matching rules）

## 归一化通道

每条术语变体生成一组归一化形式，每种形式标注生成规则，匹配在对应通道进行：

| 规则名 | 变换 | 适用场景 |
|-|-|-|
| `nfkd_fold` | NFKD 分解去组合符＋小写 | 变音字符（São→sao、Müller→muller）、大小写 |
| `umlaut_expansion` | ä→ae、ö→oe、ü→ue、ß→ss 后再折叠 | 德语转写体（Mueller、Strasse） |
| `kana_romaji` / `kana_romaji_folded` | 片假名→Hepburn 罗马字 | 日文音译术语与拉丁转写互查 |
| `suffix_stem` | 拉丁 token 去常见词尾（复数 s/es、-ed/-ing、-os/-as、-ções、-en/-er、-ieren/-ierung），主干≥4 字符 | 词形变化（pyroptoses、inflamações） |

## 匹配规则

1. **拉丁词边界匹配**：`(?<![a-z0-9])form(?![a-z0-9])`，防止 "activation" 误中 "inactivation"。
2. **复合词包含匹配（`compound_match`）**：仅当变体是 ≥5 字符的单个 token 且词边界
   匹配失败时启用；变体作为更长 token 的子串命中（Zellpyroptose ⊃ pyroptose）。
   德语复合词高产，此通道召回必要但精度较低，命中一律标 `compound_match` 供优先人工复核。
3. **CJK/假名直接子串**：中日文无词边界，子串匹配是唯一可行表面规则；
   假名变体同时在其罗马字通道匹配拉丁语料中的转写出现。
4. **混排标题**：一段文本可同时含多脚本；所有通道都跑，命中分通道记录，不去重——
   同一位置被两条规则命中时两条都保留，复核者可见规则冗余。

## 精度与召回的权衡

- 变音折叠与词形还原提高召回；误伤风险由"逐命中归因＋人工复核"控制，不靠静默提高阈值。
- unverified 变体（回译未通过或缺回译证据）照常参与匹配——漏检比假阳性更难发现；
  但每条命中带 verified 标志，下游排序可降权，审计可过滤。
- 词形还原只做轻量后缀剥离，不做词干化算法（Porter/Snowball）：宁可少还原，
  保证每条 matched_form 与原文差异可解释。

## 证据格式

每条命中：`lang`（变体语种）、`term`（变体原文）、`verified`、`rule`、
`matched_form`（实际命中的归一化形式）、`offset`（折叠文本中的字符区间）、
`context`（±60 字符窗口）。复核者可据 rule 重放变换并定位原文，无需信任引擎。

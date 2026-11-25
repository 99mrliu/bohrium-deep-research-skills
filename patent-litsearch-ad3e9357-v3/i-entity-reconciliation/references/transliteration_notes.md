# CJK 与罗马化姓名处理边界(Transliteration Notes)

## 核心原则

**罗马化的 CJK 姓名在没有旁证(corroboration)时,绝不静默等同。**

## 语序问题(family/given order)

中文、日文、韩文姓名的罗马化写法在 family-first 与 given-first 之间摇摆:
"Zhang Wei"(张伟,汉语拼音 family-first)与 "Wei Zhang"(西式 given-first)可能指向
同一人,也可能指向两个完全不同的人(张伟 vs 张威、魏章……)。仅凭 token 多重集相同
**无法**区分这两种情形。因此:

- `entity_match.py` 检测到"两侧均为 person、token 多重集相同、语序不同"时,
  打 `order_variant` flag,**强制 candidate 档**;
- 该 flag 不随阈值调整而豁免;即使把 `low` 降到 0,order-variant 对也不会进入 auto;
- 可接受的旁证(需在对账表 uncertainty 中注明来源):相同的机构/单位、相同的
  合作者网络、ORCID 等持久标识、同一文献族中的自引用。没有旁证 → 保持 candidate。

## 罗马化系统的多样性

同一汉字姓名可能有多种罗马化:拼音 / Wade-Giles / 粤语拼写 / 日文罗马字(训读、
音读、护照拼写)/ 韩式罗马字修订版与 McCune-Reischauer。例如 "Tsai"/"Cai"、
"Park"/"Pak"、"Roh"/"Noh"。本技能**不内置**任何罗马化等价表——这类表本质上是
概率性的,内置即意味着静默等同。如需启用,应当:

1. 在 policy JSON 之外显式维护一份人工审定的别名表;
2. 把别名表命中的对子仍归入 candidate 并记录依据;
3. 在 `change_records` / `uncertainty` 中声明该表的存在与版本。

## 首字母缩写

"P. Nair" 这类首字母形式通过 `initial_surname` 特征获得候选信号,但首字母碰撞极常见,
同样只落在 candidate。绝不允许把首字母展开为具体名字(如把 "P." 写成 "Priya")——
那是编造。

## CJK 原文姓名

- R3 保留 CJK 字符;R2 不改变 CJK;`株式会社` 等 CJK 后缀形式在
  `legal_suffix_table.json` 中按原样收录。
- 2–4 个 token 的 CJK 串判为 person(见 R5);更长的 CJK 机构名通常先被 R4
  或机构关键词捕获。
- 简体/繁体差异(如 "张" vs "張")**不会**被自动折叠;如语料混用,应视为
  candidate 线索并在 uncertainty 中说明,而非静默等同。

## 缺失即 null

任何一侧信息缺失(如论文未给机构、专利记录发明人字段为空),对账行相应字段
一律为 `null`,并在 `uncertainty` 中声明"该侧信息缺失",**绝不**用猜测值填充。

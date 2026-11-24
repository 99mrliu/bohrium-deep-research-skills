# claims.json 与 anchors.json 字段定义

## anchors.json — 锚点登记表

```json
{
  "own_data": [
    {"id": "D01", "type": "figure", "source": "图 1：……", "key_fact": "……"},
    {"id": "D02", "type": "table",  "source": "表 1：……", "key_fact": "……"},
    {"id": "D03", "type": "stat",   "source": "统计输出 A：……", "key_fact": "……"}
  ],
  "literature": [
    {"id": "L01", "ref": "作者. 题名. 刊名, 年."}
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| own_data[].id | 是 | `D` + 数字，如 D01；一图/一表/一项统计输出一个锚点 |
| own_data[].type | 是 | figure / table / stat |
| own_data[].source | 是 | 该锚点指向材料中的哪个图、表或统计输出 |
| own_data[].key_fact | 建议 | 该锚点锚定的关键数值事实，供写作时直接引用 |
| literature[].id | 是 | `L` + 数字，如 L01；与文献表条目一一对应 |
| literature[].ref | 是 | 文献条目原文，照抄材料，不改写 |

规则：只登记材料中**实际存在**的图/表/统计输出与实际给出的文献；
查不到的文献在 uncertainty 记 gap，不得登记编造条目。

## claims.json — 论断台账

```json
[
  {
    "id": "C01",
    "text": "论断正文（将逐字出现在讨论中，允许空白差异）",
    "anchors": [
      {"id": "D01", "relation": "支持"},
      {"id": "L02", "relation": "一致"}
    ],
    "strength": "直陈"
  }
]
```

| 字段 | 必填 | 取值与说明 |
|---|---|---|
| id | 是 | `C` + 数字，全表唯一 |
| text | 是 | 论断正文。脚本按"去除全部空白"后与 discussion.md 做子串匹配；句内锚点 [Dnn]/[Lnn] 不算入正文 |
| anchors | 是 | 至少 1 条；空数组 = 孤儿论断，ERROR |
| anchors[].id | 是 | 必须存在于 anchors.json，否则 ERROR |
| anchors[].relation | 是 | 自数据锚点（D）固定为「支持」；文献锚点（L）取 一致 / 不一致 / 部分一致 / 机制解释 / 背景 |
| strength | 是 | 直陈 / 初步 / 推测 |

### 语气强度的判定

- **直陈**：论断即数据本身（重述发现、统计显著性），或与文献的一致/
  不一致事实陈述；
- **初步**：有间接证据支撑的推断、局限声明；
- **推测**：单一来源或无直接证据的机制解释。

### relation 与措辞的联动（build_matrix.py 规则 c）

| relation | 论断句或相邻句必须出现的措辞 |
|---|---|
| 一致 | 一致、相符、吻合、印证（"不一致"不算） |
| 不一致 | 不一致、不符、相悖、矛盾 |
| 部分一致 | 部分一致、部分相符、基本一致、大体一致 |
| 机制解释 | 不强制措辞，但 strength 应为 推测/初步 |
| 背景 | 不强制措辞 |

## 常见错误

1. **anchors 空数组** → 孤儿论断 ERROR；先补锚点，补不出则删除该论断
   并记入 change_log。
2. **锚点 id 未登记**（claims 用 L05 而 anchors.json 只有 L01–L04）
   → ERROR；先登记，登记依据必须是材料中真实存在的条目。
3. **正文出现未登记锚点**（discussion 里写 [L99]）→ ERROR + cite_check
   幻觉引用 ERROR。
4. **装饰引用**：正文 [Lnn] 未挂进任何论断 → ERROR；要么为它立论断
   （如 relation=背景），要么从正文删去。
5. **D 锚点误用文献关系**（{"id": "D01", "relation": "一致"}）→ ERROR；
   自数据锚点的 relation 只能是「支持」。
6. **论断改写了正文没改台账**（或反之）→ "论断正文未出现" ERROR；
   两边同步，以审计为准。
7. **关系只登记不措辞**（台账写"不一致"而正文含糊其辞）→ ERROR；
   在论断句明说"与 Lnn 不一致"。

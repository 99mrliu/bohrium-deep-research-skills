# 锚点与论断台账 Schema（proposal-anchor-forge）

本文件是管线三类核心数据的字段契约。所有字段名为机器读取的键，不得随意改名。

## 1. anchor_map.jsonl（anchor_extract.py 产出，每行一条）

| 字段 | 类型 | 说明 |
|---|---|---|
| `anchor` | string | 稳定锚点，形如 `M2-P003`：M=材料序号（按文件名字典序），P=段序号（001 起）。同一输入重跑必得同一锚点集。 |
| `material` | string | 材料 id，如 `M2`。 |
| `file` | string | 来源文件名（相对输入目录）。 |
| `para` | int | 段序号，与锚点后缀一致。 |
| `char_start` / `char_end` | int | 段落在「抽取文本」中的字符偏移（含首尾换行剥除后的起点）。 |
| `text` | string | 段落原文。quote 逐字核验的唯一基准。 |

特例：`case.json` 解析成功后按「顶层键: JSON 值」渲染成段落，`manifest` 中该材料
`derived_rendering=true`，偏移对渲染文本有效；JSON 解析失败则退回原始字节。

## 2. fact ledger（论断台账，JSONL，Agent 起草时逐条产出）

| 字段 | 必填 | 说明 |
|---|---|---|
| `claim_id` | 是 | 论断 id，建议 `C001` 起连续编号。 |
| `section` | 是 | 所属开题七要素节（研究背景与缺口/问题定义/目标/技术路线/阶段计划/风险/预期成果）。 |
| `claim_text` | 是 | 写入草稿的论断句。kind=inference 时必须含「推断」二字。 |
| `kind` | 是 | `fact`（事实）/ `number`（数字）/ `citation`（文献引用）/ `inference`（推断）。 |
| `anchor` | 三类必填 | 来源锚点。inference 可空。 |
| `quote` | 三类必填 | 从锚点 `text` **逐字复制**的引文，禁止凭记忆改写。 |

## 3. claim_verification.json（verify_claims.py 产出）

顶层字段：`total / ok / fail / unverifiable / all_verified / link_back_rate / blocked / results`。

- `ok`：归一化（NFKC 全半角折叠 + 空白折叠）后 quote 是锚点文本子串；或无引文的
  inference 且已标注「推断」。
- `fail`：quote 不逐字、anchor 不存在、inference 未标注「推断」。**fail 论断禁止进入交付稿**。
- `unverifiable`：缺 anchor/quote、kind 非法、inference 引文残缺。**同样禁止进入交付稿**。
- `link_back_rate`（回链率）：逐字核验通过且带锚点的论断数 / 论断总数。低于 1.0 说明
  台账中存在未锚定论断（合法 inference 不扣回链分子）。
- `blocked`：被拦截论断的 `claim_id + status + reason` 清单，须同步进 result.json 的
  `uncertainty`。

退出码：0 表示 `all_verified=true`；1 表示存在拦截（供 shell 门控使用）。

## 4. 起草纪律（Agent 侧）

1. 每条事实句/数字/引用先落台账，再把 `claim_id` 以 `[Cxxx]` 形式标进草稿对应句尾。
2. 材料里没有的信息只能写成 inference 并显式标注「推断」，或写入 `uncertainty`。
3. 台账必须整体过核验；被拦截论断要么修正 quote/anchor 后复验，要么从草稿删除，
   不允许「先交付后补验」。

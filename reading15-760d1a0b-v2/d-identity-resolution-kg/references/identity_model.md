# Identity model — 候选生成、归一化键与实体 ID（d-identity-resolution-kg）

本文档定义 `scripts/candidates.py` 与 `scripts/adjudicate.py` 的确定性行为。
所有规则固定、无随机、无墙钟，词表就列在下面（不是从语料学出来的）。

## 1. 归一化键（normalization key）

对任何表面形式（surface form）依次执行：

1. Unicode 下标折叠：`₀₁₂₃₄₅₆₇₈₉` → `0-9`（MAPbI₃ 与 MAPbI3 同键）；
2. 连字符变体折叠：`– — − ‐ ‑` → `-`；
3. 符号折叠：`α→alpha, β→beta, γ→gamma, δ→delta, ×→x, °→deg`；
4. `casefold()`（大小写归一）；
5. 删除所有非字母数字字符（空格、连字符、撇号、逗号、括号全部去掉）。

例：`methylammonium lead iodide` → `methylammoniumleadiodide`；
`MAPbI3` → `mapbi3`；`spiro-OMeTAD` → `spiroometad`；`TiO2` → `tio2`。

## 2. 提及抽取（mention extraction）

对每段文本确定性扫描两类提及：

- **首提缩写定义**：正则 `\(([A-Za-z][A-Za-z0-9\-]{1,19})\)` 命中且括号内含大写
  或数字时，向前收集全名：回溯空白分词，遇句首大写词、停用词（固定表，含
  the/is/report/certified 等常见词）、纯数字单位（如 `85%`）、左括号或达到 6 词
  即停；再削掉头部停用词。`X-ray` 这类"单大写+连字符"开头的词允许入名。
- **独立词元**：满足以下任一者记为提及——
  - formula：首字母大写且含数字（MAPbI3、TiO2、AM1.5G）；
  - acronym：≥2 个大写字母、≤1 个小写字母、无数字、长度 ≤20（FTO、PCE、PSCs）；
  - hyphenated：含 `-` 且某个连字符后段以大写开头（spiro-OMeTAD、Li-TFSI；
    排除 UV-curable 这类后段小写的普通复合词）。

每条提及记录 surface、norm_key、source_id、paragraph_id、kind、以及所在句子
（该句子是段落原文的精确子串，作为上下文证据）。

## 3. 类型阻塞（blocking by entity type）

`guess_type()` 用固定词表把提及分入 material / metric / method / unknown：

- metric 词表（归一键）：pce、powerconversionefficiency、efficiency、voc、
  opencircuitvoltage、jsc、shortcircuitcurrent、ff、fillfactor、eqe、
  hysteresisindex、stability、retention、bandgap；
- method 词表：xrd、xraydiffraction、sem、tem、uvvis、pl、encapsulation、
  spincoating、deposition、spraypyrolysis、lamination、annealing；
- formula 形态或连字符形态 → material；其余 → unknown。

同键配对只在同一 (block, norm_key) 桶内进行；unknown 与任何块兼容。
**缩写定义派生的对绕过阻塞**（定义性链接，类型猜测错了也不影响）。

## 4. 候选对类型

| kind | 含义 | 阻塞 |
|---|---|---|
| `abbr-definition` | 同段 "Full Name (ABBR)" | 绕过 |
| `abbr-cross-paper` | A 篇定义的缩写，B 篇使用（全名@A ↔ 缩写@B） | 绕过 |
| `same-key-cross-paper` | 同归一键、不同论文 | 桶内 |
| `same-key-variant` | 同归一键、同论文、不同表面形式 | 桶内 |

去重键为无序对 {(keyA,srcA),(keyB,srcB)}；pair_id P01… 按
(kind 序, keyA, srcA, keyB, srcB) 排序后分配，完全确定。

## 5. 同键异上下文陷阱（same-key-different-context trap）

对 same-key 类候选对，取双方代表提及所在句子，在提及词位 ±5 词窗口内收集
**判别词**（固定表：compact、mesoporous、scaffold(s)、dense、porous、planar、
anatase、rutile、brookite、nanoparticle(s)、nanorod(s)、powder、single-crystal、
polycrystalline、doped、undoped、pristine、treated、passivated、electron、hole、
transport、blocking、absorber、electrode、substrate、encapsulated、
unencapsulated、aged、fresh）。**双方判别词集均非空且不相等**时置
`trap=true` 并在 `trap_reason` 列出两侧词集与段落号。

陷阱只是"必须仔细审查"的标记，**不是**自动拒绝：裁决者可以论证后仍然合并
（示例中的 spiro-OMeTAD 即假阳性陷阱被合并且记理由），也可以拒绝
（TiO2 同名异物）。未裁决的对由 adjudicate.py 保守默认为 nonmerge。

## 6. 稳定实体 ID

- 身份原子 = `(norm_key, source_id)`；合并 = 原子上的并查集（根取元组较小者，
  确定）。
- 连通分量按"最小成员键"排序，依次编号 **E0001、E0002…**。
- 规范表面形式 = 提及次数最多者，平局取较短、再取字典序小者。
- build_graph 阶段才出现的孤立表面（未参与任何候选对）按 (key, source) 排序
  后续编 E 号；声明节点 C0001…、边 R0001…、冲突 K0001… 同法排序编号。

## 7. 已知局限

- 首提缩写全名回溯是启发式：漏检只会少出候选（模型可补），错检由裁决兜底；
- 无词形还原 / 无上下位关系：chemically 相同但既无同键也无括号定义链接的
  别名（如全文只写 "methylammonium lead iodide" 对 "MAPbI3" 而无定义）不会被
  自动配对——需抽取模型在 extractions 中显式指出，或扩展固定词表；
- 希腊字母折叠只覆盖常见四字母；温度等符号折叠进条件文本而非实体键。

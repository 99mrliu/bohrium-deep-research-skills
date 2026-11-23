# 断言拆解规则（claim-atomizer 方法细则）

## 1. 原子性判据

一条断言 = 一个主体 + 一个关系实例 + 一个客体 + 必要限定，且满足**独立可判真**：
遮住同段其他句子，仅凭该断言与其证据，评审能判定真/假/证据不足。

拆分触发条件：

- **并列谓语**：「A achieves X and supports Y」→ 两条（性能断言、功能断言）。
- **因果复合句**：「A enables B, reducing C」→ 「A enables B」与「A reduces C」两条；
  因果链若在原文是单句机制解释，可保留一条 `causes/enables` 并在 qualifiers 注明中间步骤。
- **多实验组/多数据集**：「on D1 A beats B and on D2 A matches C」→ 按数据集拆，各自携带
  数据集限定。
- **枚举性参数**：「parameters k=19, w=10」按语义拆还是合，看是否独立可判真：同一行默认
  参数表可合为一条 `has_parameter`（object 为参数表），但跨章节强调的单个参数独立成条。

禁止拆分的情形：

- 必要比较基准（「faster than B」拆成「A is fast」是拆强）；
- 联合条件（「with paired-end reads under default settings」是同一条件集）；
- 集合性结论（「X is the best among Y, Z」的比较范围必须整体保留在 object/qualifiers）。

## 2. 自足句规则

- 代词与省略主语必须解析为实体：`It automatically chooses…` → `BWA-MEM automatically chooses…`；
  解析依据是原文先行词，不是猜测。
- 被动语态还原方向：「B was outperformed by A」→ subject=A, relation=outperforms, object=B。
- 断言句用陈述语序单句，可含从句，但只表达一个关系实例。

## 3. 限定词保留

以下信息出现在证据中就必须落入断言（text 或 qualifiers）：

| 限定类型 | 例 |
|-|-|
| 条件/设置 | under default parameters、with 100 bp reads |
| 样本/群体 | in human whole-genome data、for paired-end reads |
| 数据集与版本 | on HG38、using v0.7.17 |
| 数值范围 | up to 70 bp、at least 95% |
| 时间范围 | to date、as of 2013 |
| 空间/方法范围 | in vitro、within exonic regions |
| 模态 | may、suggests、proposed、approximately |

模态不得升级：`may reduce` 的断言 modality=hedged，文本保留 may；
`we propose` → modality=proposed。负向结论用肯定关系 + polarity=negative 表示，
不另造否定关系词（任务另有约定除外）。

## 4. 方向与主体常见错误

- 主客体写反：比较句默认「主体在前」未必成立，按原文施事方向定。
- 引用既往工作的句子不是本论文的新实验：主体是被引工作，关系用 `reports` 或限定
  attribution。
- 「we re-seed…」的主语是方法/系统不是作者；主体从文档语境解析时须声明依据并进入待审。

## 5. 去重与合并

仅当主体、关系、客体、全部限定、极性、模态一致时合并；合并保留全部来源与证据。
主体+关系相同、客体仅措辞差异 → 近重复，人工裁定保留一条更精确的或区分限定后都保留。

## 6. 与证据的最小充分性接口

拆解决定证据边界：每条断言的引文只需支撑该断言的谓语、数值与限定；被拆出的另一条
断言所需的句子不应塞进本条证据。证据窗口超过 6 行或 55 词时先怀疑拆得不够细，
再考虑证据确实跨句（如表格头+单元格）。

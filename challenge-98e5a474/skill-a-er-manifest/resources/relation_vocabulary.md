# 受控关系词表与图形语法（v1）

关系类型决定箭头/端头形状与方向语义。渲染脚本只接受下表类型；
来源中的表述按下表映射，**映射不上时一律用 unclear，不得按猜测归类**。

| type | 图形语法（脚本绘制） | 方向语义 from→to | 典型来源措辞 |
|-|-|-|-|
| activates | 实线 + 三角箭头指向 to | from 上调/激活 to | activates, promotes, induces, stimulates, upregulates, phosphorylates→激活, recruits→激活 |
| inhibits | 实线 + T 形平头端（⊣）指向 to | from 下调/抑制 to | inhibits, suppresses, represses, blocks, downregulates, prevents |
| binds | 实线无端头 + 中点圆点 | from 与 to 结合（无方向） | binds, interacts with, associates, forms complex |
| produces | 实线 + 三角箭头 + 空心 | from 生成/表达 to | produces, secretes, expresses, synthesizes, releases |
| degrades | 实线 + 三角箭头 + 末端 × | from 降解 to | degrades, cleaves, ubiquitinates→降解 |
| translocates | 折线 + 三角箭头指向 to | from 移位到 to（to 可为 group） | translocates, translocates into, shuttles, imports/exports |
| modifies | 实线 + 三角箭头 + 边标签 | from 修饰 to（label 写修饰位点/类型） | phosphorylates, acetylates, methylates（未说明激活/抑制时） |
| contains | **不画边**，用 group 容器嵌套 | 容器包含成员 | located in, resides in, part of, nucleus/cytoplasm/membrane 分区 |
| unclear | 虚线 + 问号边标签 | 方向或类型存疑 | 材料未明确；必须同时在 manifest.uncertainty 说明 |

## 方向判读规则

1. 主语-谓语-宾语严格按来源语序： "A phosphorylates B, leading to B
   activation" → A—modifies→B（label: 位点）且 A—activates→B。
2. 间接证据（"A knockdown reduces B"）→ A—activates→B，evidence.quote 保留
   原句，不得改写成直接结合。
3. 相关不等于因果：仅报告共表达/相关性时，用 binds（无方向）或 unclear，
   并在 uncertainty 标注"相关性证据"。
4. 时序/流程（步骤先后）→ activates 链条按时间从左到右布列（grid.col 递增）。
5. 反馈环允许成环；脚本按声明绘制，拓扑分层自动布局遇环时以 box/grid 为准。

## 图例规则

图例自动包含：实际用到的 entity class（色块 + 类别名）与实际用到的 relation
type（线样 + 类型名）。未出现的类别/类型不进图例；图例项与清单逐项一致，
由 verify_figure.py 复核。

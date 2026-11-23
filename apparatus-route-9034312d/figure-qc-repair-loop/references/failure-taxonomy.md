# 科研图示缺陷分类学（failure taxonomy）

本文件是 figure-qc-repair-loop 的核心知识制品：把"实验装置与技术路线图"挑战中列出的
经典失败模式，逐条形式化为**机器可检的缺陷代码**。每个代码 = 自动检测器
（`scripts/qc_figure.py`）+ 文档化修复动作。挑战原文失败模式 ↔ 代码映射见文末。

## 缺陷总表

| code | 现象 | 检测方法 | 常见原因 | 修复动作 | 严重度 |
|---|---|---|---|---|---|
| DANGLING_EDGE | 连线一端悬空/指向不存在的部件；凭空补齐的连接 | ①IR 级：边 from/to 不在 nodes 中；②几何级：解析 SVG，箭头端点坐标未触及任何节点盒（容差 1.5mm） | 改节点 id 忘改边；源文本没有该连接却"合理推测"补上 | 端点改为存在的节点 id；若源文本无此连接，**删除该边** | error |
| REVERSED_FLOW | 材料流向箭头反向 / 步骤先后颠倒 | 顺序语义边（kind=sequence 或两端皆有 order）检查 from.order < to.order；并比对 SVG 中箭头走向与声明顺序 | 对流程方向理解反了；编辑时交换了节点未换边 | 交换边的 from/to，或修正节点 order，使 order 沿流向递增 | error（方向矛盾为 warn） |
| NUMBERING_GAP | 步骤编号跳号/重号；编号与正文步骤错位 | 收集有序节点 order，要求恰为 1..n 连续；与源文本中枚举的步数（步骤N / 行首编号）比对 | 删了一步没重排；从正文摘步骤时漏摘 | order 重排为连续整数并与正文一一对应 | error（步数不符/无法核对为 warn） |
| LABEL_SOURCE_MISMATCH | 部件名称与材料对不上；图上词源文本里没有 | 标签分词（ASCII 词 + 中文连续段/二元组）在归一化源文本中做子串匹配，中文段二元组命中率 <70% 记缺失 | 凭印象自造术语；缩写过度 | 改用源文本原词；确为合理缩写在 uncertainties 说明 | warn |
| LEGEND_MISMATCH | 图例颜色/线型与图形实际用的不一致 | 解析 SVG：每个边 kind 的 (stroke, dash) 集合 vs 图例色块的 (stroke, dash)；缺条目/多余条目也报 | IR 显式 legend 残留旧配色；手改 SVG | 删除 legend 的 color/dash 覆盖或整个 legend 字段（改自动生成）；**不要手改 SVG** | error（多余条目为 warn） |
| TEXT_OVERFLOW | 标签文字超出部件盒子 | 估算宽（CJK≈1.0em，ASCII≈0.55em，font-size 取自 SVG）vs 节点盒宽：>盒宽 error，>90% warn | 标签过长；盒子宽度有上限（46mm） | 用源文本中的简称缩短标签；或 canvas 指定更大尺寸 | error / warn |
| FONT_RISK | 导出后中文变方框（字体未嵌入/无 CJK 字体） | 探测 `fc-list :lang=zh` 与常见字体路径（PingFang.ttc、NotoSansCJK、文泉驿）；标签含 CJK 且无字体即报 | 评测容器无中文字体 | 安装 Noto Sans CJK/文泉驿；或依赖渲染端回退链，导出后必须目检 PNG | warn |
| CANVAS_OVERFLOW | 元素被画布裁切 | 解析 SVG 全部 rect/path/line/text 的包围盒，与 viewBox 比较（容差 0.6mm） | canvas 固定尺寸给小了 | canvas 加大 width_mm/height_mm，或改回 "auto" | error |
| EXPORT_FAIL | 交付的 PNG/PDF 打不开 | 导出后检查：文件存在、非零字节、文件头魔数（%PDF / \x89PNG） | 导出工具链全部失败仍声称已导出 | 查 export_report.json 的 attempts 换工具重试；实在不行只交付 SVG 并如实声明 | error |
| UNVERIFIED_QUOTE | source.quote 与源文本对不上 | quote 归一化（去空白标点、小写）后在源文本全文中找子串 | 引文凭记忆改写而非复制 | 从抽取文本复制原文片段替换；仅记录不阻断 | warn |

## 严重度约定

- **error**：阻断交付。存在 error 时不得声明 status=ok；预算内必须修，预算耗尽转入
  partial 并列入 uncertainties。
- **warn**：不阻断，但全部原样记录在 qc_report 与 result.json uncertainties 中。
  warn 不允许"看着烦就删检查"。

## 挑战失败模式 ↔ 代码映射

| 挑战列出的失败模式 | 对应代码 |
|---|---|
| 部件名称与材料对不上 | LABEL_SOURCE_MISMATCH |
| 凭空补齐连接 | DANGLING_EDGE（+ IR 纪律：源文本无据不连） |
| 材料流向箭头反向 | REVERSED_FLOW |
| 步骤编号与正文错位 | NUMBERING_GAP |
| 图例颜色与图形不一致 | LEGEND_MISMATCH |
| 无源文件 | 流程纪律：SVG 始终由 IR 渲染，figure_ir.json + figure.svg 均交付 |
| 字体未嵌入中文变方框 | FONT_RISK（+ 导出后 PNG 目检） |
| 画布溢出 | CANVAS_OVERFLOW（+ TEXT_OVERFLOW） |

## 检测器的已知边界（诚实声明）

- 文本宽度和几何检查基于估算与 2D 包围盒，不模拟真实字体度量；
- LABEL_SOURCE_MISMATCH / UNVERIFIED_QUOTE 用归一化子串匹配，同义改写会误报 warn——
  这是刻意的轻核对，traceability 门控不是本 bundle 的职责；
- 渲染器为单层从左到右布局，不支持泳道/回路/交叉避让；复杂版式超出本技能范围。

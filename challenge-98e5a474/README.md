# 科研示意图生成与编辑（challenge-98e5a474）：三个相互独立的 Skill 方向

本目录是 Playground 挑战「科研示意图生成与编辑」的三份独立参赛作品。三者解决
同一任务族（来源材料 → 可编辑图稿 → 合规导出）中**截然不同的子问题**，互不
依赖、可单独安装使用：

| 目录 | 方向（题目五方向中的定位） | 核心思想 |
|-|-|-|
| `skill-a-er-manifest/` | 方向 1+2：科学实体与关系抽取、结构关系与层级表达 | 先把来源材料编译成带来源引句的实体-关系清单 manifest.json，再由确定性脚本渲染分层 SVG，并用校验脚本做图-清单对账与反幻觉门禁；改图=改清单重渲染 |
| `skill-b-data-legend-bind/` | 方向 4：图例与数据映射一致 | 冻结数据快照（sha256 存证）+ 视觉通道绑定声明 figure.spec.json，渲染后逐项校验图例↔数据分类、配色数↔分类数、单位、数据漂移与重绘确定性；改数据后三步命令重绘 |
| `skill-c-svg-export-gate/` | 方向 5+3：可编辑源文件与导出适配、图面规范 | SVG 分层组织约定（Inkscape 图层、稳定 id、文字可选中）+ 外科式保源编辑（只动目标 id，其余字节不动，留 diff 日志）+ 期刊导出合规门禁（尺寸/DPI/字体/文件头逐项核验） |

每个目录即一个完整 Skill 包：`SKILL.md`（用途/调用/输入输出/异常处理）、
`scripts/`（确定性脚本）、`resources/`（规范与预设）、`examples/`（标注为
示例的最小调用）。运行环境：Python 3（标准库为主；bundle B 需 matplotlib，
TIFF 需 Pillow）；导出按 cairosvg → rsvg-convert → inkscape → chromium →
ImageMagick 顺序探测，缺失时如实降级。

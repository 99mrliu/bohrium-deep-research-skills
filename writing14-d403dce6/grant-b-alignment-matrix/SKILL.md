---
name: grant-b-alignment-matrix
description: 基金申请书「目标-内容-路线-指标一致性」过程质量控制技能。Use when 需要撰写或修改基金申请书章节稿，并保证科学问题、研究目标、研究内容、技术路线步骤、考核指标编号化且逐条对齐、可被机器回检（尤其防止"目标三个、路线两条、指标另说一套"与"矩阵写在文档里但正文对不上"两类失败）。
---

# 目标-内容-路线-指标一致性矩阵：过程质量控制

本技能是基金申请书写作的**过程质量控制层**，不是写作模板库。核心纪律三条：

1. **先建矩阵再写稿**：Q（科学问题）/G（研究目标）/C（研究内容）/R（技术路线
   步骤）/K（考核指标）全部编号并登记进一致性矩阵，对齐关系落成边之后，
   才允许动笔写对应章节。
2. **稿矩阵同步改**：任何一处正文改动（增删条目、改编号、改挂接）必须在同一
   轮次同步修改矩阵，反之亦然；矩阵是编号与对齐关系的单一事实来源。
3. **机器回检不过不交付**：`matrix_check.py` 退出码非 0 的稿件一律不得交付；
   warning（厚度失衡）可以存在，但必须在交付说明中逐条解释。

## 一、运行契约（必读）

- 运行时读取 `/input/case.json` 与 `/input/task.md`；可能存在
  `/input/organizer-workorder.json` 与 `environment/resources.yaml`。
  材料的七要素清单与一致性约束以案例自身给定为准，`output_contract`
  字段名运行时读取，**不得硬编码**。
- 工作目录 `/app/work`；最终产物与可编辑稿件归 `/app/output`，其中必须有
  `result.json`，含原始 `case_id` + 全部 `output_contract` 字段 + 诚实
  `status`（success/partial/unable_to_determine/refused）+ 原因 + sources +
  uncertainty + change records。
- 材料清单一出来就先落一份诚实的 partial（含缺口清单），再就地迭代改进；
  预算 64 次模型请求 / 900 秒 / 每次响应 16384 tokens（含 reasoning）。
- 只依据实际读到的材料写作（PDF 用 pdftotext 实际抽取），绝不按文件名或
  领域标签补造内容；组织方已声明申请人证据缺失时按缺失处理，研究基础部分
  只能写材料中确有内容，缺失项列入缺口清单。

## 二、聚焦问题：「对不上」

基础 Agent 的真实失败模式：目标写三个、技术路线只覆盖两条、考核指标另说一套；
或附录画了对照表而正文从不出现表内编号，甚至正文冒出表外编号。本技能把
Q/G/C/R/K 编号与对齐关系建成可机器验证的矩阵，用 M1–M8 规则回检：

- 每个 G ≥1 个 C 支撑，每个 C ≥1 个 R 覆盖，每个 Q ≥1 个 G 回应，每个 K 挂到
  具体 G（M2）；无孤儿节点（M3）；无悬空引用（M4）。
- 矩阵每个 ID 在正文真实出现，正文同类编号全部登记进矩阵，双向一致（M5）。
- 七要素标题齐备（M6）、厚度与任务要求匹配（M7）、计数表述与矩阵一致（M8）。

## 三、工作流程（编号步骤）

1. **读输入**：读 `/input/case.json`、`/input/task.md`；若存在
   `/input/organizer-workorder.json`、`environment/resources.yaml` 一并读入。
   记录 `case_id` 与 `output_contract` 字段名。材料为 PDF 时用 pdftotext
   实际抽取文本。
2. **落 partial**：在 `/app/output/result.json` 先落诚实 partial：status=partial、
   已读材料清单、缺口清单（含【待申请人确认：…】条目）、拟用要素清单。
3. **建计划**：运行
   `python3 scripts/matrix_scaffold.py --case /input/case.json --workorder /input/organizer-workorder.json --outdir /app/work`
   （workorder 不存在时只传 --case）。得到 `plan.json`（七要素清单、编号约定、
   写作顺序）与 `consistency_matrix.template.json`（空矩阵）。案例指定的
   要素清单与 SPEC 默认清单不同时，以案例为准（scaffold 自动优先 workorder）。
4. **填矩阵**：按 plan 的写作顺序，从材料中凝练 Q→G→C→R→K，填入
   `/app/work/consistency_matrix.json`（结构见
   `references/consistency_matrix.schema.json`）。每个节点写 id 与 title；
   每条对齐关系写一条边（G→Q、C→G、R→C、K→G）。
5. **写章节稿**：按七要素顺序撰写**可直接进入申请书的章节稿**
   `/app/work/proposal_sections.md`，不是提纲或建议。正文中真实引用编号
   （写法约定见 `references/numbering_convention.md`）。事实标注遵守第四节
   红线。考核指标未单列标题时并入研究目标章节，但 K 编号与 K→G 边照旧登记。
6. **机器回检**：运行
   `python3 scripts/matrix_check.py --matrix /app/work/consistency_matrix.json --draft /app/work/proposal_sections.md --plan /app/work/plan.json --report /app/work/check_report.json`。
   - 退出码 2：输入文件问题，修复后重跑。
   - 退出码 1：按报告中 M 编号逐条修复（改稿或改矩阵，单一事实来源是矩阵），
     回到第 5 步；warning（M7 厚度）可不修，但要在交付说明中解释。
   - 退出码 0：进入第 7 步。
7. **渲染对照表**：运行
   `python3 scripts/matrix_render.py --matrix /app/work/consistency_matrix.json --out /app/work/matrix_appendix.md`，
   把要素对照说明表嵌入章节稿附录（交付物要求的「要素对照说明」）。
8. **交付**：把章节稿（含附录对照表）、`consistency_matrix.json`、
   `check_report.json` 归入 `/app/output`；更新 `result.json`：status 改为
   success 或 partial（说明界限）、sources（材料→论断映射）、uncertainty、
   change records（含每次回检的退出码记录）。

## 四、事实与来源红线（四态标注）

章节稿中的事实性内容必须可标注为以下四态之一：

- **已完成**[申请人，有材料证据]：材料中明确记载的申请人前期成果/条件。
- **外部工作**[原论文/既有成果，归外部作者]：立项依据中的背景引用，注明归
  外部作者，不写入本申请创新主张。
- **拟开展**[本研究计划]：研究内容、路线、指标中的计划性表述。
- **待确认**[材料缺失需人工确认]：以【待申请人确认：…】占位并列入缺口清单。

不新增材料外事实；引用无法核实的标注「未核验」；不使用「首次」「国际领先」
「填补空白」一类无法核验的修饰。

## 五、异常处理表

| 异常 | 处置 |
| --- | --- |
| PDF 加密/无文本层 | 先 pdftotext 探测；失败则渲染+OCR（环境具备时），否则声明该文件不可读并在 result.json 落 partial，缺口清单注明 |
| 材料缺失（如申请人研究基础证据） | 【待申请人确认：…】占位 + 缺口清单；研究基础章节只写材料确有内容 |
| 材料冲突（同一事实两种说法） | 两说并录、标注冲突来源，不擅自取舍；列入 uncertainty |
| 超长输入 | 先抽取与 Q/G/C/R/K 相关的段落建矩阵，再按预算分段处理；partial 说明覆盖界限 |
| 格式冲突（workorder 与 task.md 要求不一致） | 以 case 自身的 output_contract 与 workorder 为准，冲突记入 uncertainty |
| 七要素清单与默认不同 | 以案例为准；matrix_scaffold.py 会自动优先 workorder/case 中的清单 |
| 矩阵 JSON 无法解析 | M1 判 error，按 schema 修复后重跑 |
| 检查报 M7 warning | 对照 references/element_guide.md 经验值判断，必要时加厚或说明原因 |

## 六、脚本与资源清单

| 文件 | 用途 | 调用方式 |
| --- | --- | --- |
| scripts/matrix_scaffold.py | 从 case/workorder 提取七要素清单与一致性约束，生成 plan.json 与空矩阵模板 | `python3 scripts/matrix_scaffold.py --case case.json [--workorder wo.json] --outdir DIR`；exit 0 成功，2 输入错误 |
| scripts/matrix_check.py | M1–M8 机器回检 | `python3 scripts/matrix_check.py --matrix M.json --draft D.md [--plan P.json] [--report R.json] [--threshold 0.35]`；exit 0 通过（可 warning），1 有 error，2 输入错误 |
| scripts/matrix_render.py | 渲染要素对照说明表（Q\|G\|C\|R\|K + 覆盖统计） | `python3 scripts/matrix_render.py --matrix M.json [--out A.md]`；exit 0 成功，1 矩阵非法，2 输入错误 |
| references/numbering_convention.md | Q/G/C/R/K 编号与正文写法约定（含别名表与识别正则） | 写作与改稿时查阅 |
| references/matrix_rules.md | M1–M8 规则全文与判定示例 | 修复检查报告时查阅 |
| references/consistency_matrix.schema.json | 矩阵 JSON schema | 手工/程序校验矩阵结构 |
| references/element_guide.md | 七要素厚度配比经验值与常见错位案例 | M7 warning 判断、评审视角自查 |

三个脚本均为 Python3 标准库实现，确定性输出（同输入二次运行字节一致），
支持 `--help`，失败退出码非零。

## 七、最小示例（合成示例，非正式案例结果）

`examples/` 内置合成示例：workorder.json（要求七要素+一致性）、
proposal_sections.md（含四类陷阱缺陷的章节稿）、consistency_matrix.json
（与缺陷稿一致的矩阵）。缺陷版回检退出码 1，恰好抓到 M2（研究内容缺路线
步骤）、M4（指标挂到不存在的目标）、M5（正文出现未登记编号）、M6（缺创新点
标题）各一条；修复版退出码 0。完整命令与真实输出见 `examples/README.md`。

## 八、版本与维护

- 版本：1.0（2026-11）。
- 依赖：Python 3（仅标准库）；pdftotext 为可选外部工具，缺失时按异常表降级。
- 适用范围：需要交付「可直接进入申请书的章节稿＋要素对照说明」的基金申请书
  写作/改稿任务；七要素清单可由案例覆盖。
- 限制：只做编号级与结构级一致性校验，不判断科学价值；M8 只识别显式计数句；
  别名表覆盖常见标题写法，生僻标题需先改稿或扩展别名表。

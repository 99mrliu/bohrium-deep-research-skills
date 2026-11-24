---
name: renum-sync-engine
description: >-
  确定性参考文献编号更新与交叉引用同步引擎。适用：顺序编码制（GB/T 7714—2015 式 [n] 上标/方括号）
  或著者-出版年制（APA 7 式）稿件在插入、删除、调序、合并章节/条目后的正文标记与文末列表
  重编号同步；编号连续性、区间折叠、样式统一、图表注/脚注/附录覆盖、悬空标记与未引用条目
  的审计与修复；重算幂等性自证。不适用：LaTeX \cite/\ref/\eqref 体系（属 citekey 适配流程，
  不做硬编码编号）、BibTeX/CSL 数据库编译、正文语义改写、文献内容真伪核验、从 PDF 提取
  书目元数据。
---

# renum-sync-engine — 编号更新与交叉引用结构工程

## 核心主张

编号一致性不该靠人眼核对。本 skill 把「稿件 + 文末文献表」建成一张以**稳定 ID** 为节点的
引用图：每个文献条目先拿到与位置无关的 sid（sid-001…），正文里的每个标记只是对 sid 的
引用。所有修改（插入/删除/调序/合并）都是**事务性编辑操作**（ops.json），编号永远由
「全局真实阅读序的首现顺序」**重算**得出，正文标记、文末列表、图表注、脚注、附录在
同一次施加中同步更新。全程保留 `original-label → stable-id → new-label` 三层映射：
**旧编号 12 不等于数组第 12 条**，任何旧标签绝不按位置猜测。apply 先复算校验、全部通过
才原子落盘；verify 用 V1–V8 八条规则做双向核验，其中 V8 用空操作集重跑一遍证明零变化
（幂等自证）。

## 运行时契约（必须先读）

1. **逐文件读真实内容**：/input 下的 case.json、task.md、稿件、文献库、可能的
   PDF/DOCX/LaTeX，全部实际打开阅读，不得凭文件名臆测内容。
2. **resources.yaml 先读**：若 /input 或 skill 内存在 resources.yaml，先读它再动工。
3. **目录分工**：中间产物（occurrences.jsonl、labels.json、label_map.json、ops.json、
   核验草稿）写入 /app/work；最终交付（改后稿、同步文献表、result.json）写入 /app/output。
4. **result.json 契约**：必须包含**逐字** case_id 与 output_contract 的**全部原始字段**
   （原样复制，不改名、不缺省、不重排语义）。第一阶段先写骨架——契约字段填 null、
   `status: "in_progress"`——之后逐阶段回填，**骨架与回填都不可省**。
5. **预算**：64 请求 / 900 秒 / 16384 token。规划调用次数，重活交给本地脚本（确定性、
   不占请求），模型只做判断（编 ops、看报告）。
6. **诚实状态**：status ∈ {success, partial, failed}，如实填写；部分完成就 partial 并
   写明缺口，失败就 failed 并写明原因。
7. **禁止伪造**：不臆造缺失的文献条目、不编造编号映射、不把 LaTeX 的 \ref/\eqref/\cite
   当成本引擎处理的文献引用标记（见异常处理表第 1 行）。

## 工作流程（五阶段）

总览：阶段 0 定契约 → 阶段 1 建图 → 阶段 2 定操作并重算 → 阶段 3 校验后落盘 →
阶段 4 核验并回填。判断类工作（读任务、编 ops、看报告）由模型做；计算类工作
（扫描、重算、渲染、核验）全部交给脚本，确定性、可复跑、不占请求预算。

### 阶段 0 — 盘点与契约骨架

- 读 /input 全部文件；识别稿件格式（纯文本/Markdown/LaTeX/著者-年/顺序编码）。
- 写 /app/output/result.json 骨架：case_id 逐字复制、output_contract 全部原始字段置
  null、status=in_progress。
- 在 /app/work 记录任务要点：要求的样式（numeric-bracket / numeric-superscript /
  author-year）、编号起始值、未引用条目是删还是保留标注、哪些章节要动。

result.json 骨架的形状（仅示意键位；case_id 与 output_contract 的字段以 case.json
原文为准，逐字复制，一个都不能少）：

```json
{
  "case_id": "<逐字复制 case.json 的 case_id>",
  "status": "in_progress",
  "output_contract": { "<字段1>": null, "<字段2>": null, "...": "……全部原始字段" },
  "artifacts": null,
  "label_map_summary": null,
  "verification": null,
  "notes": []
}
```

- 若稿件是 DOCX/PDF：先用可用工具抽取纯文本到 /app/work/manuscript.txt，把抽取动作
  记入 notes；文末列表同样抽取为「每行一条」的 references.txt。
- 若稿件是 LaTeX：走异常表第 1 行，不在本引擎内硬编。

### 阶段 1 — 扫描建图

```
python3 /skills/weekly-skill/scripts/cite_scan.py \
  --manuscript /app/work/manuscript.txt \
  --references /app/work/references.txt \
  --out /app/work
```

（评测环境路径为 /skills/weekly-skill/scripts/…；本地复现用相对路径 scripts/…，下同。）

产物：
- **occurrences.jsonl**：正文/图注/表注/脚注/附录按真实阅读序的全部标记，每行含
  reading_order、区域、行列、原标签、展开后的条目引用集（[1-3] 展开成 1,2,3）。
- **labels.json**：原标签 → 稳定 id（按全局首现顺序赋 sid-001…，未被引条目按列表顺序
  续赋）、文末列表条目、**悬空标记清单**、**未引用条目清单**、区域计数。

人工/模型审读这两份产物，确定编辑意图。审读要点：

- dangling 清单里的每个标签：对照 task.md 决定是 delete_marker 删除，还是列表确实
  缺条目（缺条目→异常表第 5 行，只交审计不臆造）。
- uncited 清单：对照 task.md 决定删除还是保留；保留则由引擎自动加
  【未引用·保留】 标注并以 [*] 列于末尾。
- region_counts：确认图注/表注/脚注/附录里的标记都被看到（为 V7 打底）。

### 阶段 2 — 编辑操作与重算

按 task.md 要求的插入/删除/调序/合并，编 **ops.json**（坐标一律指向原始稿件：
delete_marker 用 reading_order，insert_marker 用 line+col 或 line+after_text，
merge_paragraphs 用 0 基段落索引，move_section 用标题正则，merge_entries 用原标签）。
然后：

```
python3 /skills/weekly-skill/scripts/renumber.py plan \
  --manuscript /app/work/manuscript.txt \
  --references /app/work/references.txt \
  --ops /app/work/ops.json \
  --occurrences /app/work/occurrences.jsonl \
  --style numeric-bracket \
  --out /app/work
```

plan 的重算规则：
- **顺序编码制**：按编辑后全局阅读序（图注/表注/脚注/附录纳入同一序列）首现赋 1..N；
  重复出现共享编号；多编号标记排序后区间折叠（连续 ≥3 → [1-3]，长度 2 → [1,2]）；
  未引用条目按任务要求以 `[*] …【未引用·保留】` 列于末尾。
- **著者-出版年制**：文末列表按 (作者, 年, 题名) 重排；同作者同年按题名排序赋 a/b
  后缀并回改正文标记；未引用条目追加保留标注。
- plan 内部重扫稿件保证坐标新鲜；提供的 occurrences 仅作一致性校验，不一致即报错
  （提示先重跑 cite_scan）。
- 仍有悬空标记未显式 delete_marker → plan 报错退出，**绝不替它编个号**。

ops.json 的坐标纪律（重要）：

- 所有坐标指向**原始稿件**：delete_marker 用阶段 1 扫描得到的 reading_order；
  insert_marker 用 1 基 line + 0 基 col，或用 after_text（该行首个匹配子串之后）；
  merge_paragraphs 用 0 基段落索引（段落=空行分隔的非空行块，occurrences.jsonl 的
  para 字段可直接查到）；move_section 用标题正则；merge_entries 用原始标签。
- plan 分两相施加：先标记级（删/插，行内从右到左，坐标不漂移），后结构级
  （并段、移节），然后对编辑后文本**整篇重扫**得到最终阅读序——所以结构改动
  不会让任何坐标失效。
- 每个 op 建议附 reason 字段，便于审计与回填 result.json。

### 阶段 3 — 施加与同步

```
python3 /skills/weekly-skill/scripts/renumber.py apply \
  --manuscript /app/work/manuscript.txt \
  --references /app/work/references.txt \
  --label_map /app/work/label_map.json \
  --style numeric-bracket \
  --out /app/output   # 或 /app/work 再复制，按契约
```

- apply 用相同输入 + label_map 中的 ops **完整复算一遍**，逐字段比对 label_map；
  一致才原子写出 edited_manuscript.txt、edited_references.txt、label_map.json；
  任何不一致（过期/篡改/样式不符/占位符残留）→ **不写任何文件**，退出码 1。
- 纪律：**先映射后渲染**；旧标签绝不按位置猜；三层映射全程留痕于 label_map.json。

label_map.json 的三层映射（示例取自 examples/output）：

```
原标签 3  → sid-001 → 新标签 1   （引言首现）
原标签 1  → sid-002 → 新标签 2
原标签 8  → sid-008 → null       （uncited_retained，[*] 保留）
```

### 阶段 4 — 双向一致性核验与收口

```
python3 /skills/weekly-skill/scripts/sync_verify.py \
  --manuscript /app/output/edited_manuscript.txt \
  --references /app/output/edited_references.txt \
  --label_map /app/output/label_map.json \
  --out /app/output
```

- V1–V8 必须全过（退出码 0）；任何违规退出码 1 并给出 sync_report.json/md 明细。
- 回填 result.json：status、产物路径、label_map 摘要、核验结论；连同改后稿与同步
  文献表一起交付 /app/output。

回填要点：

- status：V1–V8 全过且契约字段齐 → success；核验未过但已交付审计产物、或任务只有
  部分可执行（如文末列表缺失）→ partial 并写明缺口；输入不可读/契约无法满足 →
  failed 并写明原因。
- verification 字段：照抄 sync_report.json 的 all_pass 与 failed_rules。
- label_map_summary：原标签→新标签对照、uncited_retained、dangling_removed、notes，
  便于评测方与人审复核「哪条变成了哪条」。
- 交付清单（/app/output）：改后稿、同步文献表、result.json；label_map.json 与
  sync_report.* 作为佐证一并放入（若 output_contract 另有命名要求，以契约为准）。

## 核验规则 V1–V8（简述）

| 规则 | 内容 |
| --- | --- |
| V1 | 无悬空：每个正文标记都能解析到文献列表条目 |
| V2 | 无多余：每个列表条目至少被引一次，或带 【未引用·保留】 标注按任务要求保留 |
| V3 | 编号自 1 连续无跳号（列表侧 + 正文实际使用侧双侧检查） |
| V4 | 区间合法：[a-b] 满足 a≤b 且端点都存在于列表 |
| V5 | 样式统一：全稿 [n] 与 ^[n]^ 上标形态不混用、不与著者-年混用（除非任务指定分区）、无占位符残留 |
| V6 | 著者-年 a/b 后缀在正文与列表一致（纯数字稿自动跳过） |
| V7 | 图注/表注/脚注/附录中的标记全部纳入编号序列 |
| V8 | 重算幂等：对已同步稿件以空 ops 再跑一次重编号，映射恒等且文本零变化 |

### 阅读序与首现赋号（V3/V8 的判定基准）

- **真实阅读序**：文本行自上而下；行内按列从左到右；章节移动、段落合并之后以**编辑后**
  的文本为准（plan 对编辑后文本整篇重扫）。图注、表注、脚注、附录与正文在**同一序列**
  中，不单独编号。
- **首现赋号**：扫描序列中，某条目第一次被引用时获得下一个可用编号；其后的重复出现
  共享该编号。多编号标记（[7,3]）按标记内列出的顺序逐个结算首现。
- **区间折叠**：一个标记引用多个编号时，编号排序去重后渲染；连续长度 ≥3 折叠为
  [a-b]，长度为 2 不折叠（[1,2]），非连续用逗号（[1,3]）。
- **V8 幂等**：对交付文本以空 ops 再跑一次完整重算。若映射为恒等（每个标签映射到
  自身）且重渲染文本与输入逐字节一致，则编号体系处于不动点——这就是「编号已同步」的
  可操作定义；任何人手改编号都会破坏首现序而被 V8 捕获（见 examples 的 trap_a）。

## 异常处理表

| 异常 | 处置 |
| --- | --- |
| 稿件含 LaTeX \cite / \ref / \eqref | 登记为 citekey 体系，交相应适配流程；本引擎不对其硬编码编号，也不把 \ref/\eqref 当文献引用 |
| 标记样式混杂（[n] 与 ^[n]^ 或著者-年并存） | V5 报警；按 task.md 指定样式用 --style 统一重渲染，并在 result.json 记录统一动作 |
| 合并章节导致重复首现、定义冲突 | 以编辑后**真实阅读序**为准重算首现；在 label_map.notes 输出判定依据 |
| 著者-年制中同年同姓氏不同人 | 展开更多名字（initials/全名）区分排序键；无法区分时按题名排序赋后缀并记录 |
| 文末列表缺失或不可解析 | 不臆造条目；只交付标记审计（occurrences/labels），result.json 标 partial 并写明缺口 |
| 任务指定编号起始值非 1（如从 5 开始） | 按任务参数偏移赋号，V3 相应改为「自起始值连续」；在 result.json 记录起始值 |
| 提供的 occurrences 与稿件不符 | plan 拒绝并提示重跑 cite_scan（防止用过期坐标动刀） |
| 仍存在的悬空标记 | plan 报错列出清单，要求显式 delete_marker；绝不自动补条目 |

## 最小调用示例（合成示例）

见 `examples/minimal_example.md`：全虚构稿件（乱序 [3][1][7]、悬空 [9]、图注/表注/脚注/
附录各带标记）+ 8 条虚构文献 + ops.json（删悬空、并两段、插入 1 个新标记），跑通
扫描→plan→apply→verify 全流程；另含两个 booby-trap 演示（手改产物后 verify 退出码 1）。
examples/output/ 为真实运行产物。

最小命令序列（本地复现用相对路径；评测环境把 scripts 换成
/skills/weekly-skill/scripts）：

```bash
python3 scripts/cite_scan.py  --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --out work/
python3 scripts/renumber.py plan  --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --ops examples/input/ops.json \
  --occurrences work/occurrences.jsonl --style numeric-bracket --out work/
python3 scripts/renumber.py apply --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --label_map work/label_map.json \
  --style numeric-bracket --out out/
python3 scripts/sync_verify.py --manuscript out/edited_manuscript.txt \
  --references out/edited_references.txt --label_map out/label_map.json --out out/
```

## 预算分配建议（64 请求 / 900 秒 / 16384 token）

- 脚本调用（scan/plan/apply/verify）是本地进程，确定性输出，应占绝对大头；
  模型请求只花在：读 case/task、审读 labels.json 与 dangling/uncited 清单、编
  ops.json、读 sync_report 并决定收尾。
- 一次失败不要盲改：plan/apply/verify 的报错都带行列号与期望值，按报错定点修。
- result.json 骨架在阶段 0 就落盘，任何中途失败都保留现场（work 目录 + 骨架），
  回填 failed/partial 即可，不丢证据。

## 限制与适用范围

- 输入为**纯文本/Markdown** 稿件与「每行一条」的文末列表；DOCX/PDF/LaTeX 需先抽取为
  文本（抽取不在本引擎内）。
- 数字标记形态：`[n]`、`[n-m]`、`[n,m]`、`^[n]^` 上标约定；著者-年：`(Smith, 2020)`、
  `（张三，2021）`。其他形态（脚注编号引用文献、数字-字母混合标签）不识别。
- 图注/表注按「行首 图/表/Figure/Table + 数字」识别，跨行注的第二行起按正文处理；
  脚注识别 `[^x]:` 定义行与「注：」起首段。
- 著者-年制只处理单条著者-年标记；多文献并列标记 `(A, 2020; B, 2021)` 不拆分。
- 编号起始值、保留/删除未引用条目、分区样式等以 task.md 参数为准；默认值见
  references/renumber_model.md。
- 脚本确定性、无网络、仅标准库；退出码：0 成功，1 校验/核验违规，2 输入或操作错误。

## 文件索引

- `scripts/cite_scan.py` — 阶段 1 扫描建图
- `scripts/renumber.py` — 阶段 2/3 重算（plan）与原子施加（apply）
- `scripts/sync_verify.py` — 阶段 4 核验 V1–V8
- `references/renumber_model.md` — 引用图模型与规则细则
- `references/file_formats.md` — 各 JSON/JSONL 字段级格式
- `examples/` — 全虚构合成示例与真实运行产物

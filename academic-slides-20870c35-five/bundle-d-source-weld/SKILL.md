---
name: source-weld-verifier
description: 学术汇报内容组织中的上游材料真实性门控——把页面上每一句话"焊"回源材料：每条页级主张必须带逐字锚点与精确定位（file/pdf_page/printed_page/section/exhibit），每个数字连同单位与条件逐字转录且必须在源数字注册表中出现，结论措辞强度必须与证据分级匹配，回链率可计算可复核；触发词：学术汇报、幻灯片证据映射、逐字引用核验、数字防漂移、图表引用绑定、claim anchoring、verbatim audit、slide evidence map。
---

# source-weld-verifier：上游材料真实性门控（逐字锚定与数字防漂移）

## 1. 用途与边界

本 Skill 面向"学术汇报内容组织"任务，针对三类最高发、最难自察的失信失败：
（a）数字凭记忆抄错——页面上写 98.6%，原文根本没有这个数；
（b）引文对错页、对错 caption——页面结论与所引图表对不上；
（c）结论强于证据——初步数据被讲成"证明了"。

做法：先由 `scripts/source_index.py` 把真实材料（PDF/文本）焊成带页级
span、题注重册表、节标题注册表、数字注册表的 `source_index.json`；
之后每一句拟上页的话都登记为 claim card，由 `scripts/anchor_audit.py`
做三道确定性检查（逐字锚定五态、slide_text 数字扫描、强度措辞门），
输出逐条状态与回链率，退出码硬门控：`0` 全部焊住，`1` 存在违例
（stdout 逐项精确违例码），`2` 用法/IO/schema 错误。两个脚本仅依赖
Python3 标准库（pdftotext 子进程除外），可离线运行。

本 Skill 不负责叙事设计美学、模板视觉与问答预演；它保证的是
**源材料 → 页面主张**这条上游链条的零漂移。格式细节见
`references/anchor-schema.md`，强度分级与过强词表见
`references/strength-lexicon.md`。

## 2. 环境与前置条件

- python3（≥3.10，仅标准库）；宿主 PATH 中有 `pdftotext` 与 `pdftoppm`；
  python-pptx / soffice 可能存在但**不得假设**，缺失时优雅降级并如实记录。
- 平台输入在 `/input`：`case.json`、`task.md`、真实材料（真实 PDF/PPTX，
  无预提取答案层——必须读真实文件内容，禁止从文件名或目录标签推断内容），
  可能还有模板 PPTX、起始 deck、slide-workorder。
- 工作目录 `/app/work`；最终产物与可编辑件放 `/app/output`，
  必须含 `result.json`。预算：64 次模型请求 / 900 秒 / 每响应 16384 token。
- 以下设 `SKILL_DIR=/skills/weekly-skill`（平台安装路径）。

## 3. 六阶段案例执行协议（焊接重心版）

### Phase 0 — 契约 intake（先落盘，防超时归零）

1. 递归列出 `/input`，逐一打开真实文件：`case.json`、`task.md`、
   材料、模板、起始 deck。**读内容，不读文件名**。
2. 防御式解析 `case.json`，**动态**取得真实 `case_id` 与
   `output_contract` 的全部根字段名（禁止在脚本或产物里硬编码字段名）：

```bash
python3 - <<'EOF'
import json
try:
    case = json.load(open('/input/case.json', encoding='utf-8'))
except (OSError, json.JSONDecodeError) as e:
    case = {}; print('[WARN] case.json 读取失败:', e)
cid = case.get('case_id') or case.get('id') or 'unknown'
oc = case.get('output_contract') or {}
fields = list(oc.keys()) if isinstance(oc, dict) else list(oc or [])
print('case_id =', cid); print('contract fields =', fields)
EOF
```

3. 写 `/app/work/contract.json`：真实 case_id、output_contract 根字段、
   mode、页数、听众、时长、语言、模板与起始 deck 路径、导出格式。
4. **立刻**写 `/app/output/result.json` 骨架：`case_id` 填真值，全部契约
   字段先占位，`status: "partial"`，`uncertainty` 注明"构建中"。
   此后每完成一阶段就地增量更新——宁可交诚实的 partial，不交伪造的
   completed。
5. 工具普查：`which pdftotext pdftoppm soffice python3`、
   `python3 -c "import pptx"` 试 python-pptx、字体枚举；结果记入
   contract.json。预算纪律：批处理 shell 一次做多件事、早存盘、
   全量渲染至多两轮。

### Phase 1 — 源材料索引与主线提取（本 Skill 的重心）

1. 把全部材料焊成源索引：

```bash
python3 $SKILL_DIR/scripts/source_index.py --materials /input --out /app/work/source_index.json
```

   - exit 0：索引就绪。逐文档核对 `parse_method` 是否如实记录
     （`pdftotext-layout` / `pdftotext-plain` / `direct-read`），
     页数、题注数、数字数是否符合直觉。
   - exit 1：存在 unparseable 文档——该文档相关结论全部降级，
     在 uncertainty 中注明；不得以文件名臆测其内容。
   - exit 2：目录含 PDF 但无 pdftotext——如实记录工具缺失，
     文本材料仍可单独索引后重试（把 PDF 暂时移出扫描目录并记录原因）。
2. **关键图页必须渲染目检**：用 `pdftoppm -png -r 110 -f <p> -l <p>`
   把含核心 Figure/Table 的页渲成 PNG 并真正看图，确认题注与图形内容、
   数值轴/表值是否一致（题注注册表只保证文字，不保证图形内容）。
3. 提取主线：central_question / approach / results / limitations。
   每条 result 当场标注 `strength`（established / preliminary /
   contextual，语义见 references/strength-lexicon.md）与完整 locator
   （file / pdf_page / printed_page / section / exhibit）。
4. **数字转录纪律**：所有数字连同单位与条件从 `source_index.json` 的
   数字注册表与页文本中逐字抄出（"retained 91 percent after 1000 hours
   at 85 degrees Celsius"），禁止凭记忆补单位、四舍五入或跨条件拼接。

### Phase 2 — 听众与页级 storyboard

1. 从 task.md 确认听众决策目标、先验知识与预期质疑；
   据此决定背景比例与证据展示深度。
2. 每页恰好一个 message，指定叙事角色（hook/problem/approach/result/
   limitation/conclusion…）、时间片、转场句。
3. 每个承载事实的 message 绑定 ≥1 张 claim card 草稿
   （slide_text + strength + locator + anchor）；图表页绑定
   `exhibit`，并用题注注册表核对"引的图确实是那个 caption"。

### Phase 3 — 建 deck（真实模板内构建）

1. python-pptx 可用：`Presentation(template_path)` 在真实模板内增改；
   不可用：用 bundle 外临时 stdlib OOXML 兜底（zipfile+XML），
   并在 uncertainty 记录降级。
2. 每页写入：唯一 message、绑定图表、讲稿备注（speaker notes，
   与页面结论口径一致）、页角证据定位（file:pdf_page:exhibit）。
3. **页面上每个事实句 → claim card 落盘** `/app/work/claims.json`
   （schema 见 references/anchor-schema.md）。版本快照存入 /app/work。

### Phase 4 — 焊接审计门（交付前的硬门控）

```bash
python3 $SKILL_DIR/scripts/anchor_audit.py --claims /app/work/claims.json --index /app/work/source_index.json --outdir /app/work
```

逐条状态语义与修复动作：

| 状态 | 含义 | 修复 |
|-|-|-|
| `verified` | 声明页内逐字命中，数字与措辞合规 | — |
| `page_mismatch` | 引文在其它页（报告给出真实页） | 改 `pdf_page` 为 `found_page` |
| `not_verbatim` | 归一化后全文档未命中 | 回原文重新逐字摘录，或删该 claim |
| `doc_missing` | locator.file 不在索引 | 核对 doc_id / 补建索引 |
| `quote_empty` | anchor 为空 | 无引文的句子不许上页 |
| `number_not_in_source` | slide_text 数字不在源数字注册表 | 回源核对数字/单位/条件，删改漂移数 |
| `strength_overclaim` | preliminary/contextual 用了过强词 | 换弱措辞，或升档 strength 并补强证据 |

- exit 0：回链率 1.0，允许进入渲染 QA。
- exit 1：按清单逐条修复后重跑，直至 exit 0；预算不足时**只保留
  verified 子集上页**，未焊住条目移入 uncertainty 并将 status 保持
  partial——宁可少讲，不可错讲。
- 锚定归一化 = NFKC + casefold + 空白压缩 + 换行/连字符断词修复，
  所以跨行、跨 PDF 断词（"contin-\nuous"）的逐字引文都能焊住；
  但同义改写、凭记忆重述焊不住——这正是设计意图。

### Phase 5 — 渲染 QA 与交付

1. 渲染 QA：soffice 可用则导出 PDF + `pdftoppm` PNG 预览逐页目检
   （页数/空白页/溢出/字体）；soffice 缺失则如实记录降级，
   **绝不伪造渲染产物**。修复回路至多两轮。
2. 交付 `/app/output/`：可编辑 deck、导出预览、`claims.json`、
   `source_index.json`、`audit_report.json`（页级证据映射的可复核附件）、
   以及完整 `result.json`：
   - `case_id` 与 case.json 原样一致；`output_contract` 全部根字段齐备；
   - `status` ∈ completed / partial / blocked，partial 必须逐字段写明限制；
   - `sources` 列出全部材料 doc_id + sha256；`uncertainty` 记录降级与
     未覆盖项；`change_log` 记录每处修改（file/what/why/rollback）；
   - 回链率写进 evidence 映射字段：交付时必须是 1.0（或如实说明为何不是）。

## 4. 脚本接口速查

| 脚本 | 功能 | 关键参数（默认值） | 退出码 |
|-|-|-|-|
| `scripts/source_index.py` | 材料 → source_index.json（页 span + 题注/节标题/数字注册表） | `--materials /input` `--out /app/work/source_index.json` | 0 成功；1 无可解析文档；2 IO/工具缺失（含 PDF 在场而 pdftotext 缺失） |
| `scripts/anchor_audit.py` | claims.json 三道焊接检查 + 回链率 | `--claims /app/work/claims.json` `--index /app/work/source_index.json` `--lexicon`（默认 bundle 内词表） `--outdir` | 0 全部 verified；1 任一非 verified；2 IO/schema |

两脚本 `--help` 可查；产物均为 UTF-8 JSON（`ensure_ascii=False, indent=2`）。

## 5. 异常处理与预算策略

- pdftotext 两级重试（`-layout` → plain）；扫描版无文本层 PDF 标
  unparseable（exit 1），相关结论降级并记 uncertainty；本 Skill 不内置
  OCR，必要时借助宿主 OCR 先转文本。
- 缺 pdftoppm/soffice/python-pptx：Phase 1 目检、Phase 5 渲染分别降级，
  一律在 result.json 的 uncertainty 与 change_log 中如实记录。
- 预算紧张（64 请求/900 秒）：先保"全部上页句子 verified"这条底线，
  再扩页数与修饰；每阶段结束就地更新 result.json 骨架。
- 一键自洽演示（合成示例，含门控开火变例）：
  `bash examples/run_example.sh`，日志产物在 `examples/output_demo/`。
  示例中的 `synthetic_note_gamma.pdf` 由 `examples/make_gamma_pdf.py`
  （matplotlib，仅示例夹具允许使用）在演示开始现场生成、演示结束自动
  删除——bundle 本体为纯 UTF-8 文本，不含二进制；该 PDF 用于实测真实
  PDF 的 pdftotext 索引路径（含跨行/断词锚点），其索引与审计产物保留
  在 `output_demo/` 供目检。

## 6. 限制

- 逐字锚定是子串级证据回链：它证明"这句话在源材料里存在"，
  不判断引文是否足以支撑结论的语义充分性（仍需人/模型判断）。
- 数字扫描按数值等值匹配（"91" 与 "91.0" 视为同值）；它抓不住
  "数字对但单位错"这类漂移，单位与条件靠转录纪律与目检把关。
- 强度措辞门是词表级启发式，只拦明说过强词；语义层面的隐性夸大
  不在门控范围。
- txt/md 材料按 `\f` 换页符切页（与 pdftotext 同约定）；无换页符的
  纯文本即单页文档，`page_mismatch` 检查对其退化为页 1。

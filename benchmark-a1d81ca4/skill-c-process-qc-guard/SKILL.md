---
name: process-qc-guard
description: 过程质量控制守卫：为文献阅读问答与 benchmark-DRAFT 出题工单提供预检、预算安全网、原子检查点、复跑一致性审计与 12 类失败探针，确保任何时刻中断都有诚实 partial 可提交、每个字段可追溯到输入哈希与检查点、机器产物复跑逐字节一致。Use when running reading-QA/extraction/translation or benchmark-DRAFT authoring tasks under strict budgets (64 requests / 900s), when reruns must be byte-identical and auditable, when a crash-safe honest partial result.json must exist from minute one, or when failures must be probed, classified and fixed before delivery.
---

# process-qc-guard：过程质量控制守卫

## 用途与适用条件

本技能**不直接作答**，而是包住整个干活过程：预检（init_run）→ 检查点（checkpoint）→ 失败探针（probe_failures）→ 复跑一致性（rerun_consistency）→ 导出（export）。核心理念"跑得一致、查得回"：任何时刻中断都有可提交的诚实 partial；每个分数/字段能追到输入哈希、运行配置与检查点；机器产物复跑必须逐字节一致，漂移必须被检出并解释。适用于有严格预算与复跑要求的文献阅读评测场景。与其他 bundle 错位：本 bundle 只管过程质量，具体作答由 agent 完成并写入约定工作文件（T1 写 `answers.json`，T2 写 `items.json`）。

## 运行时契约

1. 平台把本技能装在 `/skills/weekly-skill`；官方 DeepSeek Harness 在 3 个隐藏固定案例上各跑 3 次（同案例重复运行，复跑稳定性正是考察点）。
2. 每个案例输入：`/input/case.json`（含 `case_id` 与 `output_contract` 字段集——运行时动态读取，禁止硬编码）、`/input/task.md`、`/input` 下源材料（真实 PDF 或段落/表格文本；revision2 案例为段落/表格文本）。
3. 工作目录 `/app/work`；最终交付 `/app/output/result.json`，含：`case_id` + `output_contract` 全部字段（填不了置 null 并写 uncertainty，**不得编造**）+ 诚实 `status`（成功/部分完成/无法判断/拒答 + `status_reason`）+ `sources` + `uncertainty` + `change_records`。partial 必须指明局限。
4. 预算：64 次模型请求、900 秒、每响应 16384 tokens。**必须先尽早写合法部分 result.json 再增量完善**（init_run 已完成此安全网）。
5. 技能包约束：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无符号链接；不得包含隐藏案例预制答案。
6. 脚本仅用 Python 标准库（3.8+）；`pdftotext`/`pdfinfo` 可选，缺失时优雅降级（改用纯文本材料或人工摘录），不阻塞流程。

## 依赖

- `python3`（≥3.8，仅标准库）；`bash`（示例脚本）。
- 可选：`pdftotext`、`pdfinfo`（init_run 自动探测并在 manifest 记录）。

## 两类工单识别

- **T1 阅读问答/解析/翻译/抽取**：默认类型。逐问作答写入 `/app/work/answers.json`，条目含 `id/question/answer/evidence/confidence/uncertainty`；材料未给出的信息标"未报告"。
- **T2 benchmark-DRAFT 出题**：`task.md` 含"出题/题卡/benchmark/DRAFT/草拟/4 道/四道"任一关键词即判 T2。从段落/表格文本起草 4 道题卡写入 `/app/work/items.json`，每题含任务、材料范围、参考答案、评分规则、证据锚点、难度、授权七要素。
- 两类的过程质量控制动作（预检/检查点/探针/一致性/导出）完全一致。

## 工作流程

- **步骤 0（init_run，立即锁 partial）**：`python3 scripts/init_run.py`。清点输入（sha256+字节数）、探测工具、解析 case.json、写 `run_manifest.json`（含预算台账），并立即写 `result.json` 合法骨架（status=部分完成，skeleton=true）。幂等：重复运行不覆盖已有工作文件与正式结果。
- **步骤 1（起草）**：按 `references/runbook.md` 预算分配（预检 ≤1 分钟、起草 ≤60%、核验 ≥20%、门禁 ≥10%）读材料并作答，写入 `answers.json`（T1）或 `items.json`（T2）。
- **步骤 2（每阶段 checkpoint save）**：`checkpoint.py save --stage <名> --dep <输入> --out <产物> [--cmd <复跑命令>]`。原子写；记录依赖与产物 sha256。
- **步骤 3（probe_failures 并修复）**：`probe_failures.py` 跑 12 类探针（见 `references/failure_taxonomy.md`），逐条修复后重跑，直至高危（P01/P03/P07/P08）清零；无法清零则 status 降级并写明局限。
- **步骤 4（rerun_consistency）**：`rerun_consistency.py --cmd ...`（或 `--from-checkpoints`）复跑机器阶段，判定 STABLE/DRIFT；DRIFT 时按报告的原因分类（时间戳/随机数/字典序/环境依赖）消除后重跑。
- **步骤 5（导出）**：`checkpoint.py export` 汇总 case 契约、作答文件、probes 报告与检查点，原子刷新 `result.json`（含 change_records 与 qc 摘要）。`checkpoint.py status` 确认完成矩阵。

## 异常处理表

| 异常 | 处理 |
|---|---|
| 输入损坏（case.json 畸形/缺 output_contract） | init_run 降级：case_id=unknown-case、契约字段为空并写 warning；骨架照常落盘，绝不崩溃 |
| 权限不足（目录不可写） | init_run 报 fatal 并非零退出；优先尝试工作目录内重定向，保住已写产物 |
| 工具缺失（pdftotext/pdfinfo 不在） | manifest 标记 unavailable；改用纯文本材料或人工摘录，流程继续 |
| 超时/中断 | 重跑 init_run（幂等）→ `checkpoint.py status/resume` 找续跑点；STALE 阶段重跑后继续；result.json 骨架保证有诚实 partial 可交 |

## 交付前自查

1. `rerun_consistency` 判定 **STABLE**（DRIFT 已消除或已解释并修复）。
2. `probes_report.json` 未处理高危（high）为 0；中低位命中已在 status_reason/uncertainty 声明。
3. `run_manifest.json` 完整（输入 sha256、工具探测、预算台账齐全）；`checkpoint.py status` 无 STALE。
4. `result.json`：契约字段齐全（或 null+uncertainty）、status 与内容一致、sources 非空、change_records 完整。

## 限制

- 一致性审计只覆盖**机器阶段**（预检、检查点、探针、导出等确定性产物）；模型起草本身非确定，措辞允许微差，语义与证据锚点须一致。
- 探针为规则式启发，不能替代人工核验；漏报不免责，误报可人工复核后忽略。
- 本技能包**不含任何预制答案**；`examples/` 全部为合成示例（SYNTHETIC EXAMPLE），与隐藏案例无关。

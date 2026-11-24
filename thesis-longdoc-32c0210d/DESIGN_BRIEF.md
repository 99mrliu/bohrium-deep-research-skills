# 共享设计简报 — challenge-32c0210d「学位论文与长文档写作」五方向 Skill 束

本简报是五份 bundle 的共同事实基线。每份 bundle 的独有内核由各自任务书规定；
本简报只规定**不可违背的公共契约**。

## 1. 评测机制（组织方原文要点）

- 这是 Skill 出题任务。平台把参赛 Skill 安装到 `/skills/weekly-skill`，然后用官方
  DeepSeek Harness 在 **3 个固定案例**上各跑 3 次，与"不加载 Skill 的基础 Agent"对照。
- 运行时输入：`/input/case.json` 与 `task.md`；材料按题目提供。
  Organizer input repair v1 明确：**实际编辑目标与离线工作范围写在
  `organizer-edit-workorder.json`**；W16 案例把原始论文以**分章节可编辑工作稿**
  （sectioned editable working chapters，即若干 Markdown 章节文件）提供，不是成书。
  若提供 PDF，拿到的是原始 PDF，没有预抽取答案层，需自行 `pdftotext`。
- 预算：64 次模型请求、900 秒、单次响应 16384 token（含推理）。
- 工作目录 `/app/work`；最终产物与可编辑稿件放 `/app/output`，其中必须有
  `result.json`：**包含 `case_id` 与 `output_contract` 声明的全部字段**，
  并含诚实的 status、sources、uncertainty、change records。
  部分完成必须写明限制（诚实 partial）；**先存可用 partial 再增量改进**。
  可编辑的 Office/图示类产物应附真实渲染的 PDF/PNG 预览（渲染器不可用则如实记录）。
- 禁止：预制答案冒充运行结果、编造软件状态或科学数据、按错误领域标签补造数据。

## 2. case.json / workorder 形态（据组织方修复说明与合成样例）

```json
// case.json
{"case_id": "...", "task": "...", "output_contract": {"fields": ["edited_chapters", "change_record", "consistency_report", "uncertainty", "..."]}}

// organizer-edit-workorder.json
{"schema": "organizer-edit-workorder/v1", "scope": "offline local workflow on sectioned chapters",
 "items": [{"id": 1, "title": "术语统一", "action": "将全文的“隔膜”统一为“隔板”……",
            "target": "全部章节", "acceptance": "除引用标题外不再出现“隔膜”"}]}
```

注意：真实案例的 contract 字段集合以**实际 case.json 为准**，Skill 必须
**运行时读取** `output_contract.fields` 并逐字段填充，缺字段填 null + 记录问题，
不得硬编码字段名。

## 3. 平台资源约束（违反即废）

- ≤50 个 UTF-8 文本文件；单文件 ≤500KB；总计 ≤2MB；无符号链接；无二进制。
- 目录结构固定为：
  ```
  <bundle>/
    SKILL.md            # 合法 YAML frontmatter（name、description）+ 完整工作流
    README.md           # 一页概览（GitHub 读者用）
    GITHUB_URL.txt      # 第一行 GitHub 链接，第二行 SKILL.md
    scripts/            # 实际被 SKILL.md 调用的脚本（python3 标准库，唯一可选外部依赖 pdftotext）
    references/         # 规则/模板/schema 文档
    examples/synthetic/ # 最小合成示例（见 §5）
  ```

## 4. SKILL.md 质量基线（旧作低分教训）

旧作 5 份得分 56–76（榜顶 83），失败模式：

1. **只记账不干活**：ledger/checklist 堆叠，脚本只"检查"不"执行"，模型在 900s 内
   忙于留痕而章节没改完。新规约：**凡是机械可判定的操作必须由脚本确定性完成**；
   模型只做非机械判断。每个脚本都要有"它替模型省了什么"的明确答案。
2. **流程冗长难遵循**：DeepSeek Harness 的通用 Agent 只有 16k token/响应，
   SKILL.md 必须是**可直接照做的命令序列**（每步给完整命令，路径用
   `/skills/weekly-skill/...`），不要抽象方法论散文。
3. 缺预算意识：没有"先存 partial 再改进"的指令，超时即零分。

SKILL.md 必含小节：用途与触发条件 → 输入契约（/input 布局、case.json、workorder）
→ 工作流（按序命令，标注哪些步骤是模型任务、哪些是脚本任务）→ 输出契约
（result.json 字段填充规则、诚实 partial 规则）→ 异常矩阵（材料缺失/引文找不到/
渲染器不可用/目标缺失/时间不足各自的降级路径）→ 依赖与文件清单 → 已知边界。

## 5. 合成示例契约

- `examples/synthetic/input/`：自造的 case.json + organizer-edit-workorder.json +
  chapters/（3 个短章节 Markdown，内容自造、与任何真实论文无关）。
- `examples/synthetic/run_example.sh`：在 macOS `/bin/bash` + 系统 python3 下
  **一键端到端跑通**：模拟 /input、/app/work、/app/output 三段式，调用 bundle 内
  脚本产出全部产物。输出必须确定性（不得在 expected 文件里写绝对路径、时间戳）。
- `examples/synthetic/expected/`：冻结的预期产物（result.json 等）。
- 所有示例产物带 `"note": "SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"` 或
  等效中文标注；README 与 SKILL.md 中明确示例为合成。
- 构建者必须真实执行 run_example.sh 并目检产物，expected 由真实运行固化，不得手写。

## 6. 五方向（错位重心，零共享文件）

| bundle 目录 | 名称 | 重心 |
|-|-|-|
| a-surgical-edit-engine | surgical-edit-engine | 工单→操作 DSL→脚本直接落改（编辑执行） |
| b-source-fidelity-firewall | source-fidelity-firewall | 论断↔来源逐字核验、防编造（上游数据真实性） |
| c-xref-index-engine | xref-index-engine | 图表/引文/术语注册表与级联影响分析（跨章节一致性） |
| d-deliverable-forge | deliverable-forge | output_contract 装配、渲染预览、原子交付（下游交付工程） |
| e-budget-runbook-qc | budget-runbook-qc | 900s/64 请求预算调度、checkpoint、验收门（过程质量控制） |

每份 bundle 仍是**完整可用的 Skill**（能独立把案例从头跑到 result.json），
只是机制内核与篇幅重心不同。脚本数量 3–5 个，单脚本 ≤400 行，stdlib-only。

GitHub 路径：`thesis-longdoc-32c0210d/<bundle目录名>/`，GITHUB_URL.txt 第一行：
`https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/thesis-longdoc-32c0210d/<bundle目录名>`。

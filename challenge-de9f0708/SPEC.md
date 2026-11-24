# 共用构建规范（challenge-de9f0708「学术规范与合规检查」五方向 skill bundles）

## 背景与运行契约
平台（Harbor）评审时把 Skill 安装到 `/skills/weekly-skill`，用官方 DeepSeek Harness 在 3 个固定案例上
运行。每个案例：`/input/case.json` + `/input/task.md`，并按题目提供科研材料（通常是论文 PDF；
PDF 解析拿到的是真实 PDF，没有预抽取的答案层——必须读真实文件，不得从标签臆测内容）。
Agent 在 `/app/work` 工作，交付到 `/app/output`，其中 `result.json` 必须含 `case_id` 与
case.json 里 `output_contract` 要求的全部字段，并诚实标注 status（complete/partial/blocked）、
sources、uncertainty、change_log。partial 必须指明局限。执行预算：64 次模型请求、900 秒、
每响应 16384 tokens。脚本是省预算的关键：机械工作全部交给脚本。

## 本题任务实质
对固定论文/科研材料做质量、引用、事实、方法、统计、逻辑或规范审查，逐条给出证据与严重度。
组织方修订说明：**每个案例有自己具体的审查面（review facets）、类型化 findings 与证据/修改要求；
没有预埋的缺陷判决**（no forced or planted defect verdicts）——报出的每个问题必须真实成立并能
指回原文具体位置；漏报与误报同样扣分。评判三件事：
1. 报出的问题是否成立并能指回原文具体位置（文件+页码+章节+逐字摘录）；
2. 每条判定是否有可核对依据（规范条款、目标期刊要求、数据授权范围、外部数据库记录）；
3. 报告能否被他人在同一份材料上复跑出基本一致的结论。
必须区分：事实错误 / 证据不足 / 规范问题 / 建议性意见；无法确认的标 `待复核`，不凭空补结论。

## case.json 预期结构（以实际文件为准，脚本必须容错）
```json
{
  "case_id": "…",
  "task": "…（可能逐条列出审查面 review facets）",
  "materials": ["paper.pdf", "…"],
  "output_contract": {"required_fields": ["case_id", "…", "status", "uncertainty", "sources", "change_log"]}
}
```
脚本对缺键不得崩溃：读不到的字段按空处理并在输出中说明。

## 五个方向（重心错位，不是同一管道的五个变体）
- **skill-a-evidence-anchor**：上游文本锚定工程。机械保证每条 finding 的 quote 逐字出现在
  抽取文本的声称位置；锚定验证不过的 finding 自动降级为 `待复核`。
- **skill-b-coverage-ledger**：过程质量控制。case.json 审查面 → 检查清单实例化 → 覆盖矩阵；
  开工先落合法 partial result.json 保底；预算账；未检查面如实记账。
- **skill-c-external-verify**：外部事实核验（上游数据真实性）。参考文献抽取与本地 lint +
  严格预算的 Crossref/DOI 联网核验；两信号规则才可判疑似捏造；断网优雅降级为 `待复核`。
- **skill-d-calibration-chamber**：判定校准与误报抑制。严重度规则引擎 + 风格/违规鉴别表 +
  对抗式二审（控辩）+ 降级纪律，保证每条判定强度与证据匹配。
- **skill-e-deliverable-forge**：下游交付渲染工程。result.json 对 output_contract 的机械验收
  （FAIL 自动降级诚实 partial）+ 人读报告渲染 + 严重度看板 + 修改优先级清单。

重要：每个 SKILL.md 都必须指导 Agent 完成**案例声明的全部审查面**的完整审查报告——方向只改变
"重心"（哪一环由脚本机械保证），不允许只交付方向内的局部产物。覆盖不全的审查面必须出现在
`not_reviewed` 中并说明原因。

## findings 统一要素（五个 bundle 一致，便于复跑一致）
每条 finding：`id`、`type`、`severity`(critical/major/minor/info)、`location`{file,page,section,quote
逐字}、`evidence`（本地规则名/外部来源+检索到的原文）、`suggestion`（可执行）、
`verdict_status`(确认/待复核+理由)。类别归属：fact_error / insufficient_evidence / norm_issue /
suggestion 四选一外加 type 细分。

## 每个 bundle 的硬性要求
- 目录：`/Users/liuhengshen/Desktop/bhr_product/3rd/4/submit/skills-de9f0708/skill-<x>-<name>/`
- 结构（全部 UTF-8 文本、无符号链接、无二进制、≤50 文件、单文件 ≤500KB、总计 ≤2MB；实际目标 ≤20 文件、≤200KB）：
  - `SKILL.md`：YAML frontmatter 仅含 `name` 与 `description`（description 写清何时触发使用，
    中英文均可）。正文章节：1 用途与新增价值；2 适用条件与不适用情况；3 运行时契约与路径
    （/input、/app/work、/app/output、/skills/weekly-skill）；4 工作流（编号步骤，含可直接复制的
    脚本命令，脚本路径用 /skills/weekly-skill/scripts/…）；5 输出契约（result.json 字段与
    findings 要素）；6 失败模式与止损表；7 降级策略（honest partial）；8 预算意识（先存 partial 再迭代）。
  - `scripts/*.py`：仅 Python 3 标准库；确定性；缺键不崩（exit 0 输出 partial 报告）；支持 --help；
    单次运行 <5 秒。命令行契约：显式输入路径 → 显式输出路径。
  - `references/*.md`：该方向方法论/清单/规则表，供 Agent 运行中查阅。
  - `examples/`：`mock_case.json` + 合成论文文本（纯文本 .txt 即可，note 字段标明"合成示意案例"）、
    `run_example.sh`（真实可执行，bash，set -euo pipefail，把输出写到 examples/output/）、
    已真实生成的 `examples/output/*`、`example_run.md`（说明这是合成示例、如何复跑、输出如何解读）。
    示例输出文件头部注明"合成示例输出，非正式测评结果"。合成论文必须埋入已知问题（如编造嫌疑文献、
    元数据错误、缺失伦理声明、疑似 PII、无依据论断），使脚本有真实可抓之物。
  - `GITHUB_URL.txt`：第一行写
    `https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/challenge-de9f0708/skill-<x>-<name>`
- 科学诚实：任何判定必须可定位到材料原文逐字摘录或标注为待复核；不得编造条款、期刊要求或文献元数据；
  外部核验只记录实际检索到的内容。
- 构建完成后必须真实端到端跑通 examples/run_example.sh，目检输出文件，并在汇报中说明跑了什么命令、
  看到了什么（含埋入问题是否被如数抓出）。

---
name: provenance-ledger-gate
description: 来源溯源核验门——在比较候选实验方案之前先"对账"：把每个方案里的数值、参数与论断逐条锚定到 /input 真实来源材料（论文抽取文本、价格/预订契约）的逐字片段上，锚不住的一律隔离，不进入比较。当任务要求比较/选择多个候选方案且案例附带论文、契约、有限参数域等来源材料时触发；也适用于任何"数字必须有出处"的方案审查。不适用于：无来源材料可对账的纯开放式设计题、只需单一方案撰写而无比较的任务、以及来源全是未抽取二进制且无法取得文本层的情况（此时本 Skill 只能登记指纹并如实报告 partial）。
---

# provenance-ledger-gate（来源溯源核验门）

理念：**比较之前先对账。** 候选方案里的每个数值/参数/论断，必须能在 /input 的
真实来源材料里逐字锚定；锚不住就隔离，绝不带进比较表和最终选择。本 Skill 直接
服务评分点"结果正确性：方案比较中的数字、来源与最终选择是否站得住"。

## 1. 解决什么问题

- **数字没来源**：方案里的温度、浓度、价格、货期凭空出现，比较表看似整齐实则无据。
- **凭标签臆测材料内容**：只看文件名/PDF 标题就"引用"论文结论——评测材料必须先读
  真实文件，PDF 没有预抽取答案层，臆测必然出错。
- **方案各写一套、无法对照**：字段名、单位、口径不统一，比较流于印象分。
- **参数越界没人拦**：方案给出超出有限参数域/硬约束的取值，不经校验就进决赛。

## 2. 何时使用与不适用

**使用**：/input 含 case.json + task.md + 来源材料（论文 PDF 及其抽取文本、前瞻性
价格/预订契约）+ 多个版本化候选方案，任务是"比较并选择"。
**不适用**：无任何来源文本可对账（只能登记指纹并写 partial）；单方案撰写题；
任务明确不要求溯源的纯创意题。

## 3. 模型 / 脚本分工

- **模型只做判断**：读真实文件、从方案中逐字段抽取 claims（含 source.quote 逐字
  片段）、对脚本对账结果做裁决与隔离决策、撰写七类字段与 result.json 全文。
- **脚本做一切确定性工作**（纯 Python3 标准库，无 wall-clock/随机数，双跑逐字节
  一致）：指纹登记、逐字对账、参数域/硬约束/单位校验、自查。
- 预算约束（64 次模型请求 / 900 秒 / 每响应 16384 token）下，模型不得手工做
  字符串匹配或数值比较——这些全部交给脚本。

## 4. 运行时契约（事实，必须遵守）

- Skill 安装于 `/skills/weekly-skill/`；输入在 `/input`：`case.json`、`task.md`
  及子目录中的科研材料（真实论文 PDF、组织方前瞻性契约、每案 3 个版本化候选
  方案、有限参数域、rubric/硬阈值）。**必须先读真实文件**，不得凭文件名/标签
  臆测内容。
- 案例是组织方构造的规划情景：契约数字是**前瞻性给定**，不是真实实验室/供应商
  报价或安全审批；result.json 中不得把情景数字说成实测。
- 工作目录 `/app/work`；最终结果放 `/app/output/`，必含 `result.json`：
  `case_id` + `output_contract` 的**全部原始字段**（逐键从 case.json 读取，不漏键、
  不臆造键名），并含诚实 `status`、`sources`、`uncertainty`、变更记录；partial
  必须写明限制。**尽早落盘部分 result.json，再增量改进。**

## 5. 完整工作流（严格按序）

### 步骤 0：读题与盘点（模型）
1. 读 `/input/case.json` 与 `/input/task.md`；逐键记录 `case_id` 与
   `output_contract` 的键名清单。
2. `ls -R /input` 盘点材料：来源文件、候选方案文件、参数域/约束位置。
3. **立即落盘部分 result.json** 到 `/app/output/result.json`：先写 `case_id`、
   `output_contract` 全键的占位值、`status: "partial"`、`uncertainty` 说明
   "对账未完成，以下为占位"；之后每完成一步增量更新。

### 步骤 1：登记来源指纹（脚本）
```bash
python3 /skills/weekly-skill/scripts/source_registry.py \
    --input-dir /input --out /app/work/registry.json --asof <case给定日期或省略>
```
- `.txt/.md/.json` 直读 UTF-8 文本并内联；`.pdf` 等只记 SHA-256 并标
  `needs_extraction: true`。
- 对 needs_extraction 的 PDF：模型用可用工具取得文本层后，把抽取文本存为
  `/app/work/extracted/<原名>.txt`，再对该目录重跑一次登记（两次 registry 都在
  result.json 的 sources 中声明）。**抽不出文本层的来源，其上的论断一律隔离。**

### 步骤 2：逐方案抽取 claims（模型）
- 按 `references/claim_schema.json` 与 `references/field_groups.md`，对每个候选
  方案的七类字段逐条抽取：{plan_id, field_group, field, value, unit, status,
  source{file, locator, quote}}。
- `quote` 必须是来源文本的**逐字片段**（允许空白差异），包含支撑 value 的关键
  数字；改写/翻译/拼接必被脚本判 unsupported。写 `/app/work/claims.json`。

### 步骤 3：脚本对账（两道确定性门）
```bash
python3 /skills/weekly-skill/scripts/claim_audit.py \
    --claims /app/work/claims.json --registry /app/work/registry.json \
    --out-json /app/work/audit.json --out-md /app/work/audit.md
python3 /skills/weekly-skill/scripts/domain_check.py \
    --case /input/case.json --plans /input/<方案目录或文件...> \
    --out /app/work/domain_report.json
```
- claim_audit：六种 verdict（supported/unsupported/conflict/missing_source/
  recorded_inferred/recorded_missing，定义见 `references/audit_method.md`）；
  任一 unsupported/conflict/missing_source → exit 3 且 stdout 打印缺陷清单。
- domain_check：参数域（区间 `{"min":..,"max":..}` 或枚举列表）、硬约束
  （budget_cny/deadline_days，若给出）、跨方案单位一致性；违例 → exit 3。
- exit 2 = 输入/用法错误：修正后重跑，不要把 2 当拦截。

### 步骤 4：基于对账结果撰写 result.json（模型）
- **隔离**：verdict 为 unsupported/conflict/missing_source 的论断所属字段整字段
  隔离，不进比较表；域外/超约束参数同理。隔离清单写入 `evidence_basis` 与
  `uncertainty`。
- **比较**：只用 supported 锚点 + 明确标注的 inferred 假设做七类字段对照，
  给出最终选择与一句话理由；关键方案被隔离到无法比较时如实写"不可比/不可行"。
- 写全 `output_contract` 每一键 + `status`（complete/partial，partial 写明限制）
  + `sources`（registry 指纹与文件清单）+ `uncertainty` + 变更记录。

## 6. 脚本用法与退出码

| 脚本 | 用途 | 退出码 |
|---|---|---|
| `source_registry.py --input-dir D --out R [--asof 日期] [--note 备注]` | 递归登记 SHA-256/字节数/文本抽取 → registry.json | 0 成功；2 用法错误 |
| `claim_audit.py --claims C --registry R --out-json J --out-md M [--note 备注]` | 逐字对账 → audit.json + audit.md | 0 全部通过；2 用法错误；3 存在 unsupported/conflict/missing_source（缺陷清单写 stdout，产物仍写出） |
| `domain_check.py --case CASE --plans P... --out O [--note 备注]` | 参数域/硬约束/单位一致性 → domain_report.json | 0 无违例；2 用法错误；3 存在违例（清单写 stdout，报告仍写出） |
| `selfcheck.py [--examples-dir E]` | 在合成示例上端到端自查 | 0 全过；2 用法错误；3 自查未通过 |

所有脚本 `python3 <脚本> --help` 可用；输出 JSON 键排序、无时间戳（日期只能由
`--asof` 显式给定），同一输入双跑逐字节一致。

## 7. 七类字段与确认项的落地方式

result.json 中**每个方案对象**含七组字段 + `evidence_basis` + `confirmations`：

```json
{
  "plan_id": "PLAN-X",
  "assumptions": [...], "variables": [...], "controls": [...],
  "steps": [...], "parameters": [...], "resources": [...],
  "interpretation_criteria": [...],
  "evidence_basis": [
    {"field": "parameters.fbs_percent", "verdict": "supported",
     "file": "...", "locator": "...", "quote": "...", "char_offset": 266},
    {"field": "parameters.temperature_c", "verdict": "unsupported",
     "action": "quarantined", "risk": "..."}
  ],
  "confirmations": {
    "safety": {"state": "pending", "note": "无来源明示安全审批，待确认"},
    "ethics": {"state": "pending", "note": "..."},
    "equipment_availability": {"state": "pending", "note": "..."},
    "expert": {"state": "pending", "note": "..."}
  }
}
```

- 七组定义与填写规范见 `references/field_groups.md`；缺组写空数组并在
  uncertainty 说明，不得省略键。
- `confirmations` 四键取值 confirmed/pending/not_applicable；**没有来源或组织方
  文件明示确认的一律 pending；pending 项只能写"待确认"，不得写成已确认事实或
  可执行步骤**。
- inferred 值进入比较时必须标注"假设，未经证实"；missing 字段进入 uncertainty。

## 8. 异常分类处置

| 异常 | 处置 |
|---|---|
| 设备不可得（预订契约无窗口/被占用） | 该方案 resources 标"设备可用性 pending→不可行风险"；confirmations.equipment_availability=pending；不因此编造替代设备 |
| 耗材超预算/超货期 | domain_check 判 over_budget；方案标"预算内不可行"，比较表保留但选择时排除并说明 |
| 参数窗口冲突（参数域 ∩ 方案需求为空） | 记 domain 违例 + uncertainty；不得擅自扩域 |
| 候选方案全部不可行 | result.json status=partial，明确写"全部方案被隔离/违例，无可执行选择"，列出每案原因，不硬选一个 |
| 材料缺失（来源文件缺、PDF 抽不出文本层） | registry 标记 needs_extraction；相关论断全部 missing_source/unsupported 隔离；status=partial 写明限制 |
| 无法判断（两方案 supported 证据打平） | 在 comparison 中如实写"证据不足以区分"，给出需补充的确认项，不抛硬币 |
| 运行失败（脚本 exit 2 / 环境异常） | 保留已落盘的部分 result.json（partial + 变更记录），修输入重跑；预算不足时以最近一致的部分结果交付 |

## 9. 自查（selfcheck）

交付前运行：
```bash
python3 /skills/weekly-skill/scripts/selfcheck.py
```
它在 `examples/` 合成输入上验证：正例 exit 0；负例 exit 3 且缺陷清单**精确命中**
预埋陷阱（1 unsupported + 1 conflict + 1 域外参数）；同一命令双跑产物逐字节一致。
selfcheck 不过 → 不得交付。评测现场复核：result.json 含 output_contract 全键、
隔离清单非空时可逐条指认 verdict、confirmations 无 pending 被写成 confirmed。

## 10. 适用边界

- 只做"数字有没有出处、出不出域"的核验；科学合理性本身（设计优劣、统计功效）
  仍需模型判断，本门不代替评审。
- 对账是逐字匹配：同义改写、跨语言转述天然判 unsupported——这正是设计意图
  （宁隔离、不放过），代价是需要模型在步骤 2 给出忠实逐字 quote。
- PDF 无文本层且无法抽取时，本 Skill 只能登记指纹并交付 partial，不伪造锚点。
- 不声称真实实验室/供应商数据；契约数字一律标注"前瞻性情景给定"。

## 11. 合成示例说明

`examples/` 为**合成示例 / SYNTHETIC EXAMPLE，非正式案例结果**：虚构细胞系
XJ-7、虚构供应商与设备、虚构契约。含一组正例（claims_good.json 全 supported）
与一组 booby-trap 负例（claims_bad.json：1 unsupported + 1 conflict；
plan_b.json：1 个域外参数），均被脚本精确捕获（exit 3）。`outputs/` 是真实跑出的
示意产物，调用命令序列见 `examples/README.md`。

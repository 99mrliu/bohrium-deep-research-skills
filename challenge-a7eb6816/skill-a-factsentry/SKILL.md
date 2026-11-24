---
name: factsentry-fact-fidelity
description: >-
  上游科学事实与数据保真（fact fidelity）技能。触发场景：依据给定科研源文完成改写、
  翻译、科普化或申报化写作，且必须保证数字、单位、图表编号、引用标记与论断强度与源文
  一致时使用。流程：先用确定性正则从源文提取证据台账 evidence_ledger.json（数字+单位、
  图表引用、引用标记、论断强度词，均带锚句与 file:line 定位），再对改写稿逐条核验，
  检出数字漂移、单位错配、图表/引用丢失、论断强度升格（含相关→因果），输出带定位与
  修复建议的 fact_check_report（JSON + Markdown），退出码 0=PASS、3=发现 drift。
---

# FactSentry：科研改写的事实保真核验

## 重心与边界

**重心**：改写/翻译/科普化/申报化过程中，改写稿相对源文的**事实漂移**检测，覆盖四类：

1. **数字漂移**：数值被改动（99.2% → 99.8%）或凭空出现；
2. **单位错配**：数值对但单位变了（180 °C → 180 K、mg/L → g/L）；
3. **证据丢失**：源文中的数字、图表编号（图1/Fig. 2/表3/Table S1）、引用标记（[1]、(Author, 2020)）在改写稿中消失；
4. **论断强度升格**：源文「初步表明/提示/相关」，改写稿变成「证实/导致」（强度阶梯见 `references/claim_strength_ladder.md`）。

**边界（不做什么）**：

- 不判断科学内容本身的真伪，只判断**改写稿与给定源文是否一致**；
- 不做语言润色、结构改写、受众适配（那是下游写作技能的事）；
- 不解析 PDF/图片/表格二进制，只处理纯文本（md/txt）；PDF 需先转文本（见「异常处理」）；
- 不做单位换算（180 °C 与 356 °F 视为不一致并告警，由人工裁决）。

## 运行契约

- 输入只读：`/input/case.json` 与 `/input/task.md`（或题目给定路径），**绝不写回 /input**；
- 中间产物（台账、草稿、日志）一律放 `/app/work`；
- 最终产物放 `/app/output`，其中 `result.json` **必须包含 case_id 与 case 自带 output_contract 的全部字段**；
- **诚实 partial**：任何一步失败或核验未通过，result.json 的完成度字段如实写 partial/未完成原因，**不得预制答案、不得把 FAIL 写成 PASS**；
- **先落保底 result.json**：开工第一步先按 output_contract 写出占位 result.json（字段置 null/partial），流程结束或异常退出前再更新为最终状态，保证崩溃也有兜底产物；
- 本技能的核验报告（fact_check_report.json/.md）与证据台账（evidence_ledger.json）建议一并复制到 /app/output 作为 result.json 的支撑材料。

## 标准流程

以下 bash 序列可直接复制执行。`$SK` 代指技能安装路径 `/skills/weekly-skill`，并带 fallback 定位。

```bash
# 0) 定位技能目录（fallback：全盘浅层搜索本技能的标志脚本）
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/ledger_extract.py" ]; then
  P=$(find / -maxdepth 6 -name ledger_extract.py 2>/dev/null | head -n 1)
  [ -n "$P" ] && SK=$(dirname "$(dirname "$P")")
fi
echo "SK=$SK"

# 1) 准备工作目录，读取 case
mkdir -p /app/work /app/output
cp /input/case.json /app/work/case.json
cat /input/task.md

# 2) 先落保底 result.json：含 case_id 与 output_contract 全部字段，诚实标记 partial
python3 - <<'EOF'
import json, os
case = json.load(open('/input/case.json', encoding='utf-8'))
contract = case.get('output_contract', {})
keys = list(contract.keys()) if isinstance(contract, dict) else list(contract)
result = {'case_id': case.get('case_id', 'unknown'), 'status': 'partial',
          'note': '保底占位：核验流程未完成或未完成全部字段填写'}
for k in keys:
    result.setdefault(k, None)
os.makedirs('/app/output', exist_ok=True)
json.dump(result, open('/app/output/result.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print('保底 result.json 字段:', ['case_id'] + keys)
EOF

# 3) 汇总源文（按 task.md 指示的实际路径替换 SOURCE_GLOB），提取证据台账
#    退出码：0=成功；2=用法或输入/输出错误
python3 "$SK/scripts/ledger_extract.py" /app/work/source*.md -o /app/work/evidence_ledger.json
echo "ledger_extract exit=$?"

# 4) 人工/模型完成改写稿，保存为 /app/work/draft.md（此步由智能体完成）

# 5) 事实核验：0=无 drift（PASS）；3=发现 drift（FAIL）；2=用法/IO 错误
python3 "$SK/scripts/fact_check.py" \
  --ledger /app/work/evidence_ledger.json \
  --draft /app/work/draft.md \
  --json-out /app/work/fact_check_report.json \
  --md-out /app/work/fact_check_report.md
echo "fact_check exit=$?"

# 6) 若退出码为 3：按报告中的定位与修复建议修订 draft.md，回到第 5 步，直至 PASS；
#    引用标记丢失默认为 recommended 级（不阻断），如需更严可加 --min-severity recommended

# 7) 收尾：复制产物并更新 result.json 为最终状态（PASS 才允许标 complete）
cp /app/work/evidence_ledger.json /app/work/fact_check_report.json /app/work/fact_check_report.md /app/output/ 2>/dev/null || true
```

退出码约定（两脚本一致）：**0 = PASS/成功；3 = fact_check 发现 drift；2 = 用法或输入/输出错误**（文件缺失、JSON 损坏、编码非 UTF-8）。

## 异常处理

- **源文缺引用**：台账中 citation 条目为空属正常情况（如内部报告）。此时 dropped_evidence 不产生引用类发现；不得因为「没有引用」而给改写稿编造引用。
- **数据冲突**：源文多处出现同语境不同值（如摘要 99.2%、正文 99.5%）。台账会全部收录，改写稿匹配任一值均不告警；发现冲突时应在交付说明中注明，以正文/图表值为准并在 result.json 备注，而不是擅自「修正」。
- **PDF 抽取歧义**：PDF 转文本常丢失上下标（m²/g → m2/g、10⁻³ → 10-3）、把 °C 拆成 o C、表格列错位。处理：转换后先人工通读一遍，统一单位写法（本技能归一化 ％→%、℃/°C、µm/μm），再提台账；对量级敏感的数字（10 的幂次）必须回查原文。
- **改写稿出现源文没有的数字**：记 unsupported_number；若确为合理换算（如 100 h → 约 4 天），应改写回源文口径，或在交付说明中显式标注「换算自源文 X」。
- **论断句无法配对**（相似度低于阈值 0.15）：保守不判，但这也意味着源文中可能不存在对应论断——人工复核该句是否为新增断言。

## 最小合成示例说明

`examples/` 内含一个完全虚构的「Co3O4/CeO2 催化剂」合成示例（非正式案例结果）：

- `source.md` 源文 → 提取出 21 条台账条目（数字 10、图表 3、引用 3、强度词 5）；
- `draft_bad.md` 故意含缺陷的改写稿 → 核验 **FAIL（退出码 3）**：2 个数字漂移（180→160 °C、99.2→99.8 %）、1 个图表引用丢失（表1）、2 个论断强度升格（初步表明→证实、相关→导致）等共 13 条发现；
- `draft_good.md` 保真改写稿 → 核验 **PASS（退出码 0）**，0 条发现。

运行命令与真实输出见 `examples/README.md`，脚本真实运行输出保存在 `examples/expected/`。

## 局限

1. 纯正则、纯文本：不解析 PDF/Word/图片，复杂单位（如 mL·g⁻¹·h⁻¹）按最长前缀匹配（如只认 mL），需要时先人工统一写法；
2. 不做单位换算与数量级推断，跨单位一致（180 °C = 356 °F）会误报为 unsupported_number；
3. 中文数字（「三倍」）、口语化数值（「近一半」）不提取；
4. 论断句配对基于字面相似度：改写幅度极大（同义重写）时可能配对失败而漏检升格；配对错误时可能误检，报告中给出配对双方锚句供人工裁决；
5. dropped_evidence 按「值+单位 / 编号 / 引用 key」判存在性，改写稿用完全不同的措辞重述同一数据（如「翻倍」代替「提升 2.3 倍」）会报丢失——默认策略是**宁严勿漏**，确需压缩时按 `references/retention_priority.md` 的规则在交付说明中注明；
6. 只处理 UTF-8 文本；其他编码返回退出码 2。

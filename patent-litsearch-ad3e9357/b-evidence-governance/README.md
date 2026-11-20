# README — claim-evidence-governance-auditor

专利/技术文献检索任务的**证据治理与风险分级** Skill（方向 B：权利要求/法律状态/
授权边界）。核心理念：**引文闸控（quote-gated）**——任何输出论断都必须携带逐字
引文与定位，并由脚本**确定性回核**引文真实存在于来源文本；法律状态走**官方登记
优先**；数据源按授权**绿/黄/红分级**；每条结论带**风险分级 + 人工复核清单**。

## 目录结构

```
skill/
├── SKILL.md                      # Skill 定义（触发条件、调用方式、案例路由、异常表）
├── README.md                     # 本文件
├── scripts/                      # 全部仅依赖 Python 标准库
│   ├── evidence_ledger.py        # 证据账本：数据结构与校验（库 + CLI append/validate/show）
│   ├── quote_audit.py            # 确定性引文回核（严格/OCR 容忍双模式，伪造即 exit 1）
│   ├── status_ledger.py          # 法律状态台账与核验协议（登记优先 + 未知纪律规则引擎）
│   ├── license_tiers.py          # 数据源授权分级（绿/黄/红 + 能力降级方案）
│   ├── risk_grade.py             # 结论风险分级规则引擎（high/medium/low + 复核清单）
│   ├── scaffold_result.py        # result.json 骨架生成（镜像 output_contract 全部字段）
│   └── selfcheck.py              # 自测：合成夹具 + 11 项正/负例断言
├── rules/                        # 人读规则文档（与脚本内置规则保持一致）
│   ├── legal_status_protocol.md  # 登记优先、查询日期、滞后与 unknown 纪律
│   ├── authorization_boundary.md # 绿/黄/红分级规则表与降级方案
│   └── risk_grading.md           # 风险触发规则与分级口径
├── templates/
│   ├── result_fields.md          # result.json 字段细则
│   └── ledger_format.md          # 证据账本/状态台账记录格式
└── examples/
    ├── example_walkthrough.md    # 逐步可运行示例（虚构数据）
    └── fixtures/                 # 合成夹具（全部虚构，标注 illustrative，由 selfcheck 生成）
```

## 快速开始

```bash
# 自测（11 项断言，全过 exit 0）
python3 scripts/selfcheck.py

# 在 Harbor 运行时中的典型流程（详见 SKILL.md 第 3 节）
python3 scripts/scaffold_result.py --case /input/case.json --out /app/output/result.json
pdftotext -layout /input/<材料>.pdf /app/work/<材料>.txt
python3 scripts/evidence_ledger.py append --ledger /app/work/evidence_ledger.jsonl \
  --claim-id C1 --statement "..." --quote "<逐字引文>" \
  --file /app/work/<材料>.txt --page 2 --source-kind patent_pdf_text
python3 scripts/quote_audit.py --ledger /app/work/evidence_ledger.jsonl \
  --base-dir /app/work --ocr-tolerant --report /app/output/quote_audit_report.json
```

## 方法要点

1. **证据账本**：论断 → 逐字引文 + 定位 + SHA-256 引文哈希，先登记后使用；
2. **确定性回核**：空白规范化后的逐字子串核验；OCR 文本走容忍模式
   （大小写折叠、连字符/换行合并、相似度阈值 0.92），且容忍匹配必须事先在记录中
   声明 `allow_ocr_tolerance=true`、事后再报告中标注 `match_mode=ocr_tolerant`；
3. **登记优先**：状态结论的登记依据只能是 official_register / official_gazette；
   聚合页只能 `leads_only`；推断状态必须 `downgraded` 且配人工复核建议；
   `未知` 状态禁止确定性措辞（规则引擎强制拦截）；
4. **授权分级**：绿=官方公开库、黄=开放聚合（注明来源）、红=许可受限（禁止抓取，
   用绿色源替代并标注覆盖缺口）；
5. **风险分级**：字段缺失/状态过期/同族口径不明/语料覆盖不全/OCR 不确定/单一来源/
   引文未核验/状态未知 八类触发规则计分，0 分 high、1–3 分 medium、≥4 分或引文
   未核验 low，并自动生成人工复核清单。

## 约束与兼容性

- 全部脚本仅依赖 Python 标准库（python3 ≥ 3.8）；文本处理外部依赖仅 pdftotext /
  PDF 渲染 / OCR（运行时提供）；
- 全 Skill 为 UTF-8 文本，无符号链接；夹具全部虚构并标注 illustrative，
  不预置任何真实案例答案；
- 兼容 Harbor 契约：/input/case.json + task.md 输入，/app/output 产物，
  result.json 镜像 output_contract 全部字段，status 诚实（ok/partial/failed）。

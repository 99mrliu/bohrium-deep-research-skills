# 复用指南：把本套规范与清单用于其他批量核验任务

本 Skill 的质控资产设计为可脱离评测环境独立复用。以下按场景说明。

## 1. 可复用资产清单

| 资产 | 路径 | 复用方式 |
|---|---|---|
| 标注规范 | `references/annotation-spec.md` | 直接拷贝进新项目；改动操作定义时请升版本号并记录变更 |
| 仲裁协议 | `references/adjudication-protocol.md` | 与 agreement.py/adjudicate.py 配套使用；保守默认表可按领域调整，但调整后必须同步改脚本中的 `PESSIMIZE` 映射 |
| 一致性度量 | `scripts/agreement.py` | 任意两个同格式标注 JSON 均可度量，不依赖本 Skill 其余部分 |
| 保守仲裁 | `scripts/adjudicate.py` | 同上；输出 adjudication-log.md 供归档 |
| 清单生成 | `scripts/checklist.py` | 任意 claims 列表 → 可勾选 CSV/Markdown |
| 标注模板 | `templates/annotation-pass.json` | 新标注员的记录格式约定 |

## 2. 典型复用流程（人工 + 脚本）

1. 准备 claims.json（字符串数组或对象数组均可）；
2. `python3 scripts/checklist.py claims.json -o checklist.csv --md checklist.md` 生成清单；
3. 两名标注员（或两个独立 Agent 通道）按 annotation-spec.md 各自标注，产出 passA.json / passB.json；
4. `python3 scripts/agreement.py passA.json passB.json -o agreement-report.json`；
5. `python3 scripts/adjudicate.py passA.json passB.json agreement-report.json -o adjudicated.json --log adjudication-log.md`；
6. 复核人只处理 needs_review=true 的条目，在清单 CSV 中填"复核人/复核日期"。

## 3. 批量引用检查场景（如学位论文/综述参考文献核验）

- 把每条"文内断言 + 所引文献"配对写成一条 claim；
- slots 建议改为：["被引文献是否含该断言", "页码/章节", "数值一致性"]，在 claims.json 的对象数组中逐条指定；
- 双通道可由"作者自查 + 同事互查"承担；kappa < 0.6 时应先统一对 annotation-spec.md 的理解再重标分歧高发类别，而不是强行仲裁。

## 4. 标注 JSON 格式契约（跨工具复用的唯一硬约束）

```json
[
  {
    "claim_id": "C1",
    "verdict": "supported",
    "evidence_pages": [3],
    "evidence_quote": "原文逐字引句",
    "rationale": "判定理由"
  }
]
```

- 硬约束字段：claim_id（唯一非空字符串）、verdict（四值之一）、evidence_pages（非负整数数组）；
- evidence_quote / rationale 可选，但缺失时仲裁日志中双方原话栏为空，削弱可审计性；
- 顶层可以是数组，也可以是含 `records` 数组的对象（脚本两种都接受）。

## 5. 退出码约定（脚本接入流水线时依赖）

| exit code | 含义 | 流水线动作 |
|---|---|---|
| 0 | 成功（含 kappa 低的质量警告，警告走 stderr） | 继续 |
| 1 | 输入 schema/数据错误（缺字段、非法 verdict、claim_id 不一致等） | 修正输入后重跑，不得跳过 |
| 2 | 命令行用法错误（argparse） | 检查参数 |

## 6. 常见问题

- **论断数太少（<3）**：kappa 统计意义不足，建议只做双通道 + 人工仲裁，报告中注明样本量；
- **多文档核验**：先把全部文档合并为带"文档ID:页码"复合定位的索引，evidence_pages 用整数时须保证单一文档；多文档建议扩展为字符串页标（需同步改脚本 schema 校验）；
- **判定体系不同**：若任务使用三值或五值判定，修改 agreement.py 的 VERDICTS 常量与 adjudicate.py 的 PESSIMIZE 表即可，其余逻辑通用。

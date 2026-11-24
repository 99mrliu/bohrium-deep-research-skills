# legal-status-license-governor

Bohrium Playground 挑战「专利与技术文献检索」（challenge-ad3e9357）Skill bundle：**合规与核验治理**。
核心能力：登记优先的法律状态核验协议（含查询日期与滞后声明、状态冲突处置）、数据源绿/黄/红授权分级与能力降级、结论措辞守门。

## 目录结构

```
SKILL.md                              # 技能主文档（用途/运行时契约/流水线/方法/路由/异常/自查）
README.md
GITHUB_URL.txt
scripts/
  status_ledger.py                    # 台账校验（规则 S1–S6，登记优先协议）
  license_tiers.py                    # 绿/黄/红分级 + 能力降级规划
  wording_guard.py                    # 结论措辞守门（未核验禁断言、禁 FTO/侵权结论）
  scaffold_result.py                  # result.json 骨架生成（骨架先行）
  selfcheck.py                        # 端到端自查（21 项断言）
references/
  legal_status_protocol.md            # 状态来源层级、滞后声明、冲突处置、措辞模板
  authorization_boundary.md           # 绿黄红定义、展示范围、留存、保密、禁止事项
examples/
  example_walkthrough.md              # 可复现命令 + 真实输出
  fixtures/                           # 合成示例/虚构 fixtures
```

## 快速开始

```bash
cd skill
python3 scripts/selfcheck.py          # 应输出 21 项 PASS，退出码 0
```

典型流水线（详见 `examples/example_walkthrough.md`）：

```bash
python3 scripts/scaffold_result.py --case case.json --out output
python3 scripts/license_tiers.py classify --sources sources.json --out license_report.json
python3 scripts/license_tiers.py plan --sources sources.json --out degradation_plan.json
python3 scripts/status_ledger.py validate --ledger status.jsonl --sources sources.json
python3 scripts/wording_guard.py --conclusions conclusions.md --ledger status.jsonl --sources sources.json --out wording_check.json
```

退出码约定：`0`=通过，`1`=治理违规，`2`=用法/输入错误。仅依赖 python3 标准库。

## 自查输出（真实运行，合成示例 fixtures）

```
PASS: status_ok.jsonl 校验通过（rc=0） — rc=0
PASS: status_ok.jsonl 无违规
PASS: status_bad_aggregator.jsonl 失败（rc=1） — rc=1
PASS: status_bad_aggregator.jsonl 命中 S1
PASS: status_bad_unknown.jsonl 失败（rc=1） — rc=1
PASS: status_bad_unknown.jsonl 命中 S2 与 S6 — rules=['S2', 'S6']
PASS: license classify 正常完成（rc=0） — rc=0
PASS: license 分级为 绿2/黄2/红1 — summary={'green': 2, 'yellow': 2, 'red': 1}
PASS: license plan 正常完成（rc=0） — rc=0
PASS: 降级规划非空且含红级 do_not_fetch
PASS: 能力降级 checklist 非空
PASS: conclusions_ok.md 通过措辞守门（rc=0） — rc=0
PASS: conclusions_bad_wording.md 被拦截（rc=1） — rc=1
PASS: 拦截报告含行号
PASS: 拦截覆盖确定性措辞与 FTO 两类 — kinds=['definitive_on_unverified', 'fto_out_of_scope']
PASS: 冲突用例不产生违规（rc=0） — rc=0
PASS: 冲突块已披露且双方保留
PASS: 头条状态由登记级来源胜出（granted） — headline={'status': 'granted', ...}
PASS: scaffold_result 正常完成（rc=0） — rc=0
PASS: result.json 镜像全部契约字段 — missing=[]
PASS: 骨架默认 status=partial 且 case_id 正确

自查合计: 21 项，通过 21，失败 0
全部断言通过。
```

仓库地址见 `GITHUB_URL.txt`。

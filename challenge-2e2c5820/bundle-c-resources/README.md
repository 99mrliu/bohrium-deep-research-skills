# Bundle C — 资源到位与契约排期核验（resource-readiness-contract-verifier）

Bohrium Playground 挑战 "实验方案可行性评估"（challenge-2e2c5820）的技能包。
重心：**资源是否到位、何时到位**——设备/物料/样本需求逐条与库存、供应商外协
合同、报价采购合同、预订日历、样本台账做确定性核验，杜绝"只评技术合理性，
不查资源到位"。

## 目录结构

```
outputs/
  SKILL.md                        技能定义（frontmatter + 工作流）
  README.md                       本文件
  GITHUB_URL.txt                  仓库地址
  scripts/
    inspect_case.py               case.json 结构探针（schema 无关，退出码 3 = 不可读）
    normalize_entities.py         实体名归一（别名表；未命中标记新实体，绝不静默合并）
    match_resources.py            四状态分类（已具备/可外协/需采购/不具备/无法核验）
    check_booking.py              预订区间重叠 + 采购货期核验（slack_days）
    check_samples.py              样本来源/数量/存储/伦理状态核验
    assemble_result.py            汇总为 result.json（契约字段齐全、不覆盖非 null 值）
  references/
    four_state_rules.md           五档分类定义、规格比较规则、平局裁决、gating 规则
    alias_table.json              起步别名表（extensible）
    requirements_schema.md        requirements.json 模式 + 抽取诚实规则
  examples/synthetic/             合成示例（非正式案例数据），可端到端运行
```

## 快速运行

```bash
bash examples/synthetic/run_example.sh   # 对 v1/v2/v3 跑全流程，产物在 examples/synthetic/output/
```

所有脚本仅依赖 Python 3 标准库、无网络访问、与 cwd 无关（脚本内用
`__file__` 定位 references）。用法错误以非零退出码 + stderr 信息退出。

## 运行时约定

技能安装于 `/skills/weekly-skill`，案例输入在 `/input/`，工作目录 `/app/work`，
结果写入 `/app/output/result.json`。详细工作流见 SKILL.md。

## 验证

合成示例预埋五类缺陷（规格不达标的 20000rpm 离心、Ni-NTA 货期缺口、纯化仪
预订重叠、血清 -20°C vs 需求 -80°C、伦理 pending），运行后可在
`examples/synthetic/output/` 的 match/booking/samples/result 各 JSON 中核对
均被捕获；另对缺失库存清单的 case 做过负向测试（全部无合同覆盖项 → 无法核验）。

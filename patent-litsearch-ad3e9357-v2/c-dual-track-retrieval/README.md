# dual-track-retrieval-lab

专利与技术文献**主题检索**的检索策略工程技能：可解释的概念块检索式构造（R1–R9 校验）、
专利/NPL 双轨执行与去重、PRISMA 风格筛选（计数一律脚本重算）、强制遗漏说明。

## 目录结构

```
SKILL.md                        # 技能主文档（运行时契约、管线、路由与异常表）
GITHUB_URL.txt                  # 仓库路径
scripts/
  query_build.py                # validate / render：概念块检索式校验与双轨渲染
  corpus_search.py              # run：本地语料双轨执行（file+line 定位、去重）
  prisma_screen.py              # screen / report：决策筛选与 PRISMA 计数重算
  scaffold_result.py            # result.json 骨架（先 partial 后填充）
  selfcheck.py                  # 端到端自查（22 项断言，全过才 exit 0）
references/
  query_construction.md         # 块设计、intent 语义、R1–R9 理由、双轨差异
  dual_track_screening.md       # 去重键、决策纪律、PRISMA 计数语义、遗漏说明
examples/
  example_walkthrough.md        # 真实命令 + 真实输出（示意输出·合成示例）
  fixtures/                     # 全部为合成示例/虚构数据
    case_fixture.json           # case_id = SYNTH-EXAMPLE-003
    query_spec_valid.json       # 合法 spec（3 块含分类块）
    query_spec_bad_bare_not.json    # 反面样例：R4 裸 NOT
    query_spec_bad_no_intent.json   # 反面样例：R2 缺 intent
    corpus/                     # 3 篇虚构专利 + 2 篇虚构论文（含同族对）
```

## 快速开始

```bash
cd <skill 根目录>
python3 scripts/selfcheck.py    # 先自查：22 项断言全 PASS、exit 0

# 最小管线（合成夹具）
python3 scripts/query_build.py validate --spec examples/fixtures/query_spec_valid.json
python3 scripts/query_build.py render --spec examples/fixtures/query_spec_valid.json \
    --track patent --out /tmp/q_patent.txt
python3 scripts/query_build.py render --spec examples/fixtures/query_spec_valid.json \
    --track npl --out /tmp/q_npl.txt   # stderr 输出"分类号已丢弃"NOTE（R5）
python3 scripts/corpus_search.py run --spec examples/fixtures/query_spec_valid.json \
    --roots examples/fixtures/corpus --out /tmp/hits.json
# …撰写 decisions.json 后：
python3 scripts/prisma_screen.py screen --hits /tmp/hits.json \
    --decisions /tmp/decisions.json --out /tmp/screened.json
python3 scripts/prisma_screen.py report --screened /tmp/screened.json --out /tmp/prisma.json
python3 scripts/scaffold_result.py --case examples/fixtures/case_fixture.json --out /tmp/out
```

退出码约定：`0` 成功；`2` spec/决策输入违规；`3` 计数一致性失败。
仅依赖 python3 标准库，无第三方包、无网络访问。

## 设计边界

本 bundle 只做**检索式构造、双轨执行、筛选与遗漏说明**；号码规范化引擎、
引文对账、法律状态/许可核查属于其他 bundle，不在此实现。

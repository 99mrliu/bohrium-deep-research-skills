# 运行记录（run-record）

本目录（`examples/synthetic-output/`）的全部 JSON/MD 产物均为**脚本真实运行**
的输出，非手工伪造。输入为 `examples/synthetic-input/` 下的**完全虚构**合成教学
数据（全部论文、DOI、数据库、引用图、import_state 均为虚构，DOI 形如
`10.99231/synth.*`），仅用于演示接口形态与缺陷捕获，**不是官方赛题答案**。

其中模型裁定步骤由人工以模型身份手写
`examples/synthetic-input/dispositions.json`（内容本身也是合成的示例裁定）。

## 实际执行的命令与真实退出码

工作目录 `/tmp`，Python 3（仅标准库），无网络：

```bash
# --help
python3 $BUNDLE/scripts/status_hygiene.py --help          # 退出码 0

# 端到端（含模型裁定文件）
python3 $BUNDLE/scripts/status_hygiene.py run-all \
  --input  $BUNDLE/examples/synthetic-input \
  --work   /tmp/sh_w1 \
  --output /tmp/sh_o1 \
  --dispositions $BUNDLE/examples/synthetic-input/dispositions.json
# 退出码 0；finalize 打印 status=partial（curator_comment 无法诚实填写，
# 置 null 并列入 unresolved_contract_fields），selfcheck 打印 ALL PASS。

# 幂等性：第二组全新 work/output 重跑
python3 $BUNDLE/scripts/status_hygiene.py run-all \
  --input  $BUNDLE/examples/synthetic-input \
  --work /tmp/sh_w2 --output /tmp/sh_o2 \
  --dispositions $BUNDLE/examples/synthetic-input/dispositions.json
# 退出码 0；五个产物 + 整个 work 目录与第一次逐字节一致（cmp/diff 验证）。

# 错误路径
python3 $BUNDLE/scripts/status_hygiene.py run-all --input <空目录> ...   # 退出码 3（缺 case.json）
python3 $BUNDLE/scripts/status_hygiene.py scan  --input <无材料的 case>  # 退出码 2

# 逐子命令链路（parse→scan→pair→reconcile→adjudicate→finalize→selfcheck）
# 各退出码 0，且 result.json 与 run-all 产物逐字节一致。
```

随后执行：

```bash
cp /tmp/sh_o1/{result.json,status_ledger.json,status_report.md,candidate_pool.json,version_pairs.json} \
   $BUNDLE/examples/synthetic-output/
```

## 产物要点（已人工核对）

- `crossref:10.99231/synth.002t`（被撤回的原文）与撤回通告
  `crossref:10.99231/synth.002` 均落入 **severe**，带证据定位符；
- preprint `synth.004` 与 VoR `synth.005` 经显式 `is-preprint-of`/`has-preprint`
  关系配为 **1 个显式版本对**，候选池中折叠为 1 项研究（VoR 优先，preprint 作
  `alternate_version`）；
- import_state 声称的 `10.99231/synth.404` 在所有响应中不存在 →
  **import_inconsistent** 被隔离并报告；
- import_state 标记 withdrawn 的 `10.99231/synth.pub3` 已从候选池排除；
- 出版商称 `published` 但引用图称 `withdrawn` 的 `synth.pub2` 被排除，
  冲突如实记录（STATUS_SOURCE_CONFLICT）；
- 无任何状态承载面的 `synth.001` 标 **status_unverifiable** 而非 clean，
  未入候选池。

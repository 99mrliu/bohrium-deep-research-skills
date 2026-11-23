---
name: obligation-ledger-coverage
description: 当输入含 comparison-workorder.json / case.json 与多篇论文语料时使用。把多文档比较工单编译成机器可核的"回答义务台账"（obligation ledger）：每个字段×论文单元格、六个维度的可比性判定、每条显式问题都是带唯一 obligation_id 与关闭判据的义务，只有状态机走到 closed 才算完成；交付前由脚本核算覆盖度并过交付门禁，专治多文档比较中最常见的失分——"漏答"。
---

# 义务台账式多文档比较（Obligation Ledger Coverage）

## 设计立场：先防漏答，再谈算对

多文档比较最常见的失分**不是算错，而是漏答**：工单问了 6 个维度 × N 篇论文，agent 凭印象交一张表，悄悄丢掉未报告字段和比较维度。本 Skill 的立场是：

1. **工单即合同**。`comparison-workorder.json` 不是阅读材料，而是必须逐条履约的义务清单。加载本 Skill 后的第一件事是把它**编译**成 `obligations.jsonl`：每个字段×论文单元格、每个维度×文档对的可比性判定、每条显式问题，都是一条带唯一 `obligation_id` 与关闭判据的义务。
2. **状态机不走到 closed 不算完成**。义务只有五种状态：`open` 与四种关闭态（`answered_with_evidence` / `not_reported_confirmed` / `conflict_preserved` / `out_of_scope`）。任何义务不得静默消失。
3. **未报告是合法结论，但要走流程**。`not_reported_confirmed` 必须声明"已检索相关段落无果"并附检索范围（`search_scope`），由脚本核对；这比硬编一个值诚实，也比留空可核。
4. **冲突保留，不得合并**。不同数据集、不同染料（如 RhB vs MB）、不同指标口径（去除率 vs 速率常数）一律判 `not_comparable` 并保留双方证据。
5. **比较矩阵是台账的渲染视图，不是手工产物**。`comparison-matrix.md` 由脚本从已关闭义务渲染，手工编的矩阵没有证据链。
6. **交付前过门禁**。`coverage.json` 给出 per-dimension / per-document 关闭率；任何 `open` 义务必须显式豁免或如实列入 `result.json` 的 `uncertainty`，否则 `contract_gate.py` 非零退出。

## 第 0 步：输入识别

评测时输入位于 `/input/`：

| 文件 | 说明 | 必需性 |
|---|---|---|
| `/input/case.json` | 案例元数据；**`case_id` 必须原样复制进 result.json**；`output_contract` 列出 result.json 必须包含的全部顶层字段 | 必需 |
| `/input/task.md` | 任务叙述（人读） | 必需 |
| `/input/comparison-workorder.json` | 组织方 v2 比较工单：文档清单、比较维度、字段、显式问题 | 必需（本 Skill 触发条件） |
| 语料文档 | 可能是真实 PDF，**无预提取答案层** | 必需 |

识别动作：
1. 读 `case.json`，记下 `case_id` 与 `output_contract`（字段名逐字照搬，不得改名/增删）。若 `case.json` 无 `output_contract`，退化为 `{case_id, status, 主结果, sources, uncertainty}`。
2. 读 `comparison-workorder.json`；schema 未知也没关系——`compile_obligations.py` 对 documents/dimensions/fields/questions 尝试多个常见键名，字符串或带 id 的对象均可。
3. 中间产物一律放 `/app/work`，最终交付放 `/app/output`。

## 工作流程（分阶段，含确切命令行）

以下以 `/app/work` 为工作目录。所有脚本仅依赖 python3 标准库，无网络。

### 阶段 1：语料抽取与段落索引

真实 PDF 无答案层，必须先建带 `paragraph_id` 的段落索引（quote 逐字核验依赖它）：

```bash
mkdir -p /app/work/corpus
# 对每篇 PDF（示例 doc id 为 DOC-01）：
pdftotext -layout /input/DOC-01.pdf /app/work/DOC-01.txt \
  || (pdftoppm -r 200 -png /input/DOC-01.pdf /app/work/DOC-01-page && echo "需 OCR：用可用 OCR 工具把 /app/work/DOC-01-page-*.png 转为 /app/work/DOC-01.txt")
# 切分为段落 jsonl（脚本见 references/closure-rules.md 第 7 节）：
python3 -c "
import json
paras=[p.strip() for p in open('/app/work/DOC-01.txt',encoding='utf-8').read().split('\n\n') if p.strip()]
open('/app/work/corpus/DOC-01.jsonl','w',encoding='utf-8').write(''.join(
  json.dumps({'document_id':'DOC-01','paragraph_id':'DOC-01-p%d'%i,'text':t},ensure_ascii=False)+'\n'
  for i,t in enumerate(paras,1)))
"
```

若语料已自带 paragraph_id 的 jsonl，直接复制进 `/app/work/corpus/`。

### 阶段 2：义务编译

```bash
python3 scripts/compile_obligations.py \
  --workorder /input/comparison-workorder.json \
  --case /input/case.json \
  --corpus /app/work/corpus \
  --out /app/work/obligations.jsonl
```

产出义务三类（详见 `references/obligation-schema.json`）：
- `FC-<字段>-<文档>`：工单字段 × 文档的每个单元格；
- `CMP-<维度>-<A>-vs-<B>`：维度 × 文档对。**v2 强制的六个维度（task / metric / units / material / pollutant / budget）的可比性判定本身就是六类义务，必须逐对论文关闭**——做完任何定量合成之前先关它们；
- `Q-<id>`：工单中的每条显式问题。

### 阶段 3：先交全覆盖骨架，再逐条关闭（预算策略）

预算只有 **64 次模型请求 / 900 秒**。纪律：

1. **骨架优先**：编译后立即通读台账，对每条义务先在心里定级（可答 / 需查 / 可能未报告），把最容易丢的（未报告字段、可比性义务）排在前面。
2. 把关闭结果写成 `/app/work/closures.jsonl`，每条一行（schema 见 `references/obligation-schema.json` 与下表），分批校验合并：

```bash
python3 scripts/close_obligations.py \
  --obligations /app/work/obligations.jsonl \
  --closures /app/work/closures.jsonl \
  --corpus /app/work/corpus \
  --out /app/work/obligations.jsonl   # 原地合并
```

| status | 何时用 | 必填 |
|---|---|---|
| `answered_with_evidence` | 找到取值 | `value`(+`unit`)、`source_document_id`、`paragraph_id`、`quote`（逐字，脚本核验） |
| `not_reported_confirmed` | 检索无果，确认未报告 | `search_scope`（已检索段落 id 列表）、`note` 说明检索范围与结论 |
| `conflict_preserved` | 两文档冲突/口径不一致 | 双方证据 `source_*` + `secondary_source_*`、冲突描述 |
| `out_of_scope` | 确属工单范围外 | `note` 说明理由 |

校验失败会逐条报错且**不写回**——修正后重跑即可；已合并的义务不会因后续批次失败而丢失。

### 阶段 4：覆盖度核算与渲染

```bash
python3 scripts/coverage.py --obligations /app/work/obligations.jsonl --out-dir /app/work
```

产出 `coverage.json`（总关闭率、per-dimension、per-document、open 清单）、`obligation-ledger.md`（义务×状态台账）、`comparison-matrix.md`（关闭义务的取值视图）。**有 open 义务时脚本会在 stderr 警告**——逐条决定：关闭它，或准备写入 uncertainty。

### 阶段 5：组装 result.json 并过门禁

`/app/output/result.json` 契约：

- `case_id`：从 `/input/case.json` **原样复制**；
- `output_contract` 中列出的**全部字段**（字段名原样照搬），逐字段填写或诚实标注 `not_reported` / `unavailable`；
- `status ∈ {success, partial, failed}`；`partial` 必须写明缺失边界；
- `sources`：文档/段落定位（`DOC-xx#DOC-xx-pN` 形式）；
- `uncertainty`：列出全部 open 义务（逐字 obligation_id）与其他不确定项；没有则给 `[]`。

```bash
python3 scripts/contract_gate.py \
  --result /app/output/result.json \
  --case /input/case.json \
  --obligations /app/work/obligations.jsonl
# GATE PASS（退出 0）才允许交付；GATE FAIL（退出 1）逐条修复后重跑
```

**随时可诚实 partial**：时间/预算将尽时，把未关闭义务保持 `open` 并逐条写进 `uncertainty`，交 `partial`——这比静默漏答得分高得多。

## 异常处理

| 异常 | 现象 | 处理 |
|---|---|---|
| workorder schema 不认识 | compile 找不到 documents/fields | 传 `--corpus` 让文档清单从语料文件名推断；fields 缺失时脚本只跳过 field_cell 并警告，维度默认取六维 |
| PDF 抽取失败 | pdftotext 输出为空/乱码 | 按阶段 1 的 pdftoppm 渲染 + OCR 路径；OCR 文本注意全半角与上下标（quote 逐字核验对字符敏感，OCR 后从索引文本里复制 quote，不要凭记忆写） |
| quote 核验失败 | close 报"quote 未逐字出现" | 从语料 jsonl 的 text 字段里**复制**引文，检查空格、破折号、单位写法 |
| not_reported 被拒 | close 报 search_scope 问题 | `search_scope` 必须是该义务管辖文档内**真实存在**的 paragraph_id 列表；`note` ≥10 字符说明检索范围 |
| 冲突义务只有单方证据 | close 报缺 secondary_* | `conflict_preserved` 强制双方证据，两组 quote 都要逐字核验 |
| 重复关闭 | close 警告"后写覆盖先写" | 确认后写的就是最终版本 |
| 门禁 FAIL：缺 contract 字段 | gate 列出缺失字段名 | 字段名从 `case.json` 的 `output_contract` 逐字照搬补齐；无法填的字段标 `not_reported`/`unavailable` 而不是省略 |
| 门禁 FAIL：open 未交代 | gate 列出 obligation_id | 要么回去关闭它，要么把该 id 写进 `uncertainty`（含原因） |
| 语料缺某文档 | compile 有义务但 corpus 无文件 | 该文档所有义务走 `not_reported_confirmed`（search_scope 给实际检索过的段落）或在 uncertainty 说明文档缺失 |
| 预算耗尽 | 时间/请求数告急 | 立即跑 coverage → 组装 partial result.json（uncertainty 列出全部 open）→ 过门禁交付 |

## 诚实性红线

- 不得编造取值、段落 id 或引文——quote 逐字核验会抓，但核验之外的内容（value 的解读）同样不许编；
- `not_reported` 是合法结论，但必须走 `not_reported_confirmed` 判据（检索范围声明）；
- 不得合并不同数据集或不同染料；不可比与未报告项必须保留在矩阵与台账中；
- 单篇摘要不满足多文档比较——每个字段义务按文档逐格关闭；
- 本 bundle 不含任何官方正式案例答案；examples/ 全部为虚构合成数据。

## 最小调用示例

`examples/` 含完整可运行的最小**合成**示例（三篇虚构光催化降解论文；声明：数据全部虚构，仅供演示）：

```bash
cd examples && bash run_example.sh
```

端到端跑 compile → close → coverage → 组装 result.json → contract_gate，产物写 `examples/output/`，预期 29 条义务全部关闭、`CMP-pollutant-DOC-01-vs-DOC-02` 判 `not_comparable`、门禁 `GATE PASS`。详见 `examples/README.md`。

## 文件索引

- `scripts/compile_obligations.py` — 工单 → obligations.jsonl（对未知 schema 健壮）
- `scripts/close_obligations.py` — 校验 closures.jsonl（schema + quote 逐字落地 + 状态判据）并合并
- `scripts/coverage.py` — coverage.json + obligation-ledger.md + comparison-matrix.md
- `scripts/contract_gate.py` — result.json 交付门禁（失败非零退出）
- `references/obligation-schema.json` — 义务与关闭记录的字段规范
- `references/closure-rules.md` — 各 status 判据、覆盖度指标定义、豁免规则、段落索引构建方法

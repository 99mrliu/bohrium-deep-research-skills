---
name: dr-replay-ledger
description: 深度研究文献综述的过程审计与复跑工程 Skill。重心：每一次检索/抓取工具调用逐笔记账（参数、返回计数、内容哈希、失败与重试），append-only 哈希链防事后改账，第三方可按 run journal 与 manifest 独立复跑整条研究路径，中断可按检查点恢复并发现产物被改。触发词：深度研究、文献综述、可复跑、运行日志、审计追踪、断点续跑、deep research、literature review、audit trail、replay、run journal、hash chain、resume checkpoint。
---

# dr-replay-ledger：可复跑深度研究的过程审计协议

本 Skill 把深度研究（deep research）文献综述的全过程变成**可审计、可复跑、可断点续跑**的账本。适用场景：评测输入为 `/input/case.json` + `/input/task.md` + 材料文件，工作目录 `/app/work`，最终产物写入 `/app/output`，其中 `result.json` 必须原样包含 `case_id` 与 `output_contract` 声明的全部字段，并诚实标注 `status` / `sources` / `uncertainty`。

## 核心原则

1. **逐笔记账**：每一次检索、抓取、解析、落盘动作都向 `run_journal.jsonl` append 一笔，含工具名、参数 JSON、返回条数、返回内容 SHA-256、四态状态（ok/failed/retry/empty）与备注。失败必须记 `note` 说明原因与降级决策；检索无结果记 `empty` 而非 `failed`。
2. **哈希链防改账**：每笔 `entry_digest = SHA256(prev_digest + canonical_json(哈希字段))`，任何事后篡改、删笔、插笔都会被 `journal.py verify` 检出（exit 1 并指出断链 seq）。
3. **确定性哈希**：`ts`（时间戳）记入账本但**不参与哈希**；`note` 参与哈希但措辞不影响其它字段。规范序列化固定为 `sort_keys=True, separators=(",",":"), ensure_ascii=False`。
4. **独立复跑**：`journal.py replay` 输出复跑清单，第三方按清单重放工具调用并比对 `results_digest` 与返回计数；`manifest.py` 固定输入/产物/skill 文件哈希，实现端到端复核。
5. **诚实 partial**：证据不足时 `status=partial`，并在 result.json 与 journal 中同时说明限度——日志即证据：已做哪些、卡在哪、降级决策是什么。

## 环境约定

- 仅 Python 3 标准库，无网络依赖。下文 `SKILL_DIR=${SKILL_DIR:-/skills/weekly-skill}`，`OUT=${OUT:-/app/output}`，`WORK=${WORK:-/app/work}`。
- 计算文件摘要示例用 `shasum -a 256 <file> | cut -d' ' -f1`；若环境无 `shasum`，等价替换为 `sha256sum <file> | cut -d' ' -f1` 或 `python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" <file>`。
- 所有产物 JSON 一律 `ensure_ascii=False, indent=2`。

## 五阶段流程协议

### 阶段 0：契约初始化（对应：证据回链 / 可靠交付）

读取 case 契约，初始化账本。`output_contract` 字段名因案例而异，**一律动态读取，禁止硬编码**：

```bash
python3 - <<'EOF'
import json, os, sys
with open("/input/case.json", encoding="utf-8") as f:
    case = json.load(f)
case_id = case.get("case_id") or case.get("id") or "unknown"
contract = case.get("output_contract") or case.get("contract") or {}
fields = list(contract.get("required_fields", contract.get("fields", [])) if isinstance(contract, dict) else [])
os.makedirs("/app/work", exist_ok=True); os.makedirs("/app/output", exist_ok=True)
with open("/app/work/contract.json", "w", encoding="utf-8") as f:
    json.dump({"case_id": case_id, "contract": contract, "fields": fields}, f, ensure_ascii=False, indent=2)
print("case_id:", case_id); print("required fields:", fields)
EOF

python3 "$SKILL_DIR/scripts/journal.py" init --journal "$WORK/run_journal.jsonl"
python3 "$SKILL_DIR/scripts/journal.py" append --journal "$WORK/run_journal.jsonl" \
  --tool read_case --args-json '{"path": "/input/case.json"}' \
  --results-count 1 --results-digest "$(shasum -a 256 /input/case.json | cut -d' ' -f1)" \
  --status ok --note "契约已动态读取，字段清单见 /app/work/contract.json"
```

### 阶段 1：问题拆解（对应六要点之"问题拆解"）

把研究问题拆为 3–7 个子问题，每个子问题标注：检索意图、预期证据类型、可接受的降级来源。拆解读 `/input/task.md` 与 case 材料，产出 `/app/work/subquestions.json`。此阶段为通用做法：拆解结果落盘后 mark-done：

```bash
python3 "$SKILL_DIR/scripts/resume.py" mark-done --stage decompose --out "$WORK" --file subquestions.json
```

### 阶段 2：检索执行（对应六要点之"检索覆盖"）

对每个子问题执行检索与抓取，**每次工具调用必须记账**，一笔一记：

```bash
# 检索命中（ok）：results-count 为返回条数，results-digest 为返回内容 SHA-256
python3 "$SKILL_DIR/scripts/journal.py" append --journal "$WORK/run_journal.jsonl" \
  --tool web_search \
  --args-json '{"query": "<子问题检索词>", "numResults": 8}' \
  --results-count <N> --results-digest <sha256-of-raw-results> \
  --status ok --note "覆盖子问题 SQ1"

# 检索为空（empty，不是 failed）
# --status empty --results-count 0 --note "该角度无公开证据，转为在 uncertainty 中声明"

# 工具报错（failed，note 必须记原因与降级决策）
# --status failed --note "fetch 限流 429；降级：改用摘要与元数据，标记来源等级下降"

# 同一动作重试（retry 与最终 ok 各自保留一笔，不得合并）
# --status retry --note "429 后退避 5s 重试"
```

检索矩阵至少覆盖：核心概念、方法学、反例/冲突证据、近年综述四个角度；中英文检索词并用。每完成一批检索立即 `journal.py verify` 一次（便宜且能尽早发现账本损坏）。

### 阶段 3：证据与综合（对应六要点之"证据回链 / 冲突证据 / 综合结论 / 研究空白"）

通用做法：为每条结论建立证据链 `结论 → 来源 → journal seq`，冲突证据单列并给出采信理由，研究空白单列。产出 `/app/work/synthesis.md` 后：

```bash
python3 "$SKILL_DIR/scripts/resume.py" mark-done --stage synthesis --out "$WORK" --file synthesis.md
```

### 阶段 4：交付门（写 result.json → 账本终检 → 清单 → 续跑自检）

```bash
# 1) 组装 result.json：case_id 原样回填；字段名从 /app/work/contract.json 动态读取后填值；
#    status ∈ {complete, partial, failed}，partial 必须在 uncertainty/限度字段说明边界；
#    sources 逐条给出可回链的引用，并附对应 journal seq。
python3 "$SKILL_DIR/scripts/journal.py" append --journal "$WORK/run_journal.jsonl" \
  --tool finalize --args-json '{"out": "/app/output/result.json"}' \
  --results-count 1 --results-digest "$(shasum -a 256 /app/output/result.json | cut -d' ' -f1)" \
  --status ok --note "按 output_contract 动态字段组装；status 与 uncertainty 已如实标注"
python3 "$SKILL_DIR/scripts/resume.py" mark-done --stage deliver --out "$WORK" --file ../output/result.json

# 2) 账本终检：必须 exit 0，否则修复账本前禁止交付
python3 "$SKILL_DIR/scripts/journal.py" verify --journal "$WORK/run_journal.jsonl"
python3 "$SKILL_DIR/scripts/journal.py" stats   --journal "$WORK/run_journal.jsonl"
python3 "$SKILL_DIR/scripts/journal.py" replay  --journal "$WORK/run_journal.jsonl" > /app/output/replay_plan.json

# 3) 运行清单 + 中断续跑自检（把账本一并纳入产物）
cp "$WORK/run_journal.jsonl" /app/output/run_journal.jsonl
python3 "$SKILL_DIR/scripts/manifest.py" build --input-dir /input --out /app/output --skill-dir "$SKILL_DIR"
python3 "$SKILL_DIR/scripts/manifest.py" verify --manifest /app/output/run_manifest.json
python3 "$SKILL_DIR/scripts/resume.py" verify-resume --out "$WORK"
```

以上任一步 exit 1 即交付门未通过：按 stdout 逐项失败清单修复后重跑，不得跳过。

## 六要点 → result.json 区块映射

| 六要点 | result.json 区块（字段名以 case 的 output_contract 为准，动态映射） |
|---|---|
| 问题拆解 | 拆解/子问题区块：子问题列表与检索意图（源自 subquestions.json） |
| 检索覆盖 | 覆盖区块：每子问题的检索角度、命中数（源自 `journal.py stats`） |
| 证据回链 | sources：每条来源含 journal seq，可经 replay_plan.json 复核 |
| 冲突证据 | 冲突区块：相互矛盾证据并列 + 采信理由 |
| 综合结论 | 结论区块：分确信度（strong/moderate/weak）的综合判断 |
| 研究空白 | uncertainty/空白区块：未覆盖角度、empty 检索角度、failed 降级影响 |

## 中断续跑

中断后重进环境：先 `resume.py status` 看已完成阶段，再 `resume.py verify-resume`（exit 0 说明已完成阶段产物未被改，可从下一阶段续跑；exit 1 点名须重跑的阶段）。随后 `journal.py verify` 确认账本完好，再继续记账，**禁止删除或重写既有账本行**。

## 参考文档

- `references/replay_protocol.md`：第三方复跑步骤、哈希链构造伪码、不参哈希字段说明、复跑差异处置。
- `references/failure_semantics.md`：ok/failed/retry/empty 四态语义与记账要求、partial 与日志的关系。
- `examples/`：合成示例（synthetic，无真实检索），`run_example.sh` 一键演示全部命令与埋雷变例。

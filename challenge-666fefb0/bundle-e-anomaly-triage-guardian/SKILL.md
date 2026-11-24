---
name: anomaly-triage-guardian
description: 科研资料库整理的"异常分诊与诚实降级"技能。当资料库混杂损坏 PDF、加密文件、无文本层扫描件、无权限文件、编码乱码、零字节文件、未知二进制，要求整理过程不中断、不静默丢弃、不粉饰状态时使用；重心在可靠性：每个文件先经 12 类分诊 taxonomy 判定（检测证据+处置+恢复建议），异常文件复制进 _quarantine/<类别>/ 原样保留而非丢弃或强改，健康文件正常归档；单文件异常永不阻塞全局，全部失败也产出诚实 partial result。输入只读、不删除。不负责单篇精读、全文翻译与文献检索发现。
---

# anomaly-triage-guardian：先分诊再动手，异常不阻塞、不静默、不粉饰

## 1. 核心思想

真实资料库整理的死法大多不是"分错类"，而是：一个损坏文件让整批任务崩溃、
一个无权限文件被静默跳过、扫描件被强行编出元数据。本 Skill 把**异常分诊与
诚实降级**作为第一性约束：

1. **先分诊后归档**：每个文件先过 12 类 taxonomy（见
   `references/triage_taxonomy.md`），拿到 `{triage_class, evidence, disposition,
   recovery}` 四元组才决定去向；`triage_report.md` 逐文件可复核。
2. **隔离而非丢弃**：异常文件复制进 `_quarantine/<类别>/` 并保留原始文件名，
   `quarantine_manifest.json` 登记 SHA-256 与恢复路径——资料零丢失，但也绝
   不混进整理好的目录冒充健康文件。
3. **永不阻塞**：每个文件的处理都在独立 try/except 中；意外异常降级为
   `processing_error` 继续跑；即使全部文件失败，也产出 `status="partial"`
   （或 `blocked`）的合法 result.json，写明限度。
4. **诚实状态机**：有 quarantine/skipped ⇒ `partial`；库不可读 ⇒ `blocked`；
   零异常且核验通过才是 `complete`。任何情况下不允许把 partial 写成 complete。

## 2. 适用边界

- 适用：含损坏/加密/扫描/无权限/乱码/零字节/未知二进制的混杂资料库整理；
  需要明确异常清单与恢复路径的交接场景。
- 不适用：OCR 与解密本身（只检测并给出恢复建议）；内容级版本裁决（交给
  专门技能）；精读、翻译、检索发现。

## 3. 运行时契约（Harbor）

- 安装路径 `/skills/weekly-skill`；脚本 `python3 /skills/weekly-skill/scripts/xxx.py`。
- 输入 `/input/case.json`、`/input/task.md` 与材料目录；防御式解析见
  `references/case_contract.md`。
- 工作目录 `/app/work`；交付 `/app/output/`：`result.json`（含原 `case_id` 与
  `output_contract` 全部字段、诚实 status）、`library/`（含 `_quarantine/`）、
  `triage_report.md`、`quarantine_manifest.json`、`operations.jsonl`。
- status 状态机：`complete`（零异常且 verify 通过）/ `partial`（有任何
  quarantine/skipped，限度必写）/ `blocked`（库不可读）。
- 依赖：Python 3 标准库；`pdftotext` 缺失本身即一类分诊（`extract_unavailable`）。
- 预算：脚本零模型请求；模型 0–1 次（检索回答）。第一步永远是 init。

## 4. 工作流程

设 `S=/skills/weekly-skill/scripts`。

### 第 1 步：盘点 + 分诊（脚本，0 次模型请求）

```bash
python3 $S/run_case.py init --input /input --work /app/work --out /app/output
```

产出 `triage.jsonl`（逐文件分诊）、`triage_report.md`（人读分诊报告）、
保底 partial result.json。

### 第 2 步：模型检索回答（0–1 次模型请求，可省）

case 含检索问题时写 `/app/work/answers.json`：`{"answers": [{qid, answer,
evidence}]}`；evidence 指向 triage.jsonl / aliases.json 的具体记录。

### 第 3 步：归档 + 隔离 + 交付（脚本，0 次模型请求）

```bash
python3 $S/run_case.py finalize --work /app/work --out /app/output
```

健康文件按 类型/年份 归档（确定性命名）；重复件入 `_archive_dups/`；异常件入
`_quarantine/<类别>/`；写 `quarantine_manifest.json`、`operations.jsonl`、
`verify_report.json` 与终版 `result.json`（skipped 逐条含 triage_class、
检测证据、恢复建议、preserved_at）。幂等重跑。

## 5. 分诊 taxonomy 速览（全文见 references/triage_taxonomy.md）

`ok` / `duplicate_bytes` / `sidecar` / `encrypted_pdf` / `corrupt_pdf` /
`no_text_layer` / `permission_denied` / `read_error` / `empty_file` /
`garbled_encoding` / `unknown_binary` / `extract_unavailable`
（运行时意外追加 `processing_error`）。

## 6. 最小调用示例（合成示例）

```bash
cd examples && python3 make_fixture.py && bash run_example.sh
```

夹具 16 个文件覆盖 8 类异常（损坏、加密、无文本层、无权限、零字节、乱码、
两组重复）；输出摘录见 `sample_output.md`。**合成示例，非正式案例结果。**

## 7. 自查清单

- [ ] triage.jsonl 行数 == 输入文件数（无一遗漏）。
- [ ] _quarantine/ 下文件与 quarantine_manifest.json 一一对应，SHA-256 可核。
- [ ] 全部 skipped 条目含 recovery；result.json status 与 skipped 一致。
- [ ] 构造全失败输入重跑：仍产出合法 partial/blocked result.json。

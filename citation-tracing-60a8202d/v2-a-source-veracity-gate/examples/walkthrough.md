# 合成示例运行说明（SYNTHETIC / 合成示例，非真实文献、非正式案例结果）

> **声明**：本示例中全部文献、作者、期刊与 DOI（形如 `10.0000/synth.*`）均为虚构，
> 仅用于演示 source-veracity-gate 的审计与门控能力。`run_out/` 下的产物是这些
> **合成输入的真实运行产物**（作者在本机 macOS 上用 Python 3 标准库真实执行三条
> 脚本生成），属于示意输出，不冒充平台正式案例结果。

## 示例输入

| 文件 | 内容 |
|---|---|
| `corpus/crossref_batch1.json` | Crossref 风格 `message.items`：种子 A（synth.001，引用 B 与语料外的 synth.999）＋B（synth.002） |
| `corpus/crossref_batch2.json` | Crossref 风格单条 `message`：C（synth.003，引用 A） |
| `corpus/europepmc_batch1.json` | EuropePMC 风格 `resultList.result`：D（synth.004，引用 A 与 B）＋**冲突记录**（DOI 同为 synth.001 但标题不同） |
| `corpus/broken_response.json` | **故意损坏**的 JSON（截断），用于演示"登记而非中断" |
| `case.json` | 合成案例：`seed_paper` 指向 synth.001；`output_contract` 含 11 个字段，其中 `novelty_statement` 故意未定义语义，用于演示诚实空值 |
| `task.md` | 合成任务说明（文本中亦含种子 DOI，可测试正则兜底） |

## 运行命令（与 SKILL.md 相同的三步顺序）

```bash
cd v2-a-source-veracity-gate

python3 scripts/source_audit.py \
    --roots examples/corpus --workdir examples/run_out/work
# 实际输出：{"files_total": 4, "files_parsed_ok": 3, "parse_coverage": 0.75,
#           "records_total": 5, "conflicts": 1, ...}；退出码 0

python3 scripts/build_result.py \
    --case examples/case.json --task examples/task.md \
    --out examples/run_out --workdir examples/run_out/work
# 实际输出：{"case_id": "SYNTH-CASE-001", "status": "partial",
#           "candidates": 3, "edges": 9, "uncertainty": 7, ...}；退出码 0

python3 scripts/selfcheck.py \
    --out examples/run_out --case examples/case.json
# 实际输出：{"ok": true, "defects": [], "defect_count": 0} 与 ok=true；退出码 0
```

## 预期（并已验证的）输出要点

1. **损坏文件被登记而非中断**：`work/audit_report.md` 与
   `work/source_registry.json` 中 `broken_response.json` 记为
   `status=failed`（含 JSONDecodeError 原因），其余 3 个文件正常解析，
   解析覆盖率 75%。
2. **冲突对被检出**：审计台账检出"同 DOI 不同标题"：
   `10.0000/synth.001` ↔ 两个不同标题（crossref_batch1 与 europepmc_batch1
   各一条，均带定位）；构建阶段合并这两条记录并在 `uncertainty` 保留
   title/venue 的冲突多值。
3. **locator 门禁**：全部候选与边都带 `{file, pointer}`；门禁逻辑另经专项
   测试验证（人为移除某记录 locator 后，该记录被拦截并写入 `omissions`，
   不得进入 candidates）。
4. **stub 诚实保留**：种子引用的 `10.0000/synth.999` 在语料内无记录，
   保留为 stub（只带原始指针与首次出现定位），不补造元数据。
5. **output_contract 全字段镜像**：`run_out/result.json` 顶层含 contract
   全部 11 个 key；未知语义的 `novelty_statement` 诚实置 `null` 并在
   `uncertainty` 注明；`output_contract_mirrored` 列出已镜像字段。
6. **诚实 status**：因存在损坏文件、合并冲突与 stub，`status` 为
   `partial`（真实性瑕疵降级），逐条降级依据见 `uncertainty`。
7. **方向语义**：`edges` 中 reference 边 `direction_restored=false`，
   由参考文献列表反向索引恢复的前向 citation 边 `direction_restored=true`。

## run_out/ 产物清单（合成示例的真实运行产物）

| 文件 | 说明 |
|---|---|
| `run_out/work/records_norm.jsonl` | 5 条规范化文献记录，每条带 locator |
| `run_out/work/source_registry.json` | 4 个文件的来源注册表＋冲突台账 |
| `run_out/work/audit_report.md` | 人读审计报告（覆盖率、格式分布、逐文件登记、冲突线索） |
| `run_out/result.json` | 最终结果（status=partial，3 候选、9 边、1 stub、contract 全镜像） |
| `run_out/provenance_report.md` | 人读溯源报告（种子、候选表、边表、不确定性） |
| `run_out/selfcheck_output.txt` | selfcheck 输出留档（ok=true，退出码 0） |

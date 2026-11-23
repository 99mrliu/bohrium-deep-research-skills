# 可复现性（reproducibility）

## 确定性保证

同一输入重复运行，全部输出**逐字节一致**。机制：

1. **ID 是内容的哈希**（见 version-model.md），与运行次数、候选书写顺序无关
   （建图前按"来源次序 → 段落 ID → 规范化标签"确定性排序）。
2. **无时间戳、无随机数、无环境依赖**：所有脚本只读输入文件，输出不含
   日期、主机名、绝对路径。
3. **JSON 一律 `sort_keys=True` + UTF-8 + 固定缩进**；JSONL 每行一条、键有序。
4. **幂等应用**：同锚点记录再次出现时复用原 ID 并跳过（changes.json 记
   "幂等跳过"），重复应用同一变更集不产生重复节点/边。
5. **SVG/DOT 预览**由图内容确定性生成（节点按 ID 排序、圆周布局），同样是
   纯文本、可 diff。

## 实测证据（负向测试，`examples/synthetic/tests/negative_tests.sh`）

- T1：同一合成输入完整跑两遍，`diff -r` 两个输出目录**零差异**；
  并断言 current 图无重复节点/边 ID。
- T2：MERGE 与 KEEP_DISTINCT 之后，baseline 全部节点/边 ID 在 current 中
  原样保留（`ids1 ⊆ ids2` 且被合并节点 ID 相同）。
- T4：apply 前后 `graph-v1.json` 的 MD5 不变（封存基线不被改写）；
  冲突双方并存、均属同一 `conflict_group`、158 与 149 两条数值边分存。

在本仓库中可直接复现：

```bash
bash examples/synthetic/run_synthetic.sh            # 一键跑通全流程
bash examples/synthetic/tests/negative_tests.sh     # 6 项断言全 PASS
```

## 运行时分工（Agent × 确定性工具）

- **Agent（模型）**：阅读论文，编写语义候选与变更集（选择实体、关系、操作与
  理由），编写查询清单。这是唯一的"语义判断"环节。
- **工具（stdlib 脚本）**：证据逐字校验、ID 分配、封存、变更应用、差异、
  查询执行、装配。全部确定性、无模型调用，可被任何人重跑复核。

因此复核者无需信任模型：只要重跑工具链 + 抽查 quote 是否逐字命中段落，
即可独立验证图谱的每一条记录。

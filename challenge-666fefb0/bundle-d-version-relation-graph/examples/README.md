# 最小调用示例（合成示例）

**声明：本示例为合成示例。** 夹具文件、裁决与输出均为演示数据，不对应真实文献，
也不是平台正式案例结果。

## 运行

```bash
cd examples
python3 make_fixture.py     # 生成合成夹具 fixture/input（13 个文件）
bash run_example.sh         # init -> graph -> 预写裁决 -> finalize
```

## 观察点

1. `graph` 步骤零模型请求构建 typed-edge 图谱：应发现
   - C1 簇：预印本(F004) + 正式版(F002) + 补充材料(F003)，`version_of` 与
     `supplement_of` 边各带信号与证据（标题相似、arXiv 共享、管理员说明行号）；
   - 两个 `duplicate_of` 簇（SHA-256 相等）；
   - 损坏/无文本层/无权限文件以"内容不可用"单节点簇入图。
2. canonical 仲裁：C1 由管理员说明指定 F002；纯 duplicate 簇保留最小 fid；
   `arbitration_log.json` 含每个簇的完整打分轨迹。
3. `finalize`：同题异版全部保留，重复件进 `_archive_dups/`；终版
   `version_graph.json`、`graph.md`（人读邻接表+边证据）与 result.json 的
   `version_relations` 一一对应。

实际运行输出摘录见 `sample_output.md`。

# 可复跑协议：run log → manifest → fresh/stale 核验

（result-contract-replay-compiler 参考文档 · 复跑协议）

## 1. 设计目标

让任何第三方**仅凭记录**（run_log.jsonl / replay_manifest.json + 文件哈希）即可判断：
(a) 每一步用了什么命令、读了哪些文件、产出了哪些文件；
(b) 这些文件当前是否仍与记录时一致（能否原样复跑）；
(c) 复跑环境要点（Python 版本、平台、路径约定）。

## 2. run log 格式（run_log.jsonl）

每行一个 JSON 对象，对应一次 `replay_pack.py log` 调用，字段：

| 字段 | 含义 |
| --- | --- |
| `step` | 步骤序号（追加时按现有行数自动编号，从 1 起） |
| `ts` | UTC 时间戳（ISO8601，秒级） |
| `cmd` | 实际执行的命令行（如实记录，含参数） |
| `workdir` | 记录时的工作目录（绝对路径） |
| `inputs` | `[{"path": ..., "sha256": ...}]`——命令读取的文件 |
| `outputs` | `[{"path": ..., "sha256": ...}]`——命令产出的文件 |

纪律：
- **先执行、后立即 log**：哈希必须反映命令真实读写的文件内容。
- 输入文件缺失时 log 拒绝记录（exit 2）——不存在的输入无法复跑，不能入册。
- 输出文件暂时缺失时记 `sha256: null` 并警告（例如命令以 stdout 为主产物）。
- 路径建议用绝对路径，或全部相对同一 workdir 并在 cmd 中保持一致。

## 3. manifest 结构（replay_manifest.json）

```json
{
  "manifest_version": 1,
  "generated_at": "<UTC ISO8601>",
  "environment": {
    "python": "3.12.x",
    "platform": "…",
    "note": "路径按记录时的工作目录写入；第三方复跑前请将各 path 还原到等价位置，或以 verify 确认文件哈希一致后再按 cmd 顺序重放。"
  },
  "steps": [ /* run log 中的有序步骤，原样固化 */ ]
}
```

`pack` 只是把 run log 固化为带环境说明的快照，不重哈希、不改写步骤。

## 4. fresh / stale / missing-input 定义

`verify` 对每一步重新哈希其引用的全部文件：

| 状态 | 定义 | 语义 |
| --- | --- | --- |
| `fresh` | 所有输入与输出文件的当前 SHA-256 均与记录一致 | 步骤可原样复跑，重放应得同样结果 |
| `stale` | 至少一个文件哈希不符（输入或输出），但输入仍在 | 文件已被改动；重放可能得不同结果——如实标注，不算失败 |
| `missing-input` | 至少一个输入文件不存在 | 该步骤无法复跑；verify 以 exit 1 报告 |

退出码约定：任一步骤 `missing-input` → exit 1；否则 exit 0（stale 仅如实报告）。这与"诚实标注优先于表面全绿"的原则一致。

## 5. 第三方复跑指引

1. 取得 `replay_manifest.json` 与其引用的全部文件，放到与记录等价的位置（保持相对关系即可）。
2. 运行 `python3 scripts/replay_pack.py verify --manifest replay_manifest.json`：
   - 全部 `fresh`：环境等价，按 `steps` 顺序重放 `cmd` 即可复现；
   - 存在 `stale`：对照哈希不符的文件，确认改动来源后再决定是否重放；
   - 存在 `missing-input`：补齐输入文件，否则该步骤不可复跑。
3. 重放后再次 `log` 新步骤并 `pack` 新 manifest，形成可追溯的复跑链条。

## 6. 局限（如实声明）

- 哈希只证明文件内容未变，不证明命令执行结果的业务正确性。
- 外部环境依赖（联网检索结果、数据库快照）不在哈希覆盖范围内；此类步骤应在 `cmd` 或结果 `sources` 中记录版本/日期，供人工判断。

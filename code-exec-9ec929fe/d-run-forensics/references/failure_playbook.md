# 失败处置 playbook（run-forensics）

## 总则

1. 失败不是麻烦，是证据。每次非零退出都已带现场入台账（runs.jsonl），
   禁止删除或改写台账。
2. 定位根因 → 同 tag 重跑，形成重试链。复核者看重试链判断你的调试质量。
3. 同一失败分类连续出现 2 次：停止重试，把现象、已排除原因、假设写入
   anomalies，转为 partial 或人工确认。

## 分类处置表

| 分类 | 典型 stderr 特征 | 处置路径 |
|-|-|-|
| 依赖缺失 | ModuleNotFoundError | 首选改标准库实现；必须第三方库时在 provenance 记录名称与版本，并写降级说明 |
| 路径错误 | FileNotFoundError | `ls` 核对真实文件名；一律绝对路径；不猜、不硬编码本机路径 |
| 权限不足 | PermissionError | 输入目录只读：复制到 /app/work 再处理；不就地改输入 |
| 编码问题 | UnicodeDecodeError | utf-8-sig → utf-8 → gb18030 顺序探测；实际编码记入 anomalies |
| 字段名不符 | KeyError | 先打印真实表头；写显式 rename 映射；禁止按列位置取列 |
| 表名错误 | no such table | `SELECT name FROM sqlite_master WHERE type='table'` 核对 |
| 列名错误 | no such column | `PRAGMA table_info(表名)` 核对 |
| 内存不足 | MemoryError | 分块/流式；先小样本验证逻辑；数据规模记入 provenance |
| 超时 | Timeout | 小切片验证逻辑后再全量；记录数据量与耗时 |
| 查询为空 | （exit 0 但 0 行） | 不是错误但必须核对：表名、JOIN 键、WHERE 各条件逐一注释排除 |

## 重试链阅读示例

```
`sql1`: 退出码序列 [1, 0]   —— 第一次表名错误，核对 sqlite_master 后修复
`figure`: 退出码序列 [1, 1] —— 两次依赖缺失，未解决 → 必须出现在
                               provenance.unresolved_failures 与 missing_fields
```

## 交付前自查

- runs.jsonl 覆盖了从读数到出图的全部步骤？（缺一步 = 有一段过程不可复核）
- 每个 tag 最后一次执行 exit=0？否则 missing_fields 是否解释了它？
- replay.sh 在干净目录能重放成功命令？（seal 之前手工抽一条验证）
- provenance.input_manifest 的哈希与 /input 当前文件一致？

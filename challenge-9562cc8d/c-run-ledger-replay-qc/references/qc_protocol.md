# 过程质量控制协议

## 三道防线

1. **检查点**：`result.json` 自流水线初始化即存在（合法 partial，
   含 `case_id` 与 `output_contract` 全部字段），每个阶段原地更新。
   崩溃/超时/预算耗尽时，平台上留下的是已完成的全部产物与准确的
   进度状态，而不是空目录或假 success。
2. **运行台账**（`ledger.json`）：
   - `stages[]`：每次状态更新的 {序号, status, 摘要, 当时产物清单}；
   - `artifacts[]`：全部输出文件的 {文件名, 字节数, SHA-256}；
   - 配合 `run_manifest.json`（Python/matplotlib/numpy 版本、随机
     种子、源文件 SHA-256、主数据文件判定）。
3. **复跑证明**（`replay_report.json`）：流水线在隔离目录完整复跑
   一遍并逐文件比对（见 rerun_guide.md）。

## 随机源管理

- 全流程唯一随机源：散点抖动与 n>300 抽样的 numpy Generator，
  种子固定 `20240501`，写入 `run_manifest.json`；
- 直方图分箱、统计计算、面板排序全部确定；
- 若复跑发现文本产物不一致，说明存在未声明的随机源——这是质量
  事故，`status` 降 `partial` 并在 `uncertainty` 中定位文件。

## 异常登记纪律

| 情况 | 登记位置 | 状态影响 |
|---|---|---|
| 缺失值 | cleaning_report 逐列计数；captions 说明未插补 | 不影响 success |
| 重复行 | cleaning_report 计数并标记 | 不影响 success |
| IQR 异常值 | 逐列围栏与标记数 | 不影响 success |
| CSV↔SQLite 不一致 | reconciliation.json + uncertainty | 降 partial |
| 图件生成失败 | uncertainty（哪张图、什么异常） | 降 partial |
| 复算不一致 | check_report.json + uncertainty | 降 partial |
| 复跑不一致 | replay_report.json + uncertainty | 降 partial |
| 无 CJK 字体 | run_manifest + uncertainty | 不影响 success（英文标注回退） |

## 静默行为黑名单（绝不允许）

- 插补缺失值而不声明；
- 删除重复行/离群点而不记录数量；
- 多源数据不一致时静默选一个；
- 图件失败后把上一次运行的旧图留在输出目录冒充本次产物
  （输出目录由调用方指定，流水线不主动清空，但 figdata 只登记本次
  成功写出的文件，复算校验只针对登记文件）。

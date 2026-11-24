# 失败分类与处置对照

| 类别 | 识别 | 处置 |
|-|-|-|
| 输入理解错误 | 阶段 exit≠0，stderr 为解析/编码/KeyError | 修正解析逻辑后重跑；不手算替代 |
| 材料缺失 | hash_path 返回 MISSING / 文件不存在 | checkpoint --status partial --limitation 精确点名；进下一阶段 |
| 超时 | exit=124 | 缩小该阶段范围（抽样/分片），在 change_records 记录取舍 |
| 预算耗尽 | budget report usage>0.8 | 立即收尾，现状落盘，partial + limitations |
| 结论冲突 | 两阶段输出互相矛盾 | 不得二选一静默采用；两条都写进 uncertainty，结论降级 |
| 环境缺工具 | command not found | 换 stdlib 等价实现；在 sources 登记替代方法 |

通用禁令：
- 禁止删除 manifest 或 work 目录来「让失败消失」；
- 禁止把未运行的阶段写成已完成；
- 失败后重跑次数 >2 次仍失败 → 停止该策略，降级为 partial 并说明，不无限重试。

# change record（变更对账记录，序号为单调序号，不含时间戳）

- seq 1 | status: partial | artifacts: - | uncertainty: +0/-0 | note: checkpoint: 请求 success 被拒绝——契约字段仍为占位: mindmap_file, evidence_map；状态保持 partial | 过早请求 success（守卫测试）
- seq 2 | status: partial | artifacts: +mindmap_file +evidence_map | uncertainty: +1/-0 | note: 拒绝写入未知字段 bogus_field | build 完成：登记导图与证据映射
- seq 3 | status: success | artifacts: - | uncertainty: +0/-1 | note: 不确定性经复核为可接受的合成示例限制，予以消解；全部契约字段已填

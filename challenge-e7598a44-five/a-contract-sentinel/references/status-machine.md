# 诚实状态机：complete / partial / blocked

状态是给复核者的承诺，不是给自己打分。判据如下（按优先级）：

## blocked — 无法开始或主体缺失

满足任一：
- case.json 缺失或损坏，无法确定契约；
- 输入目录不存在或解析后**零记录**；
- 管线中断，result.json 只能交付 probe 骨架。

承诺含义：本次没有可用结果，已完成的只有输入清点与问题定位。
`uncertainty` 必须逐条说明缺什么文件、哪一步中断。

## partial — 有结果，但有已声明的保留

满足任一（且不满足 blocked）：
- 任一输入文件解析失败（其余已完成）；
- 署名清单中有 missing/ambiguous 或元数据不一致；
- 存在 `disposition=uncertain` 的记录待人工复核；
- 登记了未裁决的冲突证据（如 conflict_opinion 夹具记录）；
- 任一契约字段留空。

承诺含义：列出的保留项之外的部分是完整可信的；保留项本身也如实列出，
复核者可以只针对保留项继续工作。**partial 是体面且常见的终态。**

## complete — 无保留

仅当：全部文件解析成功、清单全部 matched 且无元数据差异、无 uncertain 记录、
无未裁决冲突、无空契约字段。门禁 C5 强制：complete 时 uncertainty 必为空，
虚报 complete 会被门禁直接打回。

## 为什么不允许第四种状态

"running / unknown / success"这类状态会把举证责任推给复核者。三值状态机的
每一分岔都对应一份可检查的产物（failures 列表、missing 清单、uncertain 台账），
状态永远可以从产物复算，而不是从记忆声明。

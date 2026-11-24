# 三类固定案例的复算落点

1. **弯曲 traces**：逐 trace 跑 `fit`（slope 对应线弹性段模量代理、auc 对应吸收能代理）
   与 `series`（峰值 max/argmax）；197 条全量跑约秒级，无需抽样。
   claims 重点：群体峰值均值、离群 trace 的峰值。
2. **Iris 5×2**：split×estimator 矩阵只有 10 个数——逐 estimator 列跑 `series`，
   claims 重点：两 estimator 的 mean 差、各 split 差值。注意 rel_tol 对接近 1.0
   的准确率要按差值（0-1 尺度）而非比值设定。
3. **Cefixime 工作簿**：xlsx 需先转成文本列（用 zipfile+xml 或 LibreOffice 导出
   csv 均可，转换命令写入 change_records）；claims 重点：论文正文引用的关键
   含量/释放度数值与工作簿是否一致（TOLERANCE_MISS 在这里是重要发现而非错误）。

通用：任何「论文/材料里给出的数」都可登记为 claim（source_file 指向提取出的
文本），复算值来自原始数据——这正是「结果可核验性」评分点的直接证据。

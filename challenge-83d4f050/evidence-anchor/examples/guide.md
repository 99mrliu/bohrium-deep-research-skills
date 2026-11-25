# SYNTHETIC 合成示例

从本 bundle 根目录运行 `bash examples/run_demo.sh`。产物写入独立的 `../validation/evidence-anchor/`（不随技能提交）。主流程真实执行证据引文回查、SVG 生成、PyMuPDF 导出 PNG/PDF、结果组装；附加命令演示源 SVG 不变的结构化修改。

此通路、引文和 case_id 全部合成，不能用于正式案例。主流程成功返回 0；预期失败测试把引文改为不存在的句子时必须返回 2。

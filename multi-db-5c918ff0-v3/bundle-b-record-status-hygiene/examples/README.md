# 合成示例声明

`examples/` 目录为**完全虚构**的合成教学数据：

- 全部论文、作者、期刊、DOI（形如 `10.99231/synth.*`）、数据库响应、
  引用图与 import_state 均为虚构，不指向任何真实文献或真实撤回事件；
- 用途仅为演示 `record-status-hygiene` 技能的接口形态、信号提取、版本归并
  与 import_state 对账行为，**不是官方赛题答案**，也不应被当作任何真实
  数据库的响应样本；
- `synthetic-input/dispositions.json` 是以模型身份手写的示例裁定文件，
  内容同样虚构；
- `synthetic-output/` 为脚本对该合成输入**真实运行**的产物（非手工编造），
  复现命令与真实退出码见 `synthetic-output/run-record.md`。

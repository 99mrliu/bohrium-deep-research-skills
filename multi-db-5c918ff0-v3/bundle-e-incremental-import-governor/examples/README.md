# 合成示例声明

`examples/` 下全部数据均为**虚构的合成教学数据**,仅用于演示与测试本
技能的增量导入治理流程:

- `case_id: "synthetic-import-gov-001"`;
- 全部 DOI 使用虚构号段 `10.99988/...`,PMID(`390000xx`)、作者、期刊名
  (Journal of Synthetic Adhesion 等)、出版方记录号(`pub:JBA-1042`)
  均为虚构,**不对应任何真实文献**;
- `synthetic-input/materials/import_state.json` 是虚构的"上一轮导入状态"
  (方言 a),其 `content_hash` 由本技能脚本自身的指纹函数算出,以保证
  7 条 unchanged 记录指纹必然一致;
- publisher 材料**有意缺席**,用于同时演练水印 HELD 路径与
  `unverifiable_withdrawal` 路径;
- `synthetic-output/` 是用本 bundle 脚本**真实运行**得到的产物
  (`work/change_dispositions.json` 为手工编写,模拟工作流第 5 步的
  模型单次批量处置);复现命令、退出码与确定性验证见
  `synthetic-output/run-record.md`。

预期分类(工程化真值):7 unchanged / 1 changed(year、venue 两字段
before→after)/ 2 new / 1 withdrawn(europepmc 在场而记录消失)/
1 unverifiable_withdrawal(publisher 缺席)/ 1 inconsistent_state
(状态行 identifier 与 fields.doi 冲突);标识符并集 13。

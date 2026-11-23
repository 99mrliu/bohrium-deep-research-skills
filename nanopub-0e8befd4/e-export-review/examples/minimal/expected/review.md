# 人工复核单（claims review）

- case_id: `synthetic-cryomesh`
- 来源: CryoMesh: a low-cost mesh sensor network for vaccine cold-chain transport（fictional-2024-cryomesh）
- 断言总数: 20；逐条勾核后可回填 verdict 列。

## status = asserted（17 条）

### E-01  CryoMesh is a low-cost mesh sensor network for vaccine cold-chain transport.

- 三元组: (CryoMesh) —[has_property]→ (low-cost mesh sensor network for vaccine cold-chain transport)；polarity=positive；modality=asserted
- 证据（direct）: 「CryoMesh is a low-cost mesh sensor network for vaccine cold-chain transport.」 @ {"page": 1, "part": "Abstract"}
- 置信度: high — 定义句逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-02  A CryoMesh node costs 11.40 USD at 1000-unit volume.

- 三元组: (CryoMesh node) —[has_value]→ (11.40 USD per node)；polarity=positive；modality=asserted
- 限定: volume: 1000 units
- 证据（direct）: 「unit cost is 11.40 USD at 1000-unit volume」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 价格与量级逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-03  CryoMesh nodes communicate over a 2.4 GHz mesh radio.

- 三元组: (CryoMesh nodes) —[uses]→ (2.4 GHz mesh radio)；polarity=positive；modality=asserted
- 证据（direct）: 「nodes communicate over a 2.4 GHz mesh radio」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 通信制式逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-04  CryoMesh indoor radio range is 35 m.

- 三元组: (CryoMesh radio range) —[has_value]→ (35 m)；polarity=positive；modality=asserted
- 限定: environment: indoors
- 证据（direct）: 「indoor range of 35 m」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 距离与环境限定逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-05  A CryoMesh node runs 14 days on a CR2032 cell.

- 三元组: (CryoMesh node) —[has_value]→ (14 days battery life on CR2032)；polarity=positive；modality=asserted
- 证据（direct）: 「14 days on a CR2032 cell」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 电池型号与时长逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-06  CryoMesh temperature accuracy is ±0.4 °C over -20 to +8 °C.

- 三元组: (CryoMesh temperature accuracy) —[has_value]→ (±0.4 °C)；polarity=positive；modality=asserted
- 限定: range: -20 to +8 °C
- 证据（direct）: 「accuracy of ±0.4 °C over -20 to +8 °C」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 精度与量程逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-07  CryoMesh logs temperature every 60 seconds.

- 三元组: (CryoMesh) —[has_parameter]→ (logging interval 60 s)；polarity=positive；modality=asserted
- 证据（direct）: 「logged every 60 s」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 采样间隔逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-08  The CryoMesh pilot covered 36 vaccine shipments.

- 三元组: (CryoMesh pilot) —[has_value]→ (36 shipments)；polarity=positive；modality=asserted
- 证据（direct）: 「pilot covered 36 vaccine shipments」 @ {"page": 3, "part": "Results"}
- 置信度: high — 试点规模逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-09  CryoMesh detected 2 temperature excursions in the pilot.

- 三元组: (CryoMesh) —[generates]→ (detection of 2 temperature excursions)；polarity=positive；modality=asserted
- 限定: scope: 36-shipment pilot
- 证据（direct）: 「detected 2 temperature excursions」 @ {"page": 3, "part": "Results"}
- 置信度: high — 检出数逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-10  The 2 excursions detected by CryoMesh were missed by the reference logger.

- 三元组: (Reference logger) —[underperforms]→ (CryoMesh (missed 2 excursions))；polarity=positive；modality=asserted
- 限定: scope: pilot
- 证据（direct）: 「both excursions were missed by the reference logger」 @ {"page": 3, "part": "Results"}
- 置信度: high — 比较对象与事件数逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-11  CryoMesh mean absolute deviation from the reference thermometer was 0.3 °C.

- 三元组: (CryoMesh) —[has_value]→ (mean absolute deviation 0.3 °C vs reference thermometer)；polarity=positive；modality=asserted
- 证据（direct）: 「mean absolute deviation of 0.3 °C against the reference thermometer」 @ {"page": 3, "part": "Results"}
- 置信度: high — 偏差指标与基准逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-12  CryoMesh temperature accuracy is comparable to the reference logger within the tested range.

- 三元组: (CryoMesh) —[comparable_to]→ (reference logger)；polarity=positive；modality=asserted
- 限定: metric: temperature accuracy；note: MAD 0.3 °C, no significant bias reported
- 证据（direct）: 「no significant bias against the reference logger was observed」 @ {"page": 3, "part": "Results"}
- 置信度: medium — 无显著偏差不升级为等价，保留原文表述
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-13  CryoMesh nodes form a multi-hop mesh without a dedicated gateway.

- 三元组: (CryoMesh nodes) —[supports]→ (multi-hop mesh without dedicated gateway)；polarity=positive；modality=asserted
- 证据（direct）: 「nodes form a multi-hop mesh without a dedicated gateway」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 组网能力逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-14  CryoMesh data is exported as CSV per shipment.

- 三元组: (CryoMesh data export) —[produces_output]→ (CSV per shipment)；polarity=positive；modality=asserted
- 证据（direct）: 「exported as CSV per shipment」 @ {"page": 2, "part": "Methods"}
- 置信度: high — 导出形态逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-15  One CryoMesh node failed due to condensation during the pilot.

- 三元组: (CryoMesh node) —[limits]→ (condensation failure (1 of 36 shipments))；polarity=positive；modality=asserted
- 限定: scope: pilot
- 证据（direct）: 「one node failed due to condensation」 @ {"page": 4, "part": "Limitations"}
- 置信度: high — 失效事件与原因逐字可对
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-16  CryoMesh is not rated for air freight.

- 三元组: (CryoMesh) —[applies_to]→ (air freight)；polarity=negative；modality=asserted
- 证据（direct）: 「not rated for air freight」 @ {"page": 4, "part": "Limitations"}
- 置信度: high — 否定极性编码，适用边界保留
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-17  The CryoMesh team proposes extending the nodes to humidity sensing.

- 三元组: (CryoMesh nodes) —[extends]→ (humidity sensing)；polarity=positive；modality=proposed
- 限定: status: proposal
- 证据（direct）: 「we propose extending the nodes to humidity sensing」 @ {"page": 4, "part": "Future work"}
- 置信度: medium — 提议状态保留，不升级为已实现
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

## status = conflict（2 条）

### E-19  The pilot firmware was version 1.2 (Methods statement).

- 三元组: (CryoMesh pilot firmware) —[has_value]→ (version 1.2)；polarity=positive；modality=asserted
- 限定: stated in: Methods
- 证据（direct）: 「firmware version 1.2 was used throughout the pilot」 @ {"page": 2, "part": "Methods"}
- 置信度: low — 与 Results 的版本表述冲突，交人工裁定
- 冲突对象: ['E-20']
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

### E-20  The pilot firmware was version 1.3 (Results statement).

- 三元组: (CryoMesh pilot firmware) —[has_value]→ (version 1.3)；polarity=positive；modality=asserted
- 限定: stated in: Results
- 证据（direct）: 「running firmware 1.3, the fleet completed the pilot」 @ {"page": 3, "part": "Results"}
- 置信度: low — 与 Methods 的版本表述冲突，交人工裁定
- 冲突对象: ['E-19']
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______

## status = not_reported（1 条）

### E-18  Whether CryoMesh calibration drifts over more than 30 days is not reported in the paper.

- 三元组: (CryoMesh calibration drift) —[has_property]→ (drift over more than 30 days)；polarity=positive；modality=asserted
- 证据（direct）: 「」 @ {}
- 置信度: low — 未报告条目，已声明检索范围
- 检索范围: 全文：Methods/Results/Limitations 与 Table 1-2，未见 30 天以上漂移数据
- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______


#!/usr/bin/env python3
"""Build only this bundle's SYNTHETIC ledgers; stdlib, no external data."""

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "examples" / "synthetic"


def load_case():
    return json.loads((BASE / "input" / "case.json").read_text(encoding="utf-8"))


def ev(source_id, quote, stance, location):
    return {
        "source_id": source_id,
        "quote": quote,
        "location": location,
        "stance": stance,
    }


Q = {
    "q12": "S1-2024 直接测量记录：在25 °C下，M7的电导率为12 mS/cm（n=3）。",
    "heat": "Lamp-L将样品加热至80 °C。",
    "coat": "涂层C并未阻止离子穿透；离子穿过了涂层C。",
    "pt15": "PT处理组的平均电导率为15 mS/cm。",
    "infer": "作者推断，PT可能通过降低晶界电阻提高电导率，但本研究没有直接测量晶界电阻。",
    "direction": "在S1中，M7样品溶解了沉积盐D，而不是沉积盐D溶解M7样品。",
    "time": "本研究在2024年完成，不代表2025年的复测结果。",
    "q9": "S2-2025 直接复测：在25 °C下，M7的电导率为9 mS/cm（n=3）。",
    "s2diff": "PT组与对照组的差异区间跨越零，因此PT提高电导率在本数据集中未成立。",
    "s3infer": "S3-2024 综述：作者推断PT可能改善离子迁移数；该判断来自阻抗谱拟合，不是对离子迁移数的直接测量。",
    "tox": "S4-2025 细胞实验：5个培养样本中有2个在PT暴露后出现明显细胞毒性。",
    "clinical": "实验没有评估人体安全性，也没有支持立即临床使用。",
    "proposal": "作者提出未来可研究低剂量PT，但该提议没有疗效数据支撑。",
    "s5method": "S5-2023 方法文档：电导率以四探针法直接测量；晶界电阻通过等效电路拟合估计。",
    "s5stable": "未测量长期稳定性。",
    "s6year": "S6-2025 稳定性简报：仅完成24小时测试。不能据此确定一年的稳定性。",
    "s6heat": "未测试高温循环。",
}


def component(cid, text, disposition, nature, basis, rationale, evidence):
    return {
        "component_id": cid,
        "text": text,
        "disposition": disposition,
        "claim_nature": nature,
        "evidence_basis": basis,
        "rationale": rationale,
        "evidence": evidence,
    }


def specifications():
    return {
        "C001": ("supported", "accept", [component(
            "C001.a", "S1于2024年在25 °C直接测得M7电导率12 mS/cm", "supported",
            "positive_fact", "direct_measurement", "来源时间、测试温度和数值均与直接测量记录一致。",
            [ev("S1", Q["q12"], "support", "S1首句")]
        )]),
        "C002": ("not_established", "rewrite", [component(
            "C002.a", "S1证明PT必然提高电导率", "not_established",
            "positive_fact", "author_inference", "源文仅称可能提高，草稿将或然推断升级为必然和证明；没有强模态的反向事实。",
            [ev("S1", Q["infer"], "context", "S1作者推断句")]
        )]),
        "C003": ("contradicted", "rewrite", [component(
            "C003.a", "S2于2024年测得M7电导率9 mS/cm", "contradicted",
            "positive_fact", "direct_measurement", "数值一致但测量时间层相反：S2明确为2025复测。",
            [ev("S2", Q["q9"], "reverse", "S2首句")]
        )]),
        "C004": ("mixed", "rewrite", [
            component("C004.a", "S1在25 °C测得12 mS/cm", "supported", "positive_fact", "direct_measurement",
                      "S1直接测量值一致。", [ev("S1", Q["q12"], "support", "S1首句")]),
            component("C004.b", "S2在25 °C测得12 mS/cm", "contradicted", "positive_fact", "direct_measurement",
                      "S2在相同温度测得9而非12，是数值反向证据。", [ev("S2", Q["q9"], "reverse", "S2首句")])
        ]),
        "C005": ("mixed", "rewrite", [
            component("C005.a", "S3直接测量了离子迁移数", "contradicted", "measurement_attribution", "direct_measurement",
                      "S3明确说不是直接测量，反驳测量方式归属。", [ev("S3", Q["s3infer"], "reverse", "S3首句")]),
            component("C005.b", "S3证实PT提高离子迁移数", "not_established", "positive_fact", "author_inference",
                      "拟合只引出可能改善的作者推断，没有建立证实版本。", [ev("S3", Q["s3infer"], "context", "S3首句")])
        ]),
        "C006": ("supported", "accept", [component(
            "C006.a", "S3作者推断PT可能改善离子迁移数", "supported",
            "author_inference", "author_inference", "命题只归属作者的可能推断，未夸大为直接测量或确定事实。",
            [ev("S3", Q["s3infer"], "support", "S3首句")]
        )]),
        "C007": ("not_established", "reject", [
            component("C007.a", "应立即将PT用于临床", "not_established", "recommendation", "normative_judgment",
                      "这是无支持的建议，不因缺少证据而伪装成已被反向事实证明。",
                      [ev("S4", Q["clinical"], "context", "S4第二句")]),
            component("C007.b", "PT的人体安全性已经验证", "not_established", "positive_fact", "absence_of_evidence",
                      "未评估人体安全性说明验证命题未建立，而非有人体不安全的直接反证。",
                      [ev("S4", Q["clinical"], "context", "S4第二句")])
        ]),
        "C008": ("contradicted", "reject", [component(
            "C008.a", "S4所有培养样本均未出现细胞毒性", "contradicted",
            "negative_fact", "direct_observation", "源文明确观察2个样本出现毒性，是对全称否定事实的直接反向证据。",
            [ev("S4", Q["tox"], "reverse", "S4首句")]
        )]),
        "C009": ("supported", "accept", [
            component("C009.a", "S4的5个样本中2个出现毒性", "supported", "positive_fact", "direct_observation",
                      "计数和观察结果一致。", [ev("S4", Q["tox"], "support", "S4首句")]),
            component("C009.b", "S4作者提出未来研究低剂量PT", "supported", "proposal_attribution", "source_statement",
                      "仅支持作者曾提出该研究提议，不推断提议已有疗效。", [ev("S4", Q["proposal"], "support", "S4第三句")])
        ]),
        "C010": ("contradicted", "rewrite", [component(
            "C010.a", "S4低剂量PT提议已有疗效数据支撑", "contradicted",
            "positive_fact", "source_statement", "被裁决的是‘数据已存在’这一事实；源文明确否认数据支撑，并非裁决提议本身真假。",
            [ev("S4", Q["proposal"], "reverse", "S4第三句")]
        )]),
        "C011": ("contradicted", "rewrite", [component(
            "C011.a", "S1中沉积盐D溶解M7样品", "contradicted",
            "positive_fact", "direct_observation", "草稿反转溶解者与受作用者；源文明确给出相反主客方向。",
            [ev("S1", Q["direction"], "reverse", "S1方向句")]
        )]),
        "C012": ("supported", "accept", [component(
            "C012.a", "M7样品被Lamp-L加热至80 °C", "supported",
            "positive_fact", "direct_observation", "被动表达与源文主动表达事件方向相同，温度一致。",
            [ev("S1", Q["heat"], "support", "S1第二句")]
        )]),
        "C013": ("contradicted", "rewrite", [component(
            "C013.a", "S1中涂层C阻止离子穿透", "contradicted",
            "positive_fact", "direct_observation", "源文明确说未阻止且离子穿过，是直接反向证据。",
            [ev("S1", Q["coat"], "reverse", "S1涂层句")]
        )]),
        "C014": ("not_established", "rewrite", [component(
            "C014.a", "S2证实PT提高电导率", "not_established",
            "positive_fact", "absence_of_evidence", "区间跨零使提高未成立，但不自动证明真实效应必为零或下降，因此不是contradicted。",
            [ev("S2", Q["s2diff"], "context", "S2差异句")]
        )]),
        "C015": ("mixed", "rewrite", [
            component("C015.a", "S1直接测得晶界电阻降低", "contradicted", "measurement_attribution", "direct_measurement",
                      "反向证据只反驳‘直接测量’这一归属，不把未知的电阻变化方向写成否定事实。",
                      [ev("S1", Q["infer"], "reverse", "S1推断句")]),
            component("C015.b", "S1作者推断PT可能降低晶界电阻", "supported", "author_inference", "author_inference",
                      "准确保留作者推断和可能模态。", [ev("S1", Q["infer"], "support", "S1推断句")])
        ]),
        "C016": ("supported", "accept", [
            component("C016.a", "S5规定四探针直接测量电导率", "supported", "method_attribution", "direct_measurement",
                      "方法文档明确支持直接测量归属。", [ev("S5", Q["s5method"], "support", "S5首句")]),
            component("C016.b", "S5通过等效电路拟合估计晶界电阻", "supported", "method_attribution", "model_inference",
                      "拟合估计与直接测量分开记录。", [ev("S5", Q["s5method"], "support", "S5首句")])
        ]),
        "C017": ("not_established", "rewrite", [component(
            "C017.a", "S5证明M7具备一年长期稳定性", "not_established",
            "positive_fact", "absence_of_evidence", "未测量长期稳定性只能说明证明未建立，不构成稳定或不稳定的反向测量。",
            [ev("S5", Q["s5stable"], "context", "S5末句")]
        )]),
        "C018": ("not_established", "rewrite", [component(
            "C018.a", "S6证明M7不能保持一年稳定性", "not_established",
            "negative_fact", "absence_of_evidence", "24小时未覆盖一年；草稿的强否定仍未知，不能拿证据缺口当反向证据。",
            [ev("S6", Q["s6year"], "context", "S6前两句")]
        )]),
        "C019": ("mixed", "rewrite", [
            component("C019.a", "S6完成24小时测试", "supported", "positive_fact", "direct_observation",
                      "测试时长有直接来源支持。", [ev("S6", Q["s6year"], "support", "S6首句")]),
            component("C019.b", "S6完成高温循环测试", "contradicted", "positive_fact", "direct_observation",
                      "源文明确未测试，是对‘已完成’的反向证据。", [ev("S6", Q["s6heat"], "reverse", "S6末句")])
        ]),
        "C020": ("mixed", "rewrite", [
            component("C020.a", "S1的2024结果代表S2的2025复测", "contradicted", "positive_fact", "source_time_layer",
                      "S1明确排除代表2025复测，时间层不可合并。", [ev("S1", Q["time"], "reverse", "S1末句")]),
            component("C020.b", "S2在25 °C测得9 mS/cm", "supported", "positive_fact", "direct_measurement",
                      "S2的直接复测条件与数值一致。", [ev("S2", Q["q9"], "support", "S2首句")])
        ])
    }


CORRECTIONS = {
    "C002": "S1报告PT组平均电导率为15 mS/cm；作者仅推断PT可能提高电导率。",
    "C003": "S2在2025年测得M7在25 °C下的电导率为9 mS/cm。",
    "C004": "S1在2024年测得12 mS/cm，S2在2025年相同温度复测为9 mS/cm。",
    "C005": "S3由阻抗谱拟合推断PT可能改善离子迁移数，未直接测量或证实该数值提高。",
    "C007": "S4未评估人体安全性，也未支持立即临床使用；该建议尚不成立。",
    "C008": "S4的5个培养样本中有2个在PT暴露后出现明显细胞毒性。",
    "C010": "S4提出未来研究低剂量PT，但该提议尚无疗效数据支撑。",
    "C011": "S1中，M7样品溶解了沉积盐D。",
    "C013": "S1中涂层C未阻止离子穿透，离子穿过了涂层C。",
    "C014": "S2中PT组与对照组差异区间跨越零，尚未建立PT提高电导率。",
    "C015": "S1未直接测量晶界电阻；作者仅推断PT可能通过降低晶界电阻提高电导率。",
    "C017": "S5未测量长期稳定性，M7的一年稳定性尚未建立。",
    "C018": "S6仅完成24小时测试，不能据此确定M7的一年稳定性或稳定性缺失。",
    "C019": "S6完成24小时测试，但未测试高温循环。",
    "C020": "S1的2024年结果不代表2025年复测；S2在25 °C复测为9 mS/cm。"
}

CORRECTION_SOURCES = {
    "C002": ["S1"], "C003": ["S2"], "C004": ["S1", "S2"],
    "C005": ["S3"], "C007": ["S4"], "C008": ["S4"],
    "C010": ["S4"], "C011": ["S1"], "C013": ["S1"],
    "C014": ["S2"], "C015": ["S1"], "C017": ["S5"],
    "C018": ["S6"], "C019": ["S6"], "C020": ["S1", "S2"]
}


UNCERTAINTY = [
    {
        "uncertainty_id": "U001",
        "input_ids": ["C004", "C020"],
        "topic": "cross_source_time_conflict",
        "text": "S1与S2属于不同时间层且测值冲突；保留逐源裁决，不平均、不投票。"
    },
    {
        "uncertainty_id": "U002",
        "input_ids": ["C002", "C014", "C017", "C018"],
        "topic": "absence_is_not_reverse",
        "text": "模态、统计不确定和未测量均只支持未建立，不推出相反事实。"
    },
    {
        "uncertainty_id": "U003",
        "input_ids": ["C005", "C015"],
        "topic": "measurement_vs_inference",
        "text": "拟合与作者推断不能直接升级为仪器直接测量或确定事实。"
    }
]


def make_full(case):
    specs = specifications()
    records = []
    corrections = []
    changes = []
    for assertion in case["assertions"]:
        input_id = assertion["input_id"]
        verdict, review, components = copy.deepcopy(specs[input_id])
        correction_ids = []
        if input_id in CORRECTIONS:
            correction_id = "FIX-" + input_id
            correction_ids = [correction_id]
            corrections.append({
                "corrected_claim_id": correction_id,
                "input_id": input_id,
                "corrected_text": CORRECTIONS[input_id],
                "rationale": "仅提供带证据边界的替换建议；original_claim保持原样。",
                "source_ids": CORRECTION_SOURCES[input_id]
            })
            changes.append({
                "change_id": "CHANGE-" + input_id,
                "input_id": input_id,
                "corrected_claim_ids": [correction_id],
                "change_type": "separate_corrected_claim_proposal",
                "original_preserved": True
            })
        records.append({
            "input_id": input_id,
            "original_claim": assertion["claim"],
            "decision_status": "adjudicated",
            "verdict": verdict,
            "components": components,
            "corrected_claim_ids": correction_ids,
            "review_disposition": review
        })
    return {
        "schema_version": "1.0",
        "synthetic": True,
        "notice": "SYNTHETIC / 合成裁决台账，非正式科研结果。",
        "case_id": case["case_id"],
        "audit_complete": True,
        "assertions": records,
        "corrected_claims": corrections,
        "sources": [source["source_id"] for source in case["sources"]],
        "uncertainty": copy.deepcopy(UNCERTAINTY),
        "change_records": changes
    }


def make_partial(full):
    partial = copy.deepcopy(full)
    partial["audit_complete"] = False
    pending_ids = []
    for index, record in enumerate(partial["assertions"]):
        if index == 0:
            continue
        pending_ids.append(record["input_id"])
        record["decision_status"] = "pending"
        record["verdict"] = None
        record["components"] = []
        record["corrected_claim_ids"] = []
        record["review_disposition"] = "pending"
    partial["corrected_claims"] = []
    partial["change_records"] = []
    partial["uncertainty"] = [{
        "uncertainty_id": "U-PARTIAL",
        "input_ids": pending_ids,
        "topic": "early_checkpoint",
        "text": "诚实early partial：已登记全部20个ID和原文，仅C001完成，其余均pending。"
    }]
    return partial


def make_skipped(full):
    skipped = copy.deepcopy(full)
    skipped["assertions"] = [record for record in skipped["assertions"] if record["input_id"] != "C020"]
    skipped["corrected_claims"] = [item for item in skipped["corrected_claims"] if item["input_id"] != "C020"]
    skipped["change_records"] = [item for item in skipped["change_records"] if item["input_id"] != "C020"]
    skipped["audit_complete"] = False
    skipped["uncertainty"] = [{
        "uncertainty_id": "U-SKIPPED-NEGATIVE",
        "input_ids": ["C020"],
        "topic": "intentional_negative_fixture",
        "text": "故意跳过C020；这是验证错误，不得作为合法partial。"
    }]
    return skipped


def make_invalid_mixed(full):
    invalid = copy.deepcopy(full)
    invalid["assertions"][0]["verdict"] = "mixed"
    invalid["uncertainty"] = [{
        "uncertainty_id": "U-MIXED-NEGATIVE",
        "input_ids": ["C001"],
        "topic": "intentional_negative_fixture",
        "text": "故意把只有一个supported component的C001标成mixed。"
    }]
    return invalid


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    case = load_case()
    full = make_full(case)
    write_json(BASE / "expected" / "adjudication-ledger.json", full)
    write_json(BASE / "partial" / "adjudication-ledger.json", make_partial(full))
    write_json(BASE / "negative" / "skipped-id" / "adjudication-ledger.json", make_skipped(full))
    write_json(BASE / "negative" / "invalid-mixed" / "adjudication-ledger.json", make_invalid_mixed(full))
    print("Wrote four SYNTHETIC ledgers under {0}".format(BASE))


if __name__ == "__main__":
    main()

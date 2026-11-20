#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — Skill 自测：合成夹具 + 正/负例断言。

生成 examples/fixtures/ 下的全部合成夹具（一律虚构并标注"示例，非正式案例
结果 / illustrative"），然后以子进程方式真实调用各脚本 CLI，断言：

正例：
  P1 证据账本 validate 通过；
  P2 quote_audit --ocr-tolerant 全过（含一条 OCR 容忍匹配且被标注）；
  P3 无 --ocr-tolerant 时同一账本必须失败（证明容忍模式被闸控）；
  P4 status_ledger validate 通过（未知状态合规标注、聚合页仅线索、推断降级）；
  P5 license_tiers 输出绿/黄/红分级且红级带降级方案；
  P6 risk_grade 正确触发规则（低置信例触发 R-G2/R-G3/R-G4/R-G6/R-G7/R-G8，
     高置信例 grade=high）；
  P7 scaffold_result 镜像 output_contract 全部字段。
负例：
  N1 伪造 quote 必须审计失败 exit 非 0；
  N2 需要容忍匹配但未标注 allow_ocr_tolerance 必须失败；
  N3 把聚合页当登记依据必须被拦截（exit 非 0）；
  N4 未知状态配确定性措辞必须被拦截（exit 非 0）。

全部断言通过 exit 0；任一失败 exit 1。仅依赖标准库。
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
FIXTURES = SCRIPTS.parent / "examples" / "fixtures"

sys.path.insert(0, str(SCRIPTS))
from evidence_ledger import make_record  # noqa: E402

HEADER = "示例，非正式案例结果（illustrative，本文件全部内容均为虚构，仅用于自测）\n"

# 虚构专利文本中的权利要求句（正例引文来源，第 2 页）
CLAIM_SENTENCE = ("1. 一种用于演示引文闸控的虚构装置，其特征在于，"
                  "包括虚构部件甲、虚构部件乙以及连接二者的虚构连接件。")
# 虚构论文句
PAPER_SENTENCE = ("实验表明，该虚构方法在合成数据集上将检出率维持在百分之九十以上，"
                  "但该结果不构成任何专利有效性结论。")
# OCR 文本（含大小写、连字符断词与一处 OCR 误识别 lv<->ly）
OCR_SOURCE_LINE = ("THE PROPOSED METHOD IMPROVES DETECTION ACCU-\n"
                   "RACY ON NOISY IMAGES SIGNIFICANTLV.")
OCR_QUOTE = "the proposed method improves detection accuracy on noisy images significantly."


def write_fixtures():
    FIXTURES.mkdir(parents=True, exist_ok=True)

    patent_text = (
        HEADER +
        "（19）虚构国专利局  （12）发明专利说明书  （45）授权公告日 20XX-00-00\n"
        "（21）申请号 EX-1001 （22）申请日 20XX-00-00\n"
        "（54）发明名称：一种用于演示引文闸控的虚构装置\n"
        "（57）摘要：本虚构说明书仅用于测试，不含任何真实技术方案。\n"
        "说明书：背景技术部分描述了虚构场景；具体实施方式给出了虚构实施例一与二。\n"
        "注意：说明书中的实施例描述不等于授权权利要求的保护范围。\n"
        "\f"  # 第 2 页
        "权利要求书\n" + CLAIM_SENTENCE + "\n"
        "2. 根据权利要求 1 所述的虚构装置，其特征在于，所述虚构连接件为卡扣结构。\n"
    )
    (FIXTURES / "fictional_patent_EX1001.txt").write_text(patent_text, encoding="utf-8")

    (FIXTURES / "fictional_paper_EX2001.txt").write_text(
        HEADER + "虚构对比论文《合成数据集上的检出率研究》（illustrative）\n"
        + PAPER_SENTENCE + "\n", encoding="utf-8")

    (FIXTURES / "fictional_ocr_merged_WO.txt").write_text(
        HEADER + "WO 文献 OCR 合并文本（页边界以 [PAGE] 保留）\n[PAGE 1]\n"
        + OCR_SOURCE_LINE + "\n", encoding="utf-8")

    # 正例账本
    ok_records = [
        make_record(
            "C1",
            "虚构专利 EX-1001 的授权权利要求 1 限定了一种包含虚构部件甲、乙及连接件的装置"
            "（仅描述权利要求文本本身，不越界到说明书实施例）。",
            CLAIM_SENTENCE,
            {"file": "fictional_patent_EX1001.txt", "page": 2,
             "source_kind": "patent_pdf_text"}),
        make_record(
            "C2",
            "虚构对比论文 EX-2001 报告了合成数据集上的检出率结果，且论文自身声明"
            "该结果不构成专利有效性结论。",
            PAPER_SENTENCE,
            {"file": "fictional_paper_EX2001.txt", "source_kind": "scientific_paper"}),
        make_record(
            "C3",
            "虚构 WO 文献 OCR 文本声称所提方法在含噪图像上提升检出准确率"
            "（OCR 容忍匹配，结论需降级）。",
            OCR_QUOTE,
            {"file": "fictional_ocr_merged_WO.txt", "source_kind": "ocr_merged"},
            allow_ocr_tolerance=True),
    ]
    (FIXTURES / "ledger_ok.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ok_records),
        encoding="utf-8")

    # 负例 1：伪造引文（来源文本中不存在）
    forged = make_record(
        "B1", "虚构专利 EX-1001 的权利要求包含一种量子通信模块。",
        "3. 一种量子通信模块，其特征在于包含虚构量子芯片。",
        {"file": "fictional_patent_EX1001.txt", "source_kind": "patent_pdf_text"})
    (FIXTURES / "ledger_bad_forged.jsonl").write_text(
        json.dumps(forged, ensure_ascii=False) + "\n", encoding="utf-8")

    # 负例 2：需要 OCR 容忍但未标注 allow_ocr_tolerance
    unmarked = make_record(
        "B2", "虚构 WO 文献声称提升检出准确率（未标注容忍模式）。",
        OCR_QUOTE,
        {"file": "fictional_ocr_merged_WO.txt", "source_kind": "ocr_merged"},
        allow_ocr_tolerance=False)
    (FIXTURES / "ledger_bad_tolerant_unmarked.jsonl").write_text(
        json.dumps(unmarked, ensure_ascii=False) + "\n", encoding="utf-8")

    today = datetime.date.today().isoformat()
    # 正例状态台账
    status_ok = [
        {"entity": "EX-1001", "status_value": "未知", "source_kind": "official_register",
         "query_date": today, "as_register_basis": True,
         "statement": "截至查询日期，该虚构专利的当前官方法律状态未知，需以登记簿复核为准。",
         "review_advice": "到官方登记簿复核最新法律状态并记录查询日期"},
        {"entity": "EX-1002", "status_value": "授权", "source_kind": "aggregation_page",
         "query_date": today, "leads_only": True,
         "note": "聚合页线索，待官方登记复核",
         "review_advice": "聚合页仅作线索，结论前必须回官方登记簿确认"},
        {"entity": "EX-1003", "status_value": "失效", "source_kind": "inference",
         "query_date": today, "downgraded": True,
         "review_advice": "系按缴费期限推断，必须人工到官方登记簿复核",
         "note": "推断状态，已降级标注"},
    ]
    (FIXTURES / "status_ok.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in status_ok),
        encoding="utf-8")

    # 负例 3：聚合页当登记依据
    bad_agg = {"entity": "EX-2001", "status_value": "授权",
               "source_kind": "aggregation_page", "query_date": today,
               "as_register_basis": True, "leads_only": True}
    (FIXTURES / "status_bad_aggregation.jsonl").write_text(
        json.dumps(bad_agg, ensure_ascii=False) + "\n", encoding="utf-8")

    # 负例 4：未知状态 + 确定性措辞
    bad_unknown = {"entity": "EX-2002", "status_value": "未知",
                   "source_kind": "official_register", "query_date": today,
                   "as_register_basis": True,
                   "statement": "该专利已授权且专利权有效。",
                   "review_advice": "复核官方登记簿"}
    (FIXTURES / "status_bad_unknown.jsonl").write_text(
        json.dumps(bad_unknown, ensure_ascii=False) + "\n", encoding="utf-8")

    # 数据源清单
    (FIXTURES / "sources.json").write_text(json.dumps({"sources": [
        {"name": "国家知识产权局 CNIPA 中国专利公布公告", "url": "http://epub.cnipa.gov.cn",
         "access": "public"},
        {"name": "Google Patents", "url": "https://patents.google.com", "access": "public"},
        {"name": "PatSnap 智慧芽", "url": "https://www.patsnap.com", "access": "login"},
    ]}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 结论清单
    (FIXTURES / "conclusions.json").write_text(json.dumps({"conclusions": [
        {"claim_id": "C-low",
         "statement": "虚构低置信结论：引文未核验+状态过期+同族口径不明+覆盖不全+单一来源+状态未知",
         "fields_present": ["quote", "locator", "source_kind", "status", "query_date", "sources"],
         "evidence_verified": False, "family_scope_known": False,
         "corpus_coverage": "partial", "source_count": 1,
         "status_query_date": "2020-01-01", "status_value": "未知"},
        {"claim_id": "C-high",
         "statement": "虚构高置信结论：字段齐备、双来源、引文已核验",
         "fields_present": ["quote", "locator", "source_kind", "status", "query_date", "sources"],
         "evidence_verified": True, "match_mode": "verbatim",
         "family_scope_known": True, "corpus_coverage": "complete",
         "source_count": 2, "status_query_date": today, "status_value": "授权"},
    ]}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 最小 case.json 夹具
    (FIXTURES / "case_fixture.json").write_text(json.dumps({
        "case_id": "case-fixture-001",
        "output_contract": {
            "summary": {"type": "string"},
            "claim_chart": {"type": "array"},
            "legal_status_table": {"type": "array"},
            "risk_notes": {"type": "string"},
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def run(script, *cli_args):
    """运行 scripts/ 下的脚本，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *cli_args],
        capture_output=True, text=True)


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         (" — " + detail) if detail and not cond else ""))


def main():
    write_fixtures()
    f = lambda name: str(FIXTURES / name)  # noqa: E731

    # P1 账本结构与哈希校验
    r = run("evidence_ledger.py", "validate", "--ledger", f("ledger_ok.jsonl"))
    check("P1 证据账本 validate 通过", r.returncode == 0, r.stdout + r.stderr)

    # P2 OCR 容忍模式全过
    report_path = f("audit_report_ok.json")
    r = run("quote_audit.py", "--ledger", f("ledger_ok.jsonl"),
            "--base-dir", str(FIXTURES), "--ocr-tolerant", "--report", report_path)
    ok = r.returncode == 0
    tolerant_marked = False
    if ok and Path(report_path).exists():
        rep = json.loads(Path(report_path).read_text(encoding="utf-8"))
        tolerant_marked = rep.get("tolerant_matches") == ["C3"]
    check("P2 quote_audit --ocr-tolerant 全过且容忍匹配已标注", ok and tolerant_marked,
          r.stdout + r.stderr)

    # P3 不开容忍模式必须失败（OCR 引文严格匹配不过）
    r = run("quote_audit.py", "--ledger", f("ledger_ok.jsonl"), "--base-dir", str(FIXTURES))
    check("P3 未启用 --ocr-tolerant 时 OCR 引文被拦截", r.returncode != 0,
          "严格模式下竟全部通过")

    # P4 状态台账合规
    r = run("status_ledger.py", "validate", "--ledger", f("status_ok.jsonl"))
    check("P4 法律状态台账 validate 通过（未知纪律/线索/降级）", r.returncode == 0,
          r.stdout + r.stderr)

    # P5 授权分级
    r = run("license_tiers.py", "classify", "--sources", f("sources.json"),
            "--report", f("license_report.json"))
    tiers = []
    if r.returncode == 0 and Path(f("license_report.json")).exists():
        rep = json.loads(Path(f("license_report.json")).read_text(encoding="utf-8"))
        tiers = [x["tier"] for x in rep["results"]]
        red_ok = all(x.get("degradation") for x in rep["results"] if x["tier"] == "red")
    else:
        red_ok = False
    check("P5 license_tiers 绿/黄/红分级正确且红级带降级方案",
          tiers == ["green", "yellow", "red"] and red_ok, r.stdout + r.stderr)

    # P6 风险分级
    r = run("risk_grade.py", "--conclusions", f("conclusions.json"),
            "--report", f("risk_report.json"),
            "--checklist-md", f("review_checklist.md"))
    low_ok = high_ok = False
    if r.returncode == 0 and Path(f("risk_report.json")).exists():
        rep = json.loads(Path(f("risk_report.json")).read_text(encoding="utf-8"))
        by_id = {x["claim_id"]: x for x in rep["results"]}
        low = by_id.get("C-low", {})
        rules = {t["rule"] for t in low.get("triggered_rules", [])}
        low_ok = (low.get("grade") == "low"
                  and {"R-G2", "R-G3", "R-G4", "R-G6", "R-G7", "R-G8"} <= rules)
        high_ok = by_id.get("C-high", {}).get("grade") == "high"
    check("P6 risk_grade 触发规则与分级正确（C-low=low, C-high=high）",
          low_ok and high_ok, r.stdout + r.stderr)

    # P7 骨架镜像契约
    out = f("result_skeleton.json")
    r = run("scaffold_result.py", "--case", f("case_fixture.json"),
            "--out", out, "--force")
    mirrored_ok = False
    if r.returncode == 0 and Path(out).exists():
        sk = json.loads(Path(out).read_text(encoding="utf-8"))
        mirrored_ok = (sk.get("case_id") == "case-fixture-001"
                       and sk.get("status") == "partial"
                       and all(k in sk for k in
                               ("summary", "claim_chart", "legal_status_table", "risk_notes"))
                       and isinstance(sk.get("change_records"), list)
                       and len(sk["change_records"]) >= 1)
    check("P7 scaffold_result 镜像 output_contract 全部字段", mirrored_ok,
          r.stdout + r.stderr)

    # N1 伪造引文
    r = run("quote_audit.py", "--ledger", f("ledger_bad_forged.jsonl"),
            "--base-dir", str(FIXTURES), "--ocr-tolerant")
    check("N1 伪造 quote 审计失败 exit 非 0", r.returncode != 0)

    # N2 容忍匹配未标注
    r = run("quote_audit.py", "--ledger", f("ledger_bad_tolerant_unmarked.jsonl"),
            "--base-dir", str(FIXTURES), "--ocr-tolerant")
    check("N2 未标注 allow_ocr_tolerance 的容忍匹配被拦截", r.returncode != 0)

    # N3 聚合页当登记依据
    r = run("status_ledger.py", "validate", "--ledger", f("status_bad_aggregation.jsonl"))
    check("N3 聚合页当登记依据被拦截", r.returncode != 0)

    # N4 未知状态确定性措辞
    r = run("status_ledger.py", "validate", "--ledger", f("status_bad_unknown.jsonl"))
    check("N4 未知状态配确定性措辞被拦截", r.returncode != 0)

    n_fail = sum(1 for _, ok in RESULTS if not ok)
    print("\n自测完成：%d 项断言，%d 通过，%d 失败。"
          % (len(RESULTS), len(RESULTS) - n_fail, n_fail))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

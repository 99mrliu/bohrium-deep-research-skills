#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 汇总指纹与交叉核对结果，生成最终 result.json（provenance ledger 成品）。

用法:
    python3 build_result.py --workdir /app/work --output-dir /app/output \
        [--case /input/case.json]

行为:
    - case_id: case_id → id → caseId → "unknown_case" 回退。
    - output_contract 镜像: 在 case.json 中递归寻找 output_contract / contract /
      output_fields / required_fields 键；找到则逐一镜像其声明的字段
      （无法填的字段给 null 并在 uncertainties 中说明）。
    - provenance_ledger: 每个来源文件的指纹、快照风格、判定、是否可用于下游评估。
    - status 规则: 全部 verified → success；存在 mismatch/unverifiable → partial
      （并陈述限制）；零来源 → partial（空 ledger + 解释）。
    - 同时写出 output-dir/provenance_report.md（人类可读表格）。

退出码: 0 正常; 1 必要输入缺失; 2 参数用法错误。
"""
import argparse
import json
import os
import sys

CONTRACT_KEYS = ("output_contract", "contract", "output_fields", "required_fields")
# 编排文件：属于任务输入而非"来源文献"，不进入 provenance ledger、不参与 status 判定
ORCHESTRATION_BASENAMES = {"case.json", "task.md"}


def recursive_find(obj, keys, max_depth=12):
    """在任意嵌套结构中查找名为 keys 之一的键，返回 (key, value) 或 (None, None)。"""
    if max_depth < 0:
        return None, None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return k, obj[k]
        for v in obj.values():
            k2, v2 = recursive_find(v, keys, max_depth - 1)
            if k2 is not None:
                return k2, v2
    elif isinstance(obj, list):
        for v in obj:
            k2, v2 = recursive_find(v, keys, max_depth - 1)
            if k2 is not None:
                return k2, v2
    return None, None


def extract_contract_fields(contract_value):
    """从 contract 值中尽力提取字段名列表。支持 dict / list / str。"""
    fields = []
    if isinstance(contract_value, dict):
        for k in contract_value.keys():
            fields.append(str(k))
    elif isinstance(contract_value, list):
        for item in contract_value:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if name:
                    fields.append(str(name))
                else:
                    for k in item.keys():
                        fields.append(str(k))
    elif isinstance(contract_value, str):
        fields.append(contract_value)
    return fields


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成最终 result.json 与 provenance_report.md")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case", default=None)
    args = ap.parse_args(argv)

    workdir = os.path.abspath(args.workdir)
    outdir = os.path.abspath(args.output_dir)
    os.makedirs(outdir, exist_ok=True)

    manifest = load_json(os.path.join(workdir, "manifest.json"))
    if manifest is None:
        sys.stderr.write("ERROR: manifest.json missing/unreadable in %s\n" % workdir)
        return 1
    verification = load_json(os.path.join(workdir, "verification.json")) or {}

    # ---------------- case 解析
    case_data = load_json(args.case) if args.case else None
    case_id = "unknown_case"
    if isinstance(case_data, dict):
        case_id = (
            case_data.get("case_id")
            or case_data.get("id")
            or case_data.get("caseId")
            or case_id
        )
    elif manifest.get("case_id"):
        case_id = manifest["case_id"]

    uncertainties = []
    change_records = []

    # ---------------- output_contract 镜像
    contract_mirror = {}
    contract_key, contract_value = (None, None)
    if case_data is not None:
        contract_key, contract_value = recursive_find(case_data, CONTRACT_KEYS)
    if contract_key is not None:
        for field in extract_contract_fields(contract_value):
            # 本技能只负责来源真实性；下游质量判断字段无法在此填写 → null + 说明
            contract_mirror[field] = None
        if contract_mirror:
            uncertainties.append(
                "output_contract 字段已镜像但值为 null：本技能仅完成来源真实性核验，"
                "下游文献质量判断需绑定 verified 来源后另行填充"
            )
        change_records.append(
            {
                "step": "build_result",
                "action": "mirrored output_contract",
                "found_under_key": contract_key,
                "field_count": len(contract_mirror),
            }
        )
    else:
        uncertainties.append(
            "case.json 中未找到 output_contract/contract/output_fields/required_fields，"
            "无法镜像输出契约字段"
        )

    # ---------------- provenance ledger
    files = manifest.get("files") or []
    tlv = verification.get("text_layer_verdicts") or []
    verdict_by_file = {pv.get("text_file"): pv for pv in tlv}

    ledger = []
    excluded = []
    for entry in files:
        rel = entry.get("relpath")
        kind = entry.get("kind")
        if os.path.basename(rel or "") in ORCHESTRATION_BASENAMES:
            excluded.append(rel)
            continue
        flavor = entry.get("snapshot_flavor", "")
        pv = verdict_by_file.get(rel)
        if kind == "json":
            if flavor in ("crossref", "europepmc"):
                n_rec = sum(
                    1
                    for r in verification.get("records", [])
                    if r.get("snapshot_file") == rel
                )
                verdict = "verified" if n_rec > 0 else "unverifiable"
                note = (
                    "快照可解析，提取 %d 条记录" % n_rec
                    if n_rec > 0
                    else "快照风格已识别但未提取到记录"
                )
            else:
                verdict = "unverifiable"
                note = "非 Crossref/EuropePMC 快照（flavor=%s）" % (flavor or "?")
        elif kind in ("txt", "md", "pdf"):
            if pv:
                verdict = pv.get("verdict", "unverifiable")
                note = pv.get("reason") or ""
            else:
                verdict = "unverifiable"
                note = "未参与交叉核对"
        else:
            verdict = "unverifiable"
            note = "不支持的文件类型 kind=%s" % kind
        ledger.append(
            {
                "source": rel,
                "kind": kind,
                "size_bytes": entry.get("size_bytes"),
                "sha256": entry.get("sha256"),
                "snapshot_flavor": flavor or None,
                "verdict": verdict,
                "usable_for_assessment": verdict == "verified",
                "note": note,
            }
        )

    if excluded:
        change_records.append(
            {
                "step": "build_result",
                "action": "excluded orchestration files from provenance ledger",
                "files": excluded,
            }
        )

    # ---------------- status
    verdicts = [l["verdict"] for l in ledger]
    n_verified = sum(1 for v in verdicts if v == "verified")
    n_mismatch = sum(1 for v in verdicts if v == "mismatch")
    n_unverifiable = sum(1 for v in verdicts if v == "unverifiable")

    if not ledger:
        status = "partial"
        uncertainties.append("输入目录中未发现任何来源文件，provenance_ledger 为空")
    elif n_mismatch == 0 and n_unverifiable == 0 and n_verified > 0:
        status = "success"
    else:
        status = "partial"
        uncertainties.append(
            "来源核验未全部通过: verified=%d, mismatch=%d, unverifiable=%d；"
            "下游论断仅允许绑定 verified 来源，mismatch 已如实上报且未做静默修复"
            % (n_verified, n_mismatch, n_unverifiable)
        )

    duplicates = verification.get("duplicates") or []
    version_conflicts = verification.get("version_conflicts") or []
    if duplicates:
        uncertainties.append("检测到 %d 组重复记录（归一化标题相同）" % len(duplicates))
    if version_conflicts:
        uncertainties.append(
            "检测到 %d 组版本冲突（同 DOI 不同年份/类型）" % len(version_conflicts)
        )

    main_results = {
        "provenance_ledger": ledger,
        "counts": {
            "files": len(ledger),
            "verified": n_verified,
            "mismatch": n_mismatch,
            "unverifiable": n_unverifiable,
            "snapshot_records": verification.get("record_count", 0),
            "duplicate_groups": len(duplicates),
            "version_conflicts": len(version_conflicts),
        },
        "duplicates": duplicates,
        "version_conflicts": version_conflicts,
    }

    result = {
        "case_id": case_id,
        "status": status,
        "output_contract": contract_mirror,
        "main_results": main_results,
        "evidence": {
            "manifest": os.path.join(workdir, "manifest.json"),
            "verification": os.path.join(workdir, "verification.json"),
            "verification_summary": os.path.join(workdir, "verification_summary.md"),
        },
        "uncertainties": uncertainties,
        "change_records": change_records,
    }

    rpath = os.path.join(outdir, "result.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---------------- 人类可读报告
    lines = [
        "# Provenance Report（来源真实性台账）",
        "",
        "- case_id: `%s`" % case_id,
        "- status: **%s**" % status,
        "",
        "| 来源文件 | 类型 | 快照风格 | sha256(前12) | 判定 | 可用于评估 | 说明 |",
        "|---|---|---|---|---|---|---|",
    ]
    for l in ledger:
        sha = (l.get("sha256") or "")[:12]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                l["source"],
                l["kind"],
                l.get("snapshot_flavor") or "-",
                sha,
                l["verdict"],
                "是" if l["usable_for_assessment"] else "否",
                (l.get("note") or "-").replace("|", "\\|"),
            )
        )
    lines.append("")
    if duplicates:
        lines.append("## 重复记录")
        for d in duplicates:
            lines.append("- `%s` ← %s" % (d["normalized_title"][:80], d["files"]))
        lines.append("")
    if version_conflicts:
        lines.append("## 版本冲突")
        for v in version_conflicts:
            lines.append(
                "- DOI `%s`: years=%s types=%s" % (v["doi"], v["years"], v["types"])
            )
        lines.append("")
    if uncertainties:
        lines.append("## 不确定项")
        for u in uncertainties:
            lines.append("- %s" % u)
        lines.append("")
    ppath = os.path.join(outdir, "provenance_report.md")
    with open(ppath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    sys.stdout.write("result.json written: %s (status=%s)\n" % (rpath, status))
    sys.stdout.write("provenance_report written: %s\n" % ppath)
    return 0


if __name__ == "__main__":
    sys.exit(main())

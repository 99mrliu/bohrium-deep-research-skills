#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""warden_boot.py — 流水线启动守护（risk-warden 第一步，必做）。

职责（按序）：
  1. 容忍式读取 case.json；缺失或不可解析时仍写出 case_id="unknown"、
     status="unable_to_determine" 的 result.json，并以约定非零码(2)退出，绝不崩溃。
  2. 立即写出首份 partial 状态的 result.json（含 case_id 与 output_contract
     全部字段的占位）。【核心不变量】首份 partial 必须在任何实质计算之前落盘。
  3. 清点材料，生成 intake_manifest.json（path/exists/size/sha256/readable/note），
     缺失材料播种 uncertainty，并回填 result.json。
  4. 生成 work_plan.md 六步勾选清单。

退出码：0=正常完成；2=case.json 缺失/不可解析或其他被捕获的异常（已尽力落盘）。
任何输入不得产生 traceback。
"""
import argparse
import hashlib
import json
import os
import sys
import time

EXIT_OK = 0
EXIT_CASE_UNREADABLE = 2

MATERIAL_KEYS = ("materials", "material_paths", "material_files", "files", "inputs")

PLACEHOLDER = {"_placeholder": True, "note": "待填写：由 Agent 在主体工作阶段填充"}


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_write_json(path, obj):
    """尽力写 JSON，失败返回 False，不抛异常。"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warden_boot] 写文件失败 %s: %s\n" % (path, exc))
        return False


def load_case(case_path):
    """返回 (case_dict_or_none, error_note_or_none)。绝不抛异常。"""
    try:
        with open(case_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None, "case.json 顶层不是 JSON 对象"
        return data, None
    except FileNotFoundError:
        return None, "case.json 不存在: %s" % case_path
    except Exception as exc:  # noqa: BLE001
        return None, "case.json 不可解析: %s" % exc


def extract_contract_fields(case):
    """从 case.json 动态读取 output_contract 字段清单。兼容 list / dict。"""
    if not isinstance(case, dict):
        return []
    oc = case.get("output_contract")
    if isinstance(oc, list):
        return [str(x) for x in oc if isinstance(x, (str, int, float))]
    if isinstance(oc, dict):
        return [str(k) for k in oc.keys()]
    # 兼容字段名变体
    for alt in ("output_fields", "required_outputs", "contract"):
        v = case.get(alt)
        if isinstance(v, list):
            return [str(x) for x in v]
        if isinstance(v, dict):
            return [str(k) for k in v.keys()]
    return []


def extract_material_paths(case):
    """抽取材料路径条目：[{path, role}]。兼容 str 项与 dict 项。"""
    items = []
    if not isinstance(case, dict):
        return items
    for key in MATERIAL_KEYS:
        v = case.get(key)
        if not isinstance(v, list):
            continue
        for entry in v:
            if isinstance(entry, str):
                items.append({"path": entry, "role": key})
            elif isinstance(entry, dict):
                p = entry.get("path") or entry.get("file") or entry.get("filename")
                if isinstance(p, str):
                    items.append({"path": p, "role": str(entry.get("role", key))})
    # 去重保持顺序
    seen, out = set(), []
    for it in items:
        if it["path"] not in seen:
            seen.add(it["path"])
            out.append(it)
    return out


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(case, case_path):
    """清点材料，返回 (manifest_dict, missing_list)。"""
    base = os.path.dirname(os.path.abspath(case_path)) if case_path else os.getcwd()
    entries = []
    missing = []
    for it in extract_material_paths(case):
        raw = it["path"]
        resolved = raw if os.path.isabs(raw) else os.path.join(base, raw)
        entry = {
            "path": raw,
            "resolved_path": resolved,
            "role": it.get("role", ""),
            "exists": False,
            "size": None,
            "sha256": None,
            "readable": False,
            "note": "",
        }
        try:
            if not os.path.exists(resolved):
                entry["note"] = "材料缺失：路径不存在"
                missing.append({"path": raw, "reason": entry["note"], "critical": True})
            elif not os.path.isfile(resolved):
                entry["note"] = "路径存在但不是常规文件"
                missing.append({"path": raw, "reason": entry["note"], "critical": True})
            else:
                entry["exists"] = True
                entry["size"] = os.path.getsize(resolved)
                try:
                    entry["sha256"] = sha256_of(resolved)
                    entry["readable"] = True
                    entry["note"] = "ok"
                except OSError:
                    entry["note"] = "文件存在但不可读"
                    missing.append({"path": raw, "reason": entry["note"], "critical": True})
        except Exception as exc:  # noqa: BLE001
            entry["note"] = "清点异常: %s" % exc
            missing.append({"path": raw, "reason": entry["note"], "critical": True})
        entries.append(entry)
    manifest = {
        "generated_at": utc_now(),
        "case_path": case_path,
        "total": len(entries),
        "missing_count": len(missing),
        "entries": entries,
    }
    return manifest, missing


WORK_PLAN_TEMPLATE = """# work_plan.md — risk-warden 六步勾选清单

生成时间：{ts}
case_id：{case_id}

- [x] 1. intake 与首份 partial 落盘（warden_boot 已完成：intake_manifest.json + result.json[partial]）
- [ ] 2. 汇总异常事实（约束冲突/缺失材料/指标矛盾/设备报错/权限问题），运行 scripts/triage.py 得到机器可判定动作
- [ ] 3. 按 triage 动作执行主体工作：proceed / proceed_with_degradation（降级并记录）/ handoff_to_human（转人工，停止自主决策）/ terminate（终止并写明理由）
- [ ] 4. 填充 output_contract 全部字段；每条推荐参数值必须附可行性证据引用，或显式标注"待确认"
- [ ] 5. 交付前运行 scripts/final_audit.py；存在违例时按其结论回退 partial 并写明 partial_reason
- [ ] 6. 对账：核对 status / uncertainty / change_log 一致后交付 /app/output

预算提醒：剩余约 8 次模型请求时立即停止改进，转入第 4–6 步收尾。
"""


def main():
    ap = argparse.ArgumentParser(description="risk-warden 启动守护")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--output", default="/app/output", help="输出目录（result.json 落盘处）")
    ap.add_argument("--work", default="/app/work", help="工作目录（work_plan.md / intake_manifest.json 落盘处）")
    args = ap.parse_args()

    case, err = load_case(args.case)
    case_id = "unknown"
    contract_fields = []
    if case is not None:
        cid = case.get("case_id")
        if isinstance(cid, str) and cid.strip():
            case_id = cid.strip()
        contract_fields = extract_contract_fields(case)
    else:
        sys.stderr.write("[warden_boot] %s\n" % err)

    # ---- 步骤 2：首份 partial 必须在任何实质计算（材料清点/哈希）之前落盘 ----
    result = {
        "case_id": case_id,
        "status": "unable_to_determine" if case is None else "partial",
        "partial_reason": ("case.json 缺失或不可解析：%s" % err) if case is None
                          else "流水线初始化：warden_boot 首份占位，尚未开始实质计算",
        "sources": [],
        "uncertainty": [],
        "change_log": [{
            "ts": utc_now(),
            "event": "warden_boot_first_partial",
            "detail": "首份 partial 在任何实质计算之前落盘（核心不变量）",
        }],
    }
    for field in contract_fields:
        result[field] = dict(PLACEHOLDER)
    result_path = os.path.join(args.output, "result.json")
    if not safe_write_json(result_path, result):
        # 输出目录不可写：最后努力写到当前目录，仍不崩溃
        safe_write_json(os.path.abspath("result.json"), result)
    if case is None:
        # 约定：case 不可读时尽早以非零码退出
        safe_write_json(os.path.join(args.work, "intake_manifest.json"), {
            "generated_at": utc_now(), "case_path": args.case,
            "total": 0, "missing_count": 0, "entries": [],
            "note": "case.json 不可读，无法清点材料",
        })
        return EXIT_CASE_UNREADABLE

    # ---- 步骤 3：材料清点（首份 partial 已落盘后才进行实质计算）----
    manifest, missing = build_manifest(case, args.case)
    safe_write_json(os.path.join(args.work, "intake_manifest.json"), manifest)
    # 同时放一份到输出目录，便于交付复核
    safe_write_json(os.path.join(args.output, "intake_manifest.json"), manifest)

    for m in missing:
        result["uncertainty"].append({
            "kind": "missing_material",
            "path": m["path"],
            "detail": m["reason"],
            "impact": "以该材料为依据的结论必须降级或标注待确认",
        })
    result["change_log"].append({
        "ts": utc_now(),
        "event": "intake_completed",
        "detail": "清点材料 %d 项，缺失/不可读 %d 项" % (manifest["total"], manifest["missing_count"]),
    })
    safe_write_json(result_path, result)

    # ---- 步骤 4：六步勾选清单 ----
    plan = WORK_PLAN_TEMPLATE.format(ts=utc_now(), case_id=case_id)
    try:
        os.makedirs(args.work, exist_ok=True)
        with open(os.path.join(args.work, "work_plan.md"), "w", encoding="utf-8") as f:
            f.write(plan)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warden_boot] 写 work_plan.md 失败: %s\n" % exc)

    sys.stdout.write("[warden_boot] done: case_id=%s contract_fields=%d missing=%d\n"
                     % (case_id, len(contract_fields), manifest["missing_count"]))
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001  —— 兜底：任何输入不得 traceback
        sys.stderr.write("[warden_boot] 未预期异常（已捕获，不崩溃）: %s\n" % exc)
        safe_write_json(os.path.abspath("result.json"), {
            "case_id": "unknown",
            "status": "unable_to_determine",
            "partial_reason": "warden_boot 内部异常: %s" % exc,
            "sources": [], "uncertainty": [{"kind": "boot_error", "detail": str(exc)}],
            "change_log": [{"ts": utc_now(), "event": "boot_error", "detail": str(exc)}],
        })
        sys.exit(EXIT_CASE_UNREADABLE)

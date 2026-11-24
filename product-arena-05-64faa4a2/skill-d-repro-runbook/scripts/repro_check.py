#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repro_check.py — 复现清单核验 + 章节命令与真实命令逐条比对 + 步骤顺序核验。

纯标准库、确定性、无网络。只做比对与报告，不修改任何文件。

核验内容：
1. 复现清单七项（G1-G7）：代码版本 / 环境 / 依赖 / 命令 / 数据获取 / 种子 / 预期校验，
   状态为 present / missing / unknown（unknown = 材料本身没有该信息，需人工确认）。
2. 命令一致性：章节中的命令（围栏代码块、行内代码、含 --flag 的散文行）与
   commands.json 中的真实命令逐条比对；flag 值被改写或出现臆造 flag → FAIL。
3. 顺序一致性：章节步骤顺序与日志时间线比对（日志不可得则 skipped）。

退出码：0 = PASS/WARN，1 = FAIL，2 = 用法错误。

用法：
    python3 scripts/repro_check.py --chapter <章节.md> --commands <commands.json>
        [--steps <steps.md>] --out <输出目录>
"""
import argparse
import json
import os
import re
import sys

WS_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[一-鿿]")
FENCE_RE = re.compile(r"^\s*```(\w*)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
FLAG_RE = re.compile(r"(--[\w][\w\-]*)(?:=([^\s，。；,;]+))?")
EXEC_START_RE = re.compile(r"(?:^|[\s`\"'（(])((?:python3?|bash|sh|wget|curl|pip3?|conda)\s)")

CODE_VERSION_RE = re.compile(r"commit\s+[0-9a-f]{7,40}|代码版本|git\s+(?:checkout|clone)|版本[:：]\s*\S+")
VALIDATE_RE = re.compile(
    r"acc(?:uracy)?|f1|auc|bleu|rouge|\bloss\b|校验|checksum|md5|预期|指标|阈值|"
    r"准确率|精确率|召回率|得分|评分|baseline|基线", re.I)
SEED_MENTION_RE = re.compile(r"seed|随机种子|随机数种子", re.I)

CHECKLIST_DEF = [
    ("G1", "代码版本"),
    ("G2", "运行环境（硬件/CUDA/框架/Python 版本）"),
    ("G3", "依赖声明"),
    ("G4", "完整命令"),
    ("G5", "数据获取方式"),
    ("G6", "随机种子"),
    ("G7", "预期产物与校验方式"),
]


def norm(text):
    return WS_RE.sub(" ", text.strip())


def parse_flags(text):
    """从命令文本解析 {flag: value or None}；支持 --flag value 与 --flag=value。"""
    tokens = text.split()
    flags = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        m = FLAG_RE.match(tok)
        if m and tok == m.group(0) or (m and "=" in tok):
            name, val = m.group(1), m.group(2)
            if val is None and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                val = tokens[i + 1]
                i += 1
            flags[name] = val
        i += 1
    return flags


def token_set(text):
    return set(text.split())


def cut_at_cjk(text):
    toks = text.split()
    kept = []
    for tok in toks:
        if CJK_RE.search(tok):
            break
        kept.append(tok)
    return " ".join(kept)


def extract_chapter_commands(chapter_text):
    """提取章节中的命令候选：(来源行号, 文本, 提取方式)。"""
    lines = chapter_text.splitlines()
    cands = []
    in_block = False
    for idx, ln in enumerate(lines, start=1):
        if FENCE_RE.match(ln):
            in_block = not in_block
            continue
        s = ln.strip()
        if in_block:
            if s and not s.startswith("#"):
                cand = cut_at_cjk(s)
                if "--" in cand or re.match(r"^(python3?|bash|wget|curl|pip3?)\b", cand):
                    cands.append((idx, cand, "code_block"))
            continue
        # 行内代码 span
        for m in INLINE_CODE_RE.finditer(ln):
            cand = cut_at_cjk(m.group(1).strip())
            if "--" in cand:
                cands.append((idx, cand, "inline_code"))
        # 散文中的命令片段：先定位每个可执行词起点，再截取到行尾并按 CJK 截断
        for m in EXEC_START_RE.finditer(ln):
            seg = ln[m.start(1):]
            cand = cut_at_cjk(seg.strip().rstrip("`"))
            if "--" in cand:
                cands.append((idx, cand, "prose"))
    # 去重（同一行同一文本只保留一次，不论提取方式）
    seen = set()
    uniq = []
    for c in cands:
        key = (c[0], c[1])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def best_match(cand, real_texts):
    """返回 (best_index, score)；score = 公共token数 / 候选token数。"""
    ctoks = token_set(cand)
    best_i, best_s = -1, 0.0
    for i, rt in enumerate(real_texts):
        rtoks = token_set(rt)
        if not ctoks:
            break
        score = len(ctoks & rtoks) / len(ctoks)
        if score > best_s:
            best_i, best_s = i, score
    return best_i, best_s


def main():
    ap = argparse.ArgumentParser(description="复现清单与命令一致性核验")
    ap.add_argument("--chapter", required=True, help="待核验的章节 markdown")
    ap.add_argument("--commands", required=True, help="command_mine.py 产出的 commands.json")
    ap.add_argument("--steps", default=None, help="可选：step_table.py 产出的 steps.md")
    ap.add_argument("--out", required=True, help="输出目录")
    args = ap.parse_args()

    for p, label in ((args.chapter, "章节文件"), (args.commands, "commands.json")):
        if not os.path.isfile(p):
            print("ERROR: 找不到%s: %s" % (label, p), file=sys.stderr)
            return 2
    os.makedirs(args.out, exist_ok=True)

    with open(args.chapter, encoding="utf-8") as f:
        chapter = f.read()
    with open(args.commands, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", [])

    chapter_norm = norm(chapter)
    chapter_low = chapter.lower()

    # 排除"以章节自身为来源"的线索，防止章节用自己的话自我证明
    chap_base = os.path.basename(args.chapter)

    def not_self(it):
        return os.path.basename(it["file"]) != chap_base

    items = [it for it in items if not_self(it)]

    cmds_all = [it for it in items if it["type"] == "command"]
    # 真实命令去重（脚本与日志可能记录同一命令；保留首次出现的来源）
    real_texts, real_srcs, seen = [], [], set()
    for it in cmds_all:
        t = norm(it["text"])
        if t not in seen:
            seen.add(t)
            real_texts.append(t)
            real_srcs.append("%s:%d" % (it["file"], it["line"]))
    env_items = [it for it in items if it["type"] == "env"]
    seed_items = [it for it in items if it["type"] == "seed"]
    dep_items = [it for it in items if it["type"] == "dep"]
    data_items = [it for it in items if it["type"] == "data"]

    checklist = []

    def add(gid, name, status, detail):
        checklist.append({"id": gid, "item": name, "status": status, "detail": detail})

    # G1 代码版本
    if CODE_VERSION_RE.search(chapter):
        add("G1", CHECKLIST_DEF[0][1], "present", "章节提及代码版本/commit/仓库信息。")
    else:
        add("G1", CHECKLIST_DEF[0][1], "missing",
            "章节未写明代码版本（commit/tag/仓库地址）；若材料亦缺失，需标注为人工确认项。")

    # G2 环境：材料中的环境事实是否被章节覆盖
    env_sigs, seen_sig = [], set()
    for it in env_items:
        sig = it["text"]
        key = sig.lower()
        if sig.startswith(("export ", "nvidia-smi")):
            continue  # 整行 shell 语句不适合作为"章节应覆盖"的版本签名
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S+$", sig):
            continue  # 变量赋值（如 CUDA_VISIBLE_DEVICES=0）不要求章节原样引用
        if key not in seen_sig and len(sig) <= 60:
            seen_sig.add(key)
            env_sigs.append((sig, "%s:%d" % (it["file"], it["line"])))
    if not env_sigs:
        add("G2", CHECKLIST_DEF[1][1], "unknown",
            "材料中未发现环境信息（Python/CUDA/GPU 等）；章节需说明此缺口并列为人工确认项。")
    else:
        covered = [s for s, _ in env_sigs if norm(s).lower() in chapter_low]
        missing_env = ["%s（%s）" % (s, src) for s, src in env_sigs
                       if norm(s).lower() not in chapter_low]
        if not missing_env:
            add("G2", CHECKLIST_DEF[1][1], "present",
                "材料中的 %d 条环境线索均在章节中找到。" % len(env_sigs))
        elif covered:
            add("G2", CHECKLIST_DEF[1][1], "missing",
                "部分环境线索未被章节覆盖：%s" % "；".join(missing_env))
        else:
            add("G2", CHECKLIST_DEF[1][1], "missing",
                "章节未覆盖任何材料中的环境线索：%s" % "；".join(
                    "%s（%s）" % (s, src) for s, src in env_sigs))

    # G3 依赖
    if not dep_items:
        add("G3", CHECKLIST_DEF[2][1], "unknown", "材料中未发现依赖声明文件或安装命令。")
    else:
        dep_hits = sorted({it["text"] for it in dep_items
                           if it["text"].split("==")[0].split(">=")[0].strip().lower() in chapter_low})
        if dep_hits or "requirements" in chapter_low or "依赖" in chapter:
            add("G3", CHECKLIST_DEF[2][1], "present",
                "章节提及依赖（命中 %d 条材料依赖线索）。" % len(dep_hits))
        else:
            add("G3", CHECKLIST_DEF[2][1], "missing",
                "材料有 %d 条依赖线索（如 %s），但章节未提及依赖安装方式。"
                % (len(dep_items), dep_items[0]["text"]))

    # G4 完整命令：真实命令是否原样出现在章节
    missing_cmds = ["`%s`（%s）" % (t, src) for t, src in zip(real_texts, real_srcs)
                    if t not in chapter_norm]
    if not real_texts:
        add("G4", CHECKLIST_DEF[3][1], "unknown", "commands.json 中无 command 线索。")
    elif not missing_cmds:
        add("G4", CHECKLIST_DEF[3][1], "present",
            "%d 条真实命令全部原样出现在章节中。" % len(real_texts))
    else:
        add("G4", CHECKLIST_DEF[3][1], "missing",
            "以下真实命令未原样出现在章节中：%s" % "；".join(missing_cmds))

    # G5 数据获取
    if not data_items:
        add("G5", CHECKLIST_DEF[4][1], "unknown", "材料中未发现数据获取方式（下载命令/数据路径）。")
    else:
        data_hits = sorted({norm(it["text"]) for it in data_items if norm(it["text"]) in chapter_norm})
        if data_hits:
            add("G5", CHECKLIST_DEF[4][1], "present",
                "章节覆盖 %d 条数据线索。" % len(data_hits))
        else:
            add("G5", CHECKLIST_DEF[4][1], "missing",
                "材料有数据线索（如 %s，%s:%d），但章节未写明数据获取方式。"
                % (data_items[0]["text"], data_items[0]["file"], data_items[0]["line"]))

    # G6 随机种子
    seed_vals = sorted({it["text"].split("=", 1)[1] for it in seed_items if "=" in it["text"]})
    chapter_mentions_seed = bool(SEED_MENTION_RE.search(chapter))
    if not seed_items:
        if chapter_mentions_seed:
            add("G6", CHECKLIST_DEF[5][1], "present",
                "材料中未发现种子设置，但章节有所说明；请确认说明与材料一致。")
        else:
            add("G6", CHECKLIST_DEF[5][1], "missing",
                "材料与章节均未发现随机种子设置；需在章节中如实标注该缺口并列为人工确认项。")
    else:
        if chapter_mentions_seed and all(v in chapter for v in seed_vals):
            add("G6", CHECKLIST_DEF[5][1], "present",
                "材料中的种子值 %s 均在章节中出现。" % ", ".join(seed_vals))
        else:
            add("G6", CHECKLIST_DEF[5][1], "missing",
                "材料中发现种子 %s（如 %s:%d），但章节未完整写明。"
                % (", ".join(seed_vals), seed_items[0]["file"], seed_items[0]["line"]))

    # G7 预期校验
    if VALIDATE_RE.search(chapter):
        add("G7", CHECKLIST_DEF[6][1], "present", "章节提及预期指标/校验方式。")
    else:
        add("G7", CHECKLIST_DEF[6][1], "missing",
            "章节未写明预期产物或校验方式（指标、阈值、checksum 等）。")

    # ---------------- 命令一致性（逐条比对，防凭记忆改写 flag） ----------------
    findings = []
    cand_cmds = extract_chapter_commands(chapter)
    compared = 0
    ok_count = 0
    for lineno, cand, how in cand_cmds:
        cand_n = norm(cand)
        if not cand_n:
            continue
        compared += 1
        best_i, score = best_match(cand_n, real_texts)
        if best_i >= 0 and cand_n == real_texts[best_i]:
            ok_count += 1
            continue
        if best_i < 0 or score < 0.4:
            findings.append({
                "severity": "FAIL", "kind": "command_unmatched", "line": lineno,
                "chapter_command": cand_n, "extracted_from": how,
                "detail": "章节命令与 commands.json 中任何真实命令均不匹配（最高重合 %.0f%%）；"
                          "疑似凭记忆书写。" % (score * 100),
            })
            continue
        real = real_texts[best_i]
        cf, rf = parse_flags(cand_n), parse_flags(real)
        wrong = {k: (cf[k], rf[k]) for k in cf if k in rf and cf[k] and rf[k] and cf[k] != rf[k]}
        invented = {k: cf[k] for k in cf if k not in rf}
        omitted = {k: rf[k] for k in rf if k not in cf}
        if wrong:
            findings.append({
                "severity": "FAIL", "kind": "flag_value_mismatch", "line": lineno,
                "chapter_command": cand_n, "real_command": real,
                "real_source": real_srcs[best_i],
                "detail": "flag 值被改写：%s"
                          % "；".join("%s 章节=%s 真实=%s" % (k, v[0], v[1]) for k, v in sorted(wrong.items())),
            })
        if invented:
            findings.append({
                "severity": "FAIL", "kind": "flag_invented", "line": lineno,
                "chapter_command": cand_n, "real_command": real,
                "real_source": real_srcs[best_i],
                "detail": "章节出现真实命令中不存在的 flag：%s"
                          % "；".join("%s=%s" % kv for kv in sorted(invented.items())),
            })
        if omitted:
            findings.append({
                "severity": "WARN", "kind": "flag_omitted", "line": lineno,
                "chapter_command": cand_n, "real_command": real,
                "real_source": real_srcs[best_i],
                "detail": "章节命令省略了真实命令中的 flag：%s"
                          % "；".join("%s=%s" % (k, v) for k, v in sorted(omitted.items())),
            })
        if not (wrong or invented):
            ok_count += 1

    # 多步压一句：段落命中 ≥2 条真实命令，且其中至少一条从未以"干净步骤行"
    # （命令几乎独占一行，残余散文极少）的形式出现，才视为压缩嫌疑。
    chapter_lines = [norm(ln) for ln in chapter.splitlines()]

    def has_clean_step_line(cmd_text):
        ctoks = token_set(cmd_text)
        need = 0.6 * max(1, len(ctoks))
        for ln_n in chapter_lines:
            if not ln_n:
                continue
            if len(ctoks & token_set(ln_n)) < need:
                continue
            residual = ln_n
            for tok in cmd_text.split():
                residual = residual.replace(tok, " ", 1)
            cjk = len(CJK_RE.findall(residual))
            other = len([t for t in residual.split() if t.strip("`：:，,。;；")])
            if cjk <= 6 and other <= 3:
                return True
        return False

    for para in re.split(r"\n\s*\n", chapter):
        para_tokens = token_set(norm(para))
        if not para_tokens:
            continue
        hits = [t for t in real_texts
                if len(token_set(t) & para_tokens) >= 0.6 * max(1, len(token_set(t)))]
        if len(hits) >= 2 and any(not has_clean_step_line(h) for h in hits):
            findings.append({
                "severity": "WARN", "kind": "steps_compressed", "line": None,
                "detail": "同一段落命中 %d 条真实命令，且至少一条被压入散文句中（命中：%s）；"
                          "建议拆分为独立步骤并逐条恢复原命令。"
                          % (len(hits), "；".join("`%s`" % h for h in hits[:3])),
            })

    # ---------------- 顺序一致性（章节 vs 日志时间线） ----------------
    log_cmds = sorted([it for it in cmds_all if it["source_kind"] == "log" and it.get("log_time")],
                      key=lambda it: (it["log_time"], it["line"]))
    if log_cmds:
        log_index = {norm(it["text"]): j for j, it in enumerate(log_cmds)}
        seq = []
        for lineno, cand, _how in cand_cmds:
            cand_n = norm(cand)
            best_i, score = best_match(cand_n, list(log_index.keys()) or [""])
            if best_i >= 0 and score >= 0.6:
                seq.append((lineno, best_i, cand_n))
        positions = [p for _, p, _ in seq]
        if positions == sorted(positions):
            order_check = {"status": "ok",
                           "detail": "章节中 %d 条可匹配命令的顺序与日志时间线一致。" % len(seq)}
        else:
            order_check = {"status": "conflict",
                           "detail": "章节命令顺序与日志时间线矛盾：%s"
                                     % "；".join("第%d行的命令在日志时间线位置%d" % (ln, p + 1)
                                                 for ln, p, _ in seq)}
            findings.append({"severity": "FAIL", "kind": "order_conflict", "line": None,
                             "detail": order_check["detail"]})
    else:
        order_check = {"status": "skipped",
                       "detail": "无带时间戳的执行日志，顺序一致性无法自动核验；需人工确认。"}

    has_fail = any(fd["severity"] == "FAIL" for fd in findings)
    has_warn = any(fd["severity"] == "WARN" for fd in findings)
    has_gap = any(c["status"] == "missing" for c in checklist)
    if has_fail:
        status = "FAIL"
    elif has_warn or has_gap:
        status = "WARN"
    else:
        status = "PASS"

    report = {
        "status": status,
        "chapter": args.chapter,
        "commands_source": args.commands,
        "checklist": checklist,
        "command_consistency": {
            "chapter_commands_found": len(cand_cmds),
            "compared": compared,
            "ok": ok_count,
            "real_commands_total": len(real_texts),
        },
        "order_check": order_check,
        "findings": sorted(findings, key=lambda x: (x["severity"] != "FAIL", x.get("line") or 0)),
        "notes": [
            "unknown 表示材料本身缺少该信息，章节应如实标注缺口而非编造。",
            "FAIL 必须修复后方可定稿；WARN 需人工复核。",
        ],
    }

    json_path = os.path.join(args.out, "repro_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md_path = os.path.join(args.out, "repro_report.md")
    sev_icon = {"FAIL": "❌", "WARN": "⚠️", "PASS": "✅"}
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 复现核验报告\n\n")
        f.write("章节：`%s`　总体状态：**%s** %s\n\n" % (args.chapter, status, sev_icon[status]))
        f.write("## 复现清单（G1-G7）\n\n")
        f.write("| 编号 | 检查项 | 状态 | 说明 |\n|---|---|---|---|\n")
        for c in checklist:
            mark = {"present": "✅ present", "missing": "❌ missing", "unknown": "❔ unknown"}[c["status"]]
            f.write("| %s | %s | %s | %s |\n" % (c["id"], c["item"], mark, c["detail"]))
        f.write("\n## 命令一致性\n\n")
        cc = report["command_consistency"]
        f.write("章节中提取命令候选 %d 条，完成比对 %d 条，一致 %d 条；真实命令共 %d 条。\n\n"
                % (cc["chapter_commands_found"], cc["compared"], cc["ok"], cc["real_commands_total"]))
        f.write("## 顺序一致性\n\n- 状态：%s；%s\n\n" % (order_check["status"], order_check["detail"]))
        f.write("## 发现项（%d）\n\n" % len(report["findings"]))
        if not report["findings"]:
            f.write("无。\n")
        for fd in report["findings"]:
            loc = "第%s行" % fd["line"] if fd.get("line") else "全文"
            f.write("- %s **%s** [%s]（%s）：%s\n"
                    % (sev_icon[fd["severity"]], fd["severity"], fd["kind"], loc, fd["detail"]))

    print("repro_check: 状态=%s；清单 missing=%d unknown=%d；发现项 FAIL=%d WARN=%d -> %s / %s"
          % (status,
             sum(1 for c in checklist if c["status"] == "missing"),
             sum(1 for c in checklist if c["status"] == "unknown"),
             sum(1 for fd in findings if fd["severity"] == "FAIL"),
             sum(1 for fd in findings if fd["severity"] == "WARN"),
             json_path, md_path))
    return 1 if has_fail else 0


if __name__ == "__main__":
    sys.exit(main())

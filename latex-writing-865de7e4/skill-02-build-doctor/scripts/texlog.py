#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texlog.py — LaTeX .log 错误签名提取与根因聚类诊断（仅 Python3 标准库）。

职责（只做诊断与建议，绝不改稿）：
  1. 处理日志 79 列包裹，把物理行拼回逻辑行。
  2. 维护文件栈（跟踪 `(` / `)` 开闭文件），把每条 `! ` 错误定位到
     具体文件 + l.行号 + 上下文行。
  3. 错误签名归一化：同一签名的重复出现合并为一个根因；第一个根因之后的
     派生错误按规则标注 cascade-of（级联折叠，不停在第一条错误，也不把
     派生错误误认为独立根因）。
  4. 每个根因给出 file:line、上下文、修复建议（命令/环境 -> 宏包、
     .sty/.cls -> TeX Live 包，查 references/package-map.md；另见
     references/error-signatures.md 的处置表）。
  5. 同时提取 LaTeX Warning（含未定义引用/文献键）作为次级问题。

用法：
  python3 texlog.py --log <main.log> --project <工程目录> \
      --outdir </app/work/diagnosis> [--map <package-map.md>]

输出：diagnosis.json + diagnosis.md（写入 outdir，默认 /app/work/diagnosis）。
退出码：0=解析完成（无论是否有错误）；2=用法错误；5=日志不可读。
"""
import argparse
import json
import os
import re
import sys

MAX_PRINT_LINE = 79

# 强派生签名：只要前面已有更早的根因，这些几乎一定是级联产物
STRONGLY_DERIVED = [
    "Emergency stop",
    "Fatal error occurred",
    "Missing \\begin{document}",
    "There's no line here to end",
    "Extra }, or forgotten $",
    "==> Fatal error",
]
# 弱派生签名：仅当与更早错误同文件且同一条物理行（或上下文提及根因记号）
# 时才判级联——相隔数行的同类错误通常是独立根因，不能误折叠。
WEAKLY_DERIVED = [
    "Missing $ inserted",
    "Missing } inserted",
    "Missing { inserted",
    "Missing number",
    "Illegal unit of measure",
    "Double subscript",
    "Double superscript",
    "Extra alignment tab",
]

RE_LL = re.compile(r"\bl\.(\d+)")
RE_CS = re.compile(r"\\[A-Za-z@]+")
RE_CITE_WARN = re.compile(
    r"LaTeX Warning: Citation `([^']+)' on page (\d+) undefined")
RE_REF_WARN = re.compile(
    r"LaTeX Warning: Reference `([^']+)' on page (\d+) undefined")
RE_FILE_NOT_FOUND = re.compile(r"File `([^']+)' not found")
RE_ENV_UNDEF = re.compile(r"Environment (\S+) undefined")
RE_BIB_KEY = re.compile(r"@[A-Za-z]+\s*\{\s*([^,]+),")


def unwrap_lines(text):
    out, buf = [], ""
    for ln in text.split("\n"):
        buf += ln
        if len(ln) >= MAX_PRINT_LINE:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


# 纯消息行（不含文件开闭结构）的前缀，跳过文件栈更新
MSG_LINE_RE = re.compile(
    r"^(LaTeX|Package |Class |File:|Document Class|Underfull|Overfull|"
    r"Missing character|pdfTeX warning|This is|entering | restricted| %&-)")


def update_file_stack(line, stack):
    """按 TeX 日志的 (path ... ) 结构维护文件栈。
    防御措施：跳过纯消息行；栈底（主文件）永不弹出——错误上下文与
    "(Font)" 类消息里的括号不应破坏栈结构。"""
    if MSG_LINE_RE.match(line) or " on input line " in line:
        return
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c == "(":
            j = i + 1
            while j < n and line[j] not in " \t()":
                j += 1
            token = line[i + 1:j].strip('"').lstrip("*")
            if token and ("/" in token or re.search(r"\.\w{2,5}$", token)):
                stack.append(token)
            i = max(j, i + 1)
        elif c == ")":
            if len(stack) > 1:
                stack.pop()
            i += 1
        else:
            i += 1


def resolve_file(token, project):
    """把栈顶路径映射为工程内相对路径；系统文件保留基名并标注。"""
    if not token:
        return None, None
    tok = token[2:] if token.startswith("./") else token
    cand = os.path.join(project, tok)
    if os.path.exists(cand):
        return os.path.relpath(cand, project), "project"
    if os.path.isabs(tok) and tok.startswith(os.path.abspath(project) + os.sep):
        return os.path.relpath(tok, project), "project"
    return os.path.basename(tok), "system"


def normalize_signature(message, token):
    sig = re.sub(r"\d+", "#", message.strip())
    return sig + (" | cs=" + token if token else "")


def load_package_map(map_path):
    """解析 references/package-map.md 的三张表：命令/环境/文件 -> 宏包/TeX Live 包。"""
    maps = {"cmd": {}, "env": {}, "file": {}}
    if not map_path or not os.path.exists(map_path):
        return maps
    section = None
    with open(map_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("#"):
                if "命令" in s:
                    section = "cmd"
                elif "环境" in s:
                    section = "env"
                elif "文件" in s or "sty" in s or "cls" in s:
                    section = "file"
                continue
            if not (s.startswith("|") and section):
                continue
            cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("命令", "环境", "文件", "---", ":---"):
                continue
            if set(cells[0]) <= set("-: "):
                continue
            maps[section][cells[0]] = {"package": cells[1],
                                       "note": cells[2] if len(cells) > 2 else ""}
    return maps


def find_usage_in_project(project, fname):
    """在工程 .tex 中找引用该 .sty/.cls 的 file:line（确定性机械搜索）。"""
    stem = re.escape(re.sub(r"\.(sty|cls)$", "", fname))
    pat = re.compile(r"\\(?:usepackage|RequirePackage|documentclass)"
                     r"(?:\[[^\]]*\])?\s*\{[^}]*\b" + stem + r"\b")
    for root, _dirs, files in os.walk(project):
        for fn in sorted(files):
            if not fn.endswith(".tex"):
                continue
            p = os.path.join(root, fn)
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    for n, line in enumerate(f, 1):
                        if pat.search(line):
                            return "%s:%d" % (os.path.relpath(p, project), n)
            except OSError:
                continue
    return None


def suggest_for(message, token, context, maps, bib_keys, project):
    msg = message
    ctx = "\n".join(context)
    m = RE_FILE_NOT_FOUND.search(msg)
    if m:
        fname = m.group(1)
        usage = find_usage_in_project(project, fname)
        where = ("引用位置：%s。" % usage) if usage else ""
        hit = maps["file"].get(fname)
        if hit:
            return ("缺少文件 %s。%s映射表记录 → TeX Live 包 %s（%s）。"
                    "请安装该包，或改用已安装的等价宏包。"
                    % (fname, where, hit["package"], hit["note"]))
        return ("缺少文件 %s。%s该宏包/类未安装：用 tlmgr install <包名> 安装，"
                "或删除/替换对应 \\usepackage/\\documentclass。" % (fname, where))
    if "Undefined control sequence" in msg:
        if token and token in maps["cmd"]:
            hit = maps["cmd"][token]
            return ("未定义命令 %s：通常由宏包 %s 提供（%s）。请在导言区 "
                    "\\usepackage{%s}，或改用已加载宏包的等价命令。"
                    % (token, hit["package"], hit["note"], hit["package"]))
        return ("未定义命令 %s：检查拼写；若来自某宏包请补 \\usepackage；"
                "若是自定义命令请补 \\newcommand 定义（查 package-map.md）。"
                % (token or "<未知>"))
    m = RE_ENV_UNDEF.search(msg)
    if m:
        env = m.group(1)
        hit = maps["env"].get(env)
        if hit:
            return ("环境 %s 未定义：由宏包 %s 提供（%s），请补 \\usepackage{%s}。"
                    % (env, hit["package"], hit["note"], hit["package"]))
        return ("环境 %s 未定义：查 package-map.md 确认提供它的宏包并补 "
                "\\usepackage，或检查环境名拼写。" % env)
    if "Missing $ inserted" in msg or "Missing }" in msg or "Missing {" in msg:
        return ("数学模式/花括号不配平：检查该行 $...$ 定界与 { } 配对"
                "（常见为上下标 {n} 少写右括号）。上下文：%s"
                % (ctx.strip().splitlines()[0] if ctx.strip() else "<无>"))
    if "Citation" in msg and "undefined" in msg:
        m2 = re.search(r"Citation `([^']+)'", msg)
        key = m2.group(1) if m2 else "?"
        known = ("；.bib 中现有键：%s" % ", ".join(sorted(bib_keys))
                 if bib_keys else "；未找到 .bib 或其中无任何条目")
        return ("文献键 `%s' 未定义：核对 \\cite 拼写与 .bib 条目键名%s。"
                % (key, known))
    return "对照 references/error-signatures.md 中该签名的处置建议修复。"


def parse_log(log_path, project):
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    merged = unwrap_lines(text)

    # 第一遍：圈定错误上下文块（"! " 行到其后第一个真正的空行之间），
    # 这些行里的括号是消息文本，不参与文件栈更新。
    in_error_ctx = [False] * len(merged)
    i = 0
    while i < len(merged):
        if merged[i].startswith("! "):
            in_error_ctx[i] = True
            j = i + 1
            while j < len(merged) and merged[j] != "":
                in_error_ctx[j] = True
                j += 1
            i = j
        else:
            i += 1

    stack = []
    stack_at = []  # stack_at[i] = 处理完第 i 行后的栈快照
    for idx, ln in enumerate(merged):
        if not in_error_ctx[idx]:
            update_file_stack(ln, stack)
        stack_at.append(list(stack))

    errors = []
    warnings = []
    i = 0
    while i < len(merged):
        ln = merged[i]
        if ln.startswith("! "):
            message = ln[2:].strip()
            context = []
            lineno = None
            l_line = ""
            j = i + 1
            while j < len(merged) and merged[j] != "" and len(context) < 12:
                context.append(merged[j])
                m = RE_LL.search(merged[j])
                if m and lineno is None:
                    lineno = int(m.group(1))
                    l_line = merged[j]
                j += 1
            tok = None
            if l_line:
                # 取 l. 行内容（行号之后）的最后一个控制序列作为出错记号
                body = re.sub(r"^\s*l\.\d+\s*", "", l_line)
                cs = RE_CS.findall(body)
                tok = cs[-1] if cs else None
            file_token = stack_at[i - 1][-1] if i > 0 and stack_at[i - 1] else None
            rel, kind = resolve_file(file_token, project)
            errors.append({
                "message": message,
                "token": tok,
                "file": rel,
                "file_kind": kind,
                "line": lineno,
                "context": context[:6],
                "order": len(errors),
            })
            i = j
            continue
        if "LaTeX Warning:" in ln or "Package biblatex Warning:" in ln:
            warnings.append(ln.strip())
        i += 1
    return errors, warnings


def cluster(errors, warnings):
    """同签名合并；排序后判定 cascade-of。"""
    clusters = {}
    order = []
    for e in errors:
        sig = normalize_signature(e["message"], e["token"])
        if sig not in clusters:
            clusters[sig] = {
                "signature": sig,
                "message": e["message"],
                "token": e["token"],
                "count": 0,
                "occurrences": [],
                "first_order": e["order"],
            }
            order.append(sig)
        c = clusters[sig]
        c["count"] += 1
        c["occurrences"].append({"file": e["file"], "line": e["line"],
                                 "file_kind": e["file_kind"],
                                 "context": e["context"]})
    # 未定义引用/文献键 warning 提升为次级根因条目
    warn_items = []
    for w in warnings:
        m = RE_CITE_WARN.search(w) or RE_REF_WARN.search(w)
        if m:
            kind = "citation" if "Citation" in w else "reference"
            sig = "%s-undefined|%s" % (kind, m.group(1))
            if sig not in clusters:
                lm = re.search(r"on input line (\d+)", w)
                clusters[sig] = {
                    "signature": sig,
                    "message": w,
                    "token": m.group(1),
                    "count": 0,
                    "occurrences": [{"file": None,
                                     "line": int(lm.group(1)) if lm else None,
                                     "file_kind": None, "context": []}],
                    "first_order": len(order) + 1000,
                    "severity": "warning",
                }
                order.append(sig)
            clusters[sig]["count"] += 1

    ordered = sorted(order, key=lambda s: clusters[s]["first_order"])
    roots = []
    for idx, sig in enumerate(ordered):
        c = clusters[sig]
        first = c["occurrences"][0] if c["occurrences"] else {}
        item = {
            "id": "R%d" % (len(roots) + 1),
            "signature": c["signature"],
            "message": c["message"],
            "token": c["token"],
            "count": c["count"],
            "severity": c.get("severity", "error"),
            "file": first.get("file"),
            "line": first.get("line"),
            "file_kind": first.get("file_kind"),
            "context": first.get("context", []),
            "cascade_of": None,
            "suggestion": None,
        }
        if idx > 0:
            cause = None
            for prev in roots:
                if prev["severity"] != "error":
                    continue
                same_file = item["file"] and prev["file"] == item["file"]
                near = (same_file and item["line"] and prev["line"]
                        and abs(item["line"] - prev["line"]) == 0)
                mentions = (prev["token"] and prev["token"] in item["message"]) or \
                           (prev["token"] and prev["token"] in
                            "\n".join(item["context"]))
                if any(item["message"].startswith(p) for p in STRONGLY_DERIVED):
                    cause = prev["id"]
                    break
                if any(item["message"].startswith(p) for p in WEAKLY_DERIVED) and near:
                    cause = prev["id"]
                    break
                if mentions:
                    cause = prev["id"]
                    break
            item["cascade_of"] = cause
        roots.append(item)
    return roots, warnings


def main():
    ap = argparse.ArgumentParser(description="LaTeX 日志错误签名提取与根因聚类")
    ap.add_argument("--log", required=True, help=".log 文件路径")
    ap.add_argument("--project", required=True, help="LaTeX 工程目录（定位文件用）")
    ap.add_argument("--outdir", default="/app/work/diagnosis", help="诊断输出目录")
    ap.add_argument("--map", default=None,
                    help="references/package-map.md 路径（缺省时跳过宏包建议映射）")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    if not os.path.exists(args.log):
        sys.stderr.write("[texlog] 日志不可读：%s\n" % args.log)
        return 5
    os.makedirs(args.outdir, exist_ok=True)
    maps = load_package_map(args.map)

    # .bib 键清单（用于未定义引用建议）
    bib_keys = set()
    for root, _dirs, files in os.walk(project):
        for fn in files:
            if fn.endswith(".bib"):
                with open(os.path.join(root, fn), "r",
                          encoding="utf-8", errors="replace") as f:
                    bib_keys.update(RE_BIB_KEY.findall(f.read()))

    errors, warnings = parse_log(args.log, project)
    roots, warnings = cluster(errors, warnings)
    for r in roots:
        r["suggestion"] = suggest_for(r["message"], r["token"], r["context"],
                                      maps, bib_keys, project)

    n_err_roots = sum(1 for r in roots if r["severity"] == "error")
    n_cascade = sum(1 for r in roots if r["cascade_of"])
    diag = {
        "tool": "texlog.py",
        "log": os.path.abspath(args.log),
        "project": project,
        "summary": {
            "error_occurrences": len(errors),
            "distinct_root_causes": n_err_roots,
            "cascade_errors": n_cascade,
            "warning_items": sum(1 for r in roots if r["severity"] == "warning"),
            "warnings_total": len(warnings),
        },
        "root_causes": roots,
        "warnings": warnings[:200],
        "note": "本诊断只给建议（suggestions），不修改任何源文件；修复由 Agent "
                "理解任务后决定并执行。",
    }
    jpath = os.path.join(args.outdir, "diagnosis.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(diag, f, ensure_ascii=False, indent=2)

    lines = ["# LaTeX 编译诊断报告", "",
             "- 日志：`%s`" % os.path.abspath(args.log),
             "- 工程：`%s`" % project,
             "- 错误出现次数：%d；独立根因：%d；级联派生：%d；警告级问题：%d"
             % (len(errors), n_err_roots, n_cascade,
                diag["summary"]["warning_items"]),
             "",
             "> 本报告只给建议，不改稿；修复由 Agent 决定并执行。", ""]
    for r in roots:
        head = "## %s [%s] %s" % (r["id"], r["severity"], r["message"])
        if r["cascade_of"]:
            head += "（cascade-of %s）" % r["cascade_of"]
        lines.append(head)
        lines.append("")
        lines.append("- 位置：`%s:%s`%s" % (
            r["file"] or "?", r["line"] if r["line"] is not None else "?",
            "（系统/宏包文件）" if r["file_kind"] == "system" else ""))
        lines.append("- 出现次数：%d" % r["count"])
        if r["context"]:
            lines.append("- 上下文：")
            lines.append("  ```")
            lines.extend("  " + c for c in r["context"])
            lines.append("  ```")
        lines.append("- 建议：%s" % r["suggestion"])
        lines.append("")
    if warnings:
        lines.append("## 警告清单（前 30 条）")
        lines.append("")
        lines.extend("- %s" % w for w in warnings[:30])
        lines.append("")
    mpath = os.path.join(args.outdir, "diagnosis.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    sys.stdout.write(json.dumps({"diagnosis_json": jpath,
                                 "diagnosis_md": mpath,
                                 "summary": diag["summary"]},
                                ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

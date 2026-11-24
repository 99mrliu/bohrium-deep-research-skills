#!/usr/bin/env python3
"""Build the handoff package in OUT_DIR:

  manifest.json   input->deliverable mapping with completeness self-check
  INDEX.md        human-readable overview
  index.html      self-contained HTML twin of INDEX
  metadata.csv    per-file metadata table
  tree.md         directory tree + version families
  structure.svg   editable vector diagram of the library
  answers.json    machine-readable answers (copied from work)

Usage: handoff_build.py CASE_JSON WORK_DIR OUT_DIR
"""
import html
import json
import os
import sys


def load(work, name, default):
    p = os.path.join(work, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return default
    return default


def esc(s):
    return html.escape(str(s), quote=True)


def main():
    case_p, work, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    case = json.load(open(case_p, encoding="utf-8"))
    scan = load(work, "scan.json", {})
    answers = load(work, "answers.json", {}).get("answers", [])
    files = scan.get("files", [])
    root = scan.get("library_root")
    cid = scan.get("case_id") or case.get("case_id") or "unknown"

    # manifest with completeness self-check: each input exactly once
    entries, seen = [], set()
    for i, e in enumerate(files):
        fid = "F%02d" % (i + 1)
        seen.add(e["path"])
        entries.append({"id": fid, "input_path": e["path"],
                        "status": e["status"], "version_tag": e["version_tag"],
                        "sha16": e["sha16"],
                        "deliverable_refs": ["metadata.csv", "INDEX.md",
                                             "structure.svg"]})
    completeness = {"n_inputs": len(files), "n_mapped": len(entries),
                    "ok": len(files) == len(set(seen)) == len(entries),
                    "duplicates": sorted(p for p in seen
                                         if [e["input_path"] for e in
                                             entries].count(p) > 1)}
    manifest = {"case_id": cid, "library_root": root, "entries": entries,
                "completeness": completeness}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # metadata.csv
    with open(os.path.join(out_dir, "metadata.csv"), "w", encoding="utf-8") as f:
        f.write("id,path,ext,size,mtime,version_tag,sha16,status\n")
        for ent, e in zip(entries, files):
            f.write("%s,%s,%s,%s,%s,%s,%s,%s\n" % (
                ent["id"], '"%s"' % e["path"].replace('"', '""'), e["ext"],
                e.get("size"), e.get("mtime"), e.get("version_tag", ""),
                e.get("sha16"), e["status"]))

    # tree.md: directory tree + version families
    tree_lines = ["# 目录树与版本族", "", "```"]
    dirs = {}
    for e in files:
        dirs.setdefault(os.path.dirname(e["path"]) or ".", []).append(
            os.path.basename(e["path"]))
    for d in sorted(dirs):
        tree_lines.append("%s/" % d)
        for n in sorted(dirs[d]):
            tree_lines.append("  %s" % n)
    tree_lines += ["```", "", "## 版本族（同规范名归并）", ""]
    fams = {}
    for e in files:
        base = os.path.splitext(os.path.basename(e["path"]))[0]
        for w in ("终稿", "正式版", "定稿", "修订", "初稿", "草稿",
                  "_副本", "副本", "备份"):
            base = base.replace(w, "")
        import re as _re
        base = _re.sub(r"[vV]\d+", "", base).strip("_- .")
        fams.setdefault(base, []).append(
            "%s(%s)" % (e["path"], e["version_tag"] or "无标记"))
    for fam, members in sorted(fams.items()):
        tree_lines.append("- **%s**：%s" % (fam, "；".join(members)))
    with open(os.path.join(out_dir, "tree.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(tree_lines) + "\n")

    # INDEX.md
    idx = ["# 交付总览（case %s）" % cid, "",
           "- 库根目录：`%s`" % root,
           "- 文件 %d 个；完整性自检：%s" % (
               len(files), "通过" if completeness["ok"] else "未通过"),
           "", "## 提问与回答", ""]
    for a in answers:
        idx.append("### %s" % a.get("question"))
        if a["status"] == "answered":
            for h in a["hits"]:
                idx.append("- `%s`（命中词：%s）%s" % (
                    h["file"], ",".join(h["matched_terms"]),
                    ("— " + h["snippet"]) if h["snippet"] else ""))
        else:
            idx.append("- **no_match**：检索词 %s 在库内无命中" %
                       a.get("searched_terms"))
        idx.append("")
    idx += ["## 异常与不可读文件", ""]
    bad = [e for e in files if e["status"] != "ok"]
    idx += (["- `%s`：%s" % (e["path"], e["status"]) for e in bad]
            or ["- 无"])
    idx += ["", "## 文件编号对照（预览图图例）", ""]
    idx += ["- %s = `%s`" % (ent["id"], ent["input_path"]) for ent in entries]
    with open(os.path.join(out_dir, "INDEX.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx) + "\n")

    # self-contained index.html
    body = ["<h1>交付总览（case %s）</h1>" % esc(cid),
            "<p>库根目录：<code>%s</code>；文件 %d 个；完整性自检：%s</p>" % (
                esc(root), len(files),
                "通过" if completeness["ok"] else "未通过"),
            "<h2>提问与回答</h2>"]
    for a in answers:
        body.append("<h3>%s</h3><ul>" % esc(a.get("question")))
        if a["status"] == "answered":
            for h in a["hits"]:
                body.append("<li><code>%s</code>（命中词：%s）%s</li>" % (
                    esc(h["file"]), esc(",".join(h["matched_terms"])),
                    esc(("— " + h["snippet"]) if h["snippet"] else "")))
        else:
            body.append("<li><b>no_match</b>：检索词 %s 无命中</li>" %
                        esc(a.get("searched_terms")))
        body.append("</ul>")
    body.append("<h2>元数据</h2><table border='1'><tr><th>id</th><th>path</th>"
                "<th>ext</th><th>size</th><th>version</th><th>sha16</th></tr>")
    for ent, e in zip(entries, files):
        body.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                    "<td>%s</td><td>%s</td></tr>" % (
                        ent["id"], esc(e["path"]), esc(e["ext"]),
                        e.get("size"), esc(e.get("version_tag", "")),
                        e.get("sha16")))
    body.append("</table>")
    page = ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
            "<title>handoff %s</title></head><body>%s</body></html>"
            % (esc(cid), "\n".join(body)))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    # structure.svg: one box per file, grouped rows, version edges
    width, row_h = 640, 26
    height = 60 + row_h * (len(entries) + 1)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">'
           % (width, height),
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="10" y="22" font-size="14">library structure: %s</text>'
           % esc(cid)]
    y = 44
    prev_by_family = {}
    for ent, e in zip(entries, files):
        svg.append('<rect x="10" y="%d" width="70" height="18" fill="#def" '
                   'stroke="#369"/>' % y)
        svg.append('<text x="14" y="%d" font-size="11">%s</text>'
                   % (y + 13, ent["id"]))
        svg.append('<text x="90" y="%d" font-size="11">%s</text>'
                   % (y + 13, esc(os.path.basename(e["path"])[:40])))
        fam = os.path.splitext(os.path.basename(e["path"]))[0]
        key = "".join(ch for ch in fam if ch.isalnum())[:6]
        if key in prev_by_family:
            py = prev_by_family[key]
            svg.append('<line x1="45" y1="%d" x2="45" y2="%d" stroke="#c33" '
                       'stroke-dasharray="3,2"/>' % (py + 18, y))
        prev_by_family[key] = y
        y += row_h
    svg.append('</svg>')
    with open(os.path.join(out_dir, "structure.svg"), "w", encoding="utf-8") as f:
        f.write("\n".join(svg))

    with open(os.path.join(out_dir, "answers.json"), "w", encoding="utf-8") as f:
        json.dump({"answers": answers}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"entries": len(entries),
                      "completeness_ok": completeness["ok"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

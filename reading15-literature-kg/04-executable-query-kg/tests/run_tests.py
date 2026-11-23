#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests.py — 验收测试 + 负向测试（仅标准库 unittest，全部真实执行）。

运行：python3 tests/run_tests.py   （退出码 0 = 全部通过）

覆盖：
  A. 验收（查询驱动构建）：对 examples/minimal 的 SYNTHETIC 合成示例跑完整流水线，
     断言节点/边规模、7 条查询的真实状态（含 1 条真实无结果、1 条单源跨源为空）、
     两跳路径内容、快照核对一致。
  B. 负向-证据损坏：改字 quote、错误 paragraph_id、未声明 source_id、PDF 页码字段，
     校验必须失败且错误信息明确。
  C. 负向-缺失节点/路径：node_lookup 不存在概念 → empty；不连通节点 shortest_path → empty。
  D. 负向-非法算子：未知 op → error/unknown_operator（拒绝而非静默为空）。
  E. 负向-重跑失配检测：改动查询后 --check 退出 3；不带 --force 重跑退出 4；
     --force 重跑成功且快照如实记录 rerun_after_mismatch。
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
EXAMPLE = os.path.join(ROOT, "examples", "minimal")
sys.path.insert(0, SCRIPTS)

import kg_engine  # noqa: E402
import kg_validate  # noqa: E402
from kg_loader import load_graph  # noqa: E402


def run_script(name, args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, name)] + args,
        capture_output=True, text=True)


class TestAcceptance(unittest.TestCase):
    """A. 合成示例端到端验收（查询驱动：断言每个验收查询的真实结果）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kg04-acc-")
        cls.out = os.path.join(cls.tmp, "out")
        cls.work = os.path.join(cls.tmp, "work")
        proc = run_script("run_all.py", [
            "--case", os.path.join(EXAMPLE, "materials", "case.json"),
            "--input-dir", os.path.join(EXAMPLE, "materials"),
            "--work", cls.work, "--out", cls.out,
            "--graph", os.path.join(EXAMPLE, "graph.candidate.json"),
            "--queries", os.path.join(EXAMPLE, "queries.json"),
            "--label", "SYNTHETIC"])
        cls.proc = proc
        cls.qr = json.load(open(os.path.join(cls.out, "query_results.json"),
                                encoding="utf-8"))
        cls.by_id = {r["id"]: r for r in cls.qr["results"]}

    def test_pipeline_exit_ok(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_graph_scale(self):
        g = load_graph(os.path.join(self.out, "graph.json"))
        c = g.counts()
        self.assertGreaterEqual(c["nodes"], 10)
        self.assertGreaterEqual(c["edges"], 10)
        self.assertEqual(c["sources"], 2)
        merges = [d for d in g.merge_decisions if d["decision"] == "merge"]
        nomerges = [d for d in g.merge_decisions if d["decision"] == "no_merge"]
        self.assertGreaterEqual(len(merges), 1)
        self.assertGreaterEqual(len(nomerges), 1)

    def test_validation_report(self):
        vr = json.load(open(os.path.join(self.out, "validation_report.json"),
                            encoding="utf-8"))
        self.assertTrue(vr["ok"])
        self.assertGreaterEqual(vr["checked_evidence"], 25)  # 14 节点证据 + 12 边证据 = 26

    def test_query_count_and_statuses(self):
        self.assertGreaterEqual(len(self.by_id), 4)
        statuses = {r["status"] for r in self.qr["results"]}
        self.assertIn("ok", statuses)
        self.assertIn("empty", statuses)  # 必须含真实无结果
        self.assertNotIn("error", statuses)

    def test_typed_two_hop_path(self):
        q3 = self.by_id["Q3"]
        self.assertEqual(q3["status"], "ok")
        self.assertEqual(q3["path"]["length"], 2)
        self.assertEqual([n["id"] for n in q3["path"]["nodes"]],
                         ["n:spin-coating", "n:cvd", "n:stability"])
        rels = [e["relation"] for e in q3["path"]["edges"]]
        self.assertEqual(rels, ["优于", "促进"])

    def test_true_no_result(self):
        q5 = self.by_id["Q5"]
        self.assertEqual(q5["status"], "empty")
        self.assertEqual(q5["matches"], [])
        self.assertIn("未找到", q5["reason"])

    def test_cross_source_ok_and_single_source_empty(self):
        q4 = self.by_id["Q4"]
        self.assertEqual(q4["status"], "ok")
        self.assertEqual(q4["sources"], ["S1", "S2"])
        q7 = self.by_id["Q7"]
        self.assertEqual(q7["status"], "empty")
        self.assertIn("只来自 1 个来源", q7["reason"])

    def test_explain_present(self):
        for r in self.qr["results"]:
            self.assertIn("explain", r, r["id"])
        self.assertIn("relation_rule", self.by_id["Q2"]["explain"])

    def test_result_json_contract_mirror(self):
        res = json.load(open(os.path.join(self.out, "result.json"), encoding="utf-8"))
        self.assertEqual(res["case_id"], "SYNTHETIC-MINIMAL-EXAMPLE")
        for key in ("graph", "queries", "evidence_check", "merge_report", "preview"):
            self.assertIn(key, res["output_contract"])
            self.assertEqual(res["output_contract"][key]["status"], "done")
        self.assertEqual(res["label"], "SYNTHETIC")

    def test_snapshot_check_consistent(self):
        proc = run_script("run_queries.py", [
            "--graph", os.path.join(EXAMPLE, "graph.candidate.json"),
            "--queries", os.path.join(EXAMPLE, "queries.json"),
            "--out-dir", self.out, "--check"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_svg_wellformed_and_labeled(self):
        import xml.etree.ElementTree as ET
        svg = open(os.path.join(self.out, "graph.svg"), encoding="utf-8").read()
        ET.fromstring(svg)
        for token in ("二氧化钛", "旋涂法", "优于", "graph_hash"):
            self.assertIn(token, svg)


class TestBrokenEvidence(unittest.TestCase):
    """B. 负向：证据损坏必须被校验器拒绝。"""

    def _broken(self, mutate):
        g = json.load(open(os.path.join(EXAMPLE, "graph.candidate.json"),
                           encoding="utf-8"))
        mutate(g)
        tmp = tempfile.mkdtemp(prefix="kg04-neg-")
        path = os.path.join(tmp, "g.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(g, f, ensure_ascii=False)
        mats = [os.path.join(EXAMPLE, "materials", n)
                for n in ("primary-material.json", "secondary-material.json")]
        ok, report = kg_validate.validate(path, mats)
        return ok, report

    def test_altered_quote_rejected(self):
        def m(g):
            g["nodes"][0]["evidence"][0]["quote"] = "二氧化钛电子传输层【篡改】"
        ok, rep = self._broken(m)
        self.assertFalse(ok)
        self.assertTrue(any("精确子串" in e for e in rep["errors"]), rep["errors"])

    def test_wrong_paragraph_id_rejected(self):
        def m(g):
            g["nodes"][0]["evidence"][0]["paragraph_id"] = "p-zzz-不存在"
        ok, rep = self._broken(m)
        self.assertFalse(ok)
        self.assertTrue(any("不存在" in e for e in rep["errors"]), rep["errors"])

    def test_undeclared_source_rejected(self):
        def m(g):
            g["edges"][0]["evidence"][0]["source_id"] = "S9"
        ok, rep = self._broken(m)
        self.assertFalse(ok)
        self.assertTrue(any("未在 sources 中声明" in e for e in rep["errors"]))

    def test_pdf_page_field_rejected(self):
        def m(g):
            g["nodes"][1]["evidence"][0]["page"] = 3
        ok, rep = self._broken(m)
        self.assertFalse(ok)
        self.assertTrue(any("PDF 页码" in e for e in rep["errors"]))

    def test_cross_source_file_mismatch_rejected(self):
        """把 S2 的段落挂到 S1 的 source_id 上必须被发现。"""
        def m(g):
            g["nodes"][0]["evidence"][1] = {
                "source_id": "S1", "paragraph_id": "p-b-1", "quote": "二氧化钛薄膜"}
        ok, rep = self._broken(m)
        self.assertFalse(ok)
        self.assertTrue(any("实际出自" in e for e in rep["errors"]), rep["errors"])


class TestMissingNodePath(unittest.TestCase):
    """C. 负向：缺失节点与不连通路径必须诚实为空。"""

    @classmethod
    def setUpClass(cls):
        cls.g = load_graph(os.path.join(EXAMPLE, "graph.candidate.json"))

    def test_missing_node_lookup_empty(self):
        r = kg_engine.run_query(self.g, {"id": "n1", "op": "node_lookup",
                                         "params": {"name": "不存在的材料XYZ"}})
        self.assertEqual(r["status"], "empty")

    def test_missing_neighborhood_node_empty(self):
        r = kg_engine.run_query(self.g, {"id": "n2", "op": "neighborhood",
                                         "params": {"node": "n:ghost"}})
        self.assertEqual(r["status"], "empty")
        self.assertIn("不存在", r["reason"])

    def test_disconnected_shortest_path_empty(self):
        tiny = {
            "nodes": [
                {"id": "a", "type": "Material", "name": "甲",
                 "evidence": [{"source_id": "S1", "paragraph_id": "p", "quote": "甲"}]},
                {"id": "b", "type": "Material", "name": "乙",
                 "evidence": [{"source_id": "S1", "paragraph_id": "p", "quote": "乙"}]},
            ],
            "edges": [],
            "sources": [{"source_id": "S1"}],
            "merge_decisions": [],
        }
        tmp = tempfile.mkdtemp(prefix="kg04-disc-")
        p = os.path.join(tmp, "tiny.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(tiny, f, ensure_ascii=False)
        g = load_graph(p)
        r = kg_engine.run_query(g, {"id": "n3", "op": "shortest_path",
                                    "params": {"from": "a", "to": "b"}})
        self.assertEqual(r["status"], "empty")
        self.assertIn("不存在路径", r["reason"])

    def test_missing_path_endpoint_empty(self):
        r = kg_engine.run_query(self.g, {"id": "n4", "op": "shortest_path",
                                         "params": {"from": "n:tio2", "to": "n:ghost"}})
        self.assertEqual(r["status"], "empty")
        self.assertIn("终点缺失", r["reason"])


class TestInvalidOperator(unittest.TestCase):
    """D. 负向：未知算子被诚实拒绝。"""

    def test_unknown_operator_rejected(self):
        g = load_graph(os.path.join(EXAMPLE, "graph.candidate.json"))
        r = kg_engine.run_query(g, {"id": "bad", "op": "frob", "params": {}})
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["error"], "unknown_operator")
        self.assertIn("拒绝执行", r["detail"])

    def test_bad_param_direction(self):
        g = load_graph(os.path.join(EXAMPLE, "graph.candidate.json"))
        r = kg_engine.run_query(g, {"id": "bad2", "op": "neighborhood",
                                    "params": {"node": "n:tio2", "direction": "sideways"}})
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["error"], "bad_param")


class TestRerunMismatch(unittest.TestCase):
    """E. 负向：查询/图谱改动后的重跑失配检测。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kg04-rerun-")
        self.out = os.path.join(self.tmp, "out")
        self.graph = os.path.join(EXAMPLE, "graph.candidate.json")
        self.queries = os.path.join(self.tmp, "queries.json")
        with open(os.path.join(EXAMPLE, "queries.json"), encoding="utf-8") as f:
            self.qdoc = json.load(f)
        with open(self.queries, "w", encoding="utf-8") as f:
            json.dump(self.qdoc, f, ensure_ascii=False)
        proc = run_script("run_queries.py", ["--graph", self.graph,
                                             "--queries", self.queries,
                                             "--out-dir", self.out])
        assert proc.returncode == 0, proc.stderr

    def _mutate_queries(self):
        doc = copy.deepcopy(self.qdoc)
        doc["queries"][0]["params"]["name"] = "改动后的查询名"
        with open(self.queries, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

    def test_full_mismatch_flow(self):
        self._mutate_queries()
        # 1) --check 必须退出 3
        p1 = run_script("run_queries.py", ["--graph", self.graph,
                                           "--queries", self.queries,
                                           "--out-dir", self.out, "--check"])
        self.assertEqual(p1.returncode, 3, p1.stderr)
        self.assertIn("失配", p1.stderr)
        # 2) 不带 --force 重跑必须退出 4（拒绝悄悄覆盖）
        p2 = run_script("run_queries.py", ["--graph", self.graph,
                                           "--queries", self.queries,
                                           "--out-dir", self.out])
        self.assertEqual(p2.returncode, 4, p2.stderr)
        # 3) --force 重跑成功且快照如实记录
        p3 = run_script("run_queries.py", ["--graph", self.graph,
                                           "--queries", self.queries,
                                           "--out-dir", self.out, "--force"])
        self.assertEqual(p3.returncode, 0, p3.stderr)
        with open(os.path.join(self.out, "query_snapshot.json"), encoding="utf-8") as f:
            snap = json.load(f)
        self.assertTrue(snap.get("rerun_after_mismatch"))
        self.assertIn("previous_snapshot_hash", snap)
        self.assertIn("mismatch_items", snap)
        # 4) 重跑后 --check 恢复一致
        p4 = run_script("run_queries.py", ["--graph", self.graph,
                                           "--queries", self.queries,
                                           "--out-dir", self.out, "--check"])
        self.assertEqual(p4.returncode, 0, p4.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

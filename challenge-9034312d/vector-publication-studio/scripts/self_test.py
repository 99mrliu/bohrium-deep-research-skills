#!/usr/bin/env python3
"""Stdlib regression tests: determinism, automatic ranks, byte preservation, negative inputs."""
from __future__ import annotations
import argparse, copy, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
import studio
from patch_svg import patch, PatchError

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--example-dir",required=True); p.add_argument("--report",required=True); a=p.parse_args(argv)
    tests=[]
    try:
        example=Path(a.example_dir).resolve(); spec=studio.load_json(example/"input"/"source_spec.json")
        with tempfile.TemporaryDirectory(prefix="vps-self-test-") as td:
            root=Path(td); one=root/"one"; two=root/"two"; one.mkdir(); two.mkdir()
            svg1,_=studio.build_svg(spec,example/"input",one); svg1=svg1.replace("<defs>",studio.STYLE+"<defs>",1)
            svg2,_=studio.build_svg(spec,example/"input",two); svg2=svg2.replace("<defs>",studio.STYLE+"<defs>",1)
            assert svg1==svg2,"SVG differs across identical runs"
            tests.append({"test":"deterministic_svg","status":"pass","sha256":hashlib.sha256(svg1.encode()).hexdigest()})
            cli_hashes=[]
            for seed,folder in (("1",root/"seed-one"),("2",root/"seed-two")):
                env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONDONTWRITEBYTECODE="1")
                subprocess.run([sys.executable,str(Path(__file__).with_name("studio.py")),"build","--spec",str(example/"input"/"source_spec.json"),"--output-dir",str(folder)],check=True,capture_output=True,env=env)
                cli_hashes.append(hashlib.sha256((folder/"figure.svg").read_bytes()).hexdigest())
            assert cli_hashes[0]==cli_hashes[1],"SVG differs across processes/PYTHONHASHSEED values"
            tests.append({"test":"cross_process_determinism","status":"pass","sha256":cli_hashes[0],"python_hash_seeds":[1,2]})
            auto=copy.deepcopy(spec)
            for n in auto["nodes"]: n.pop("rank",None)
            studio.build_svg(auto,example/"input",root)
            tests.append({"test":"automatic_topological_ranks_with_information_feedback","status":"pass"})
            original=svg1.encode("utf-8")
            for edit in ({"op":"set_text","id":"figure-title","text":"Byte-safe & source-faithful"},{"op":"set_attr","id":"figure-heading","name":"data-test","value":"A&B"},{"op":"set_attr","id":"figure-heading","name":"fill","value":"#112233"}):
                changed,report=patch(original,[edit]); r=report["edits"][0]; lo,hi=r["byte_span"]; size=r["replacement_bytes"]
                assert changed[:lo]==original[:lo],"bytes before addressed span changed"
                assert changed[lo+size:]==original[hi:],"bytes after addressed span changed"
                assert changed!=original,"patch had no effect"
                tests.append({"test":"byte_preserving_"+edit["op"]+"_"+r["addressed"],"status":"pass","byte_span":[lo,hi]})
            malformed=copy.deepcopy(spec); malformed["charts"][0]["x_column"]="missing_time"
            try: studio.build_svg(malformed,example/"input",root)
            except studio.StudioError as e:
                assert "not present" in str(e); tests.append({"test":"malformed_csv_mapping_rejected","status":"pass","message":str(e)})
            else: raise AssertionError("Malformed CSV column was accepted")
            malformed2=copy.deepcopy(spec); malformed2["charts"][0]["data_csv"]="absent.csv"
            try: studio.build_svg(malformed2,example/"input",root)
            except studio.StudioError as e: tests.append({"test":"missing_csv_rejected","status":"pass","message":str(e)})
            else: raise AssertionError("Missing CSV was accepted")
            overflow=copy.deepcopy(spec); overflow["nodes"][0]["label"]="Intentionally overflowing label "*10; overflow["nodes"][0]["max_label_lines"]=1
            try: studio.build_svg(overflow,example/"input",root)
            except studio.StudioError as e:
                assert "Label overflow" in str(e); tests.append({"test":"label_overflow_rejected","status":"pass","message":str(e)})
            else: raise AssertionError("Overflow label was accepted")
            duplicate=copy.deepcopy(spec); duplicate["nodes"][1]["id"]=duplicate["nodes"][0]["id"]
            try: studio.build_svg(duplicate,example/"input",root)
            except studio.StudioError as e: tests.append({"test":"duplicate_id_rejected","status":"pass","message":str(e)})
            else: raise AssertionError("Duplicate ID was accepted")
        report={"status":"pass","tests":tests,"test_count":len(tests),"visual_review":"separate; structural tests do not certify science or aesthetics"}
        studio.dump_json(a.report,report); print(json.dumps(report,ensure_ascii=False)); return 0
    except Exception as e:
        report={"status":"fail","tests":tests,"error":str(e)}; studio.dump_json(a.report,report); print(f"ERROR: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())

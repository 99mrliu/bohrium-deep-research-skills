#!/usr/bin/env python3
"""Run the explicitly synthetic example and its source-preserving edit demonstration."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import studio
from patch_svg import patch

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--example-dir",required=True,help="examples/synthetic directory")
    p.add_argument("--output-dir",required=True,help="runtime output directory, outside the text-only bundle")
    p.add_argument("--preview-png",required=True,help="real PNG preview to create and verify")
    p.add_argument("--pdf",action="store_true",help="also create and verify figure.pdf in output-dir")
    a=p.parse_args(argv); example=Path(a.example_dir).resolve(); out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    png=Path(a.preview_png).resolve(); png.parent.mkdir(parents=True,exist_ok=True); pdf=out/"figure.pdf" if a.pdf else None
    try:
        case=studio.load_json(example/"input"/"case.json"); spec_path=example/"input"/"source_spec.json"; spec=studio.load_json(spec_path)
        if not spec.get("synthetic") or not case.get("synthetic"): raise studio.StudioError("Example must be explicitly labelled synthetic")
        svg,metadata=studio.build_svg(spec,spec_path.parent,out); svg=svg.replace("<defs>",studio.STYLE+"<defs>",1)
        (out/"figure.svg").write_text(svg,encoding="utf-8")
        normalized=dict(spec); normalized["charts"]=[dict(c,data_csv=Path(c["data_csv"]).name) for c in spec.get("charts",[])]
        studio.dump_json(out/"source_spec.json",normalized); studio.dump_json(out/"layout_manifest.json",metadata)
        report={"status":"complete","svg":studio.verify_svg(out/"figure.svg"),"exports":[],"limitations":["All content and chart values are synthetic; this is not a formal case result.","Live SVG fonts are not embedded; system font substitution is used during export."]}
        report.update(studio.export_files(out/"figure.svg",png,pdf)); report["exports"].append(studio.verify_png(png))
        if pdf: report["exports"].append(studio.verify_pdf(pdf))
        studio.dump_json(out/"export_qc.json",report)
        edits=studio.load_json(example/"input"/"edits.json")
        edited,edit_report=patch((out/"figure.svg").read_bytes(),edits); (out/"figure-edited.svg").write_bytes(edited); studio.dump_json(out/"edit_report.json",edit_report)
        edit_report["edited_svg_qc"]=studio.verify_svg(out/"figure-edited.svg"); studio.dump_json(out/"edit_report.json",edit_report)
        exports=[str(png)] + ([str(pdf)] if pdf else [])
        artifacts={"editable_source":"figure.svg","source_spec":"source_spec.json","chart_data":metadata["copied_csv"],"layout_manifest":"layout_manifest.json","exports":exports,"png":str(png),"pdf":str(pdf) if pdf else None,"export_qc_report":"export_qc.json","edited_svg":"figure-edited.svg","edit_report":"edit_report.json"}
        keys=list(case.get("output_contract",{})); values={"editable_source":artifacts["editable_source"],"export_files":artifacts["exports"],"source_and_change_records":{"sources":spec.get("sources",[]),"change_records":[{"operation":"new synthetic figure","rebuild":True},{"operation":"source-preserving patch demonstrated in separate figure-edited.svg","rebuild":False,"report":"edit_report.json"}]}}
        missing=[k for k in keys if k not in values]
        if missing: raise studio.StudioError(f"Unmapped example contract fields: {missing}")
        result={"case_id":case.get("case_id"),"status":"success","synthetic":True,"example_notice":"SYNTHETIC demonstration only; no experimental claims.","output_contract_fields":keys,"sources":spec.get("sources",[]),"uncertainties":report["limitations"],"change_records":values["source_and_change_records"]["change_records"],"data_mappings":metadata["data_mappings"],"routes":metadata["routes"],"font_embedding":False,**artifacts,**values}
        studio.dump_json(out/"result.json",result)
        print(json.dumps({"status":"complete","synthetic":True,"svg":str(out/"figure.svg"),"png":str(png),"pdf":str(pdf) if pdf else None,"edited_svg":str(out/"figure-edited.svg"),"result":str(out/"result.json")},ensure_ascii=False))
        return 0
    except Exception as e:
        failure={"case_id":"synthetic-microreactor-001","status":"failed","synthetic":True,"errors":[str(e)],"editable_source":None,"export_files":[],"source_and_change_records":None}
        out.mkdir(parents=True,exist_ok=True); studio.dump_json(out/"result.json",failure)
        print(f"ERROR: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())

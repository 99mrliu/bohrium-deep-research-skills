#!/usr/bin/env python3
"""Build, export and report an actual runtime case from an agent-authored source spec."""
from __future__ import annotations
import argparse, json, sys, traceback
from pathlib import Path
import studio

def contract_values(case, artifacts):
    contract=case.get("output_contract",{})
    keys=list(contract) if isinstance(contract,dict) else list(contract) if isinstance(contract,list) else []
    values={}
    for key in keys:
        k=str(key).lower(); descriptor=contract.get(key) if isinstance(contract,dict) else ""
        hint=(k+" "+json.dumps(descriptor,ensure_ascii=False) if not isinstance(descriptor,(dict,list)) else k).lower()
        value=None
        if k in artifacts: value=artifacts[k]
        elif "source_spec" in k or "specification" in k: value=artifacts.get("source_spec")
        elif "change" in k or "modification" in k or "record" in k: value=artifacts.get("source_and_change_records")
        elif "png" in hint: value=artifacts.get("png")
        elif "pdf" in hint: value=artifacts.get("pdf")
        elif "svg" in hint or "editable" in k or "source" in k: value=artifacts.get("editable_source")
        elif "export" in k: value=artifacts.get("exports")
        values[key]=value
    return keys,values

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case",required=True); p.add_argument("--task",required=True); p.add_argument("--spec",required=True); p.add_argument("--output-dir",default="/app/output"); p.add_argument("--skip-export",action="store_true")
    a=p.parse_args(argv); out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    case={}; status="failed"; uncertainties=[]; sources=[]; change_records=[]; errors=[]
    try:
        case=studio.load_json(a.case); task=Path(a.task).read_text(encoding="utf-8")
        if not task.strip(): raise studio.StudioError("Actual task.md is empty")
        keys,values=contract_values(case,{})
        checkpoint={"case_id":case.get("case_id"),"status":"partial","synthetic":False,
                    "sources":[],"uncertainties":["Build and export have not completed yet."],
                    "change_records":[],"output_contract_fields":keys,**values}
        studio.dump_json(out/"result.json",checkpoint)
        spec=studio.load_json(a.spec)
        if spec.get("synthetic"): raise studio.StudioError("Refusing to submit the synthetic example as an actual case")
        missing=[n["id"] for n in spec.get("nodes",[]) if not n.get("sources")]
        if missing: uncertainties.append("Nodes without explicit source evidence: "+", ".join(missing))
        svg,metadata=studio.build_svg(spec,Path(a.spec).resolve().parent,out)
        svg=svg.replace("<defs>",studio.STYLE+"<defs>",1)
        (out/"figure.svg").write_text(svg,encoding="utf-8")
        normalized=dict(spec)
        if spec.get("charts"): normalized["charts"]=[dict(c,data_csv=Path(c["data_csv"]).name) for c in spec["charts"]]
        studio.dump_json(out/"source_spec.json",normalized); studio.dump_json(out/"layout_manifest.json",metadata)
        artifacts={"editable_source":"figure.svg","source_spec":"source_spec.json","layout_manifest":"layout_manifest.json","chart_data":metadata["copied_csv"],"exports":[],"png":None,"pdf":None}
        png=out/"figure.png"; pdf=out/"figure.pdf"; report_path=out/"export_qc.json"
        export={"status":"not_requested","exports":[],"limitations":["Raster/PDF export skipped by explicit option."]}
        if not a.skip_export:
            export={"status":"complete","svg":studio.verify_svg(out/"figure.svg"),"exports":[]}
            export.update(studio.export_files(out/"figure.svg",png,pdf))
            artifacts["png"]="figure.png"; artifacts["pdf"]="figure.pdf"; artifacts["exports"]=["figure.png","figure.pdf"]
            export["exports"]=[studio.verify_png(png),studio.verify_pdf(pdf)]
            export["font_embedding"]="not performed by builder; see svg.font_note"
        studio.dump_json(report_path,export); artifacts["export_qc_report"]="export_qc.json"
        sources=spec.get("sources",[]); change_records=spec.get("change_records",[{"version":studio.VERSION,"operation":"new deterministic SVG from source_spec.json","source_preserving_patch":False}])
        status="success" if not uncertainties else "partial"
        keys,values=contract_values(case,artifacts)
        missing_contract=[k for k in keys if values[k] is None]
        if missing_contract:
            uncertainties.append("No automatic value mapping for output_contract fields: "+", ".join(missing_contract)); status="partial"
        result={"case_id":case.get("case_id"),"status":status,"synthetic":False,"task_read":str(Path(a.task)),"output_contract_fields":keys,"sources":sources,"uncertainties":uncertainties,"change_records":change_records,"data_mappings":metadata["data_mappings"],"routes":metadata["routes"],"errors":[],"export_status":export["status"],"font_embedding":False,**artifacts,**values}
        studio.dump_json(out/"result.json",result)
        print(json.dumps({"status":status,"case_id":result["case_id"],"output_dir":str(out),"contract_fields":keys}))
        return 0 if status=="success" else 3
    except Exception as e:
        errors.append(str(e)); uncertainties.append("Runtime/build/export error: "+str(e))
        svg_ok=(out/"figure.svg").is_file(); spec_ok=(out/"source_spec.json").is_file()
        png_ok=(out/"figure.png").is_file(); pdf_ok=(out/"figure.pdf").is_file()
        exports=[name for name,ok in (("figure.png",png_ok),("figure.pdf",pdf_ok)) if ok]
        artifacts={"editable_source":"figure.svg" if svg_ok else None,
                   "source_spec":"source_spec.json" if spec_ok else None,
                   "png":"figure.png" if png_ok else None,"pdf":"figure.pdf" if pdf_ok else None,
                   "exports":exports,"export_qc_report":"export_qc.json" if (out/"export_qc.json").is_file() else None}
        keys,values=contract_values(case,artifacts)
        status="partial" if svg_ok else "failed"
        result={"case_id":case.get("case_id") if isinstance(case,dict) else None,"status":status,"synthetic":False,"sources":sources,"uncertainties":uncertainties,"change_records":change_records,"errors":errors,"output_contract_fields":keys,"font_embedding":False,**artifacts,**values}
        studio.dump_json(out/"result.json",result); print(f"ERROR: {e}",file=sys.stderr)
        return 3 if svg_ok else 2
if __name__=="__main__": raise SystemExit(main())

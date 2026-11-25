#!/usr/bin/env python3
"""make_fixture.py — SYNTHETIC demo fixture for audience-refit-studio.

Builds, from scratch and with the bundle's own deck_io machinery:
  work/input/starting-deck.pptx : 5 slides, fictional "SynGraph" study,
                                  marked SYNTHETIC everywhere.
  work/paper.txt                : plain-text paper with \\f page breaks.
  work/input/case.json          : case_id synthetic-demo-003.
  work/input/task.md            : the adapt-mode task statement.
  work/workorder.json           : peer -> advisor, keep-en, 5 -> 4 slides.
  work/refit_ops.json           : honest synthetic "agent" rewrite.
  work/refit_ops_bad.json       : same, but fabricates 97.1% (audit bait).

ALL CONTENT IS INVENTED FOR DEMONSTRATION.  Nothing here is real research.
"""

import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, SKILL_SCRIPTS)
import deck_io  # noqa: E402

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
WORK = os.path.join(HERE, "work")
INPUT_DIR = os.path.join(WORK, "input")

SYN = "SYNTHETIC EXAMPLE"


def sp(pid_name, ph_type, n_paras, idx_start):
    ph = '<p:ph type="%s"/>' % ph_type
    paras = "".join("<a:p/>" for _ in range(n_paras))
    # explicit geometry: placeholder inheritance from the minimal fixture
    # layout is unreliable in some renderers, so pin real boxes (16:9 EMU)
    if ph_type == "title":
        xfrm = ('<a:xfrm><a:off x="548640" y="274320"/>'
                '<a:ext cx="11049000" cy="1250000"/></a:xfrm>')
    else:
        xfrm = ('<a:xfrm><a:off x="548640" y="1750000"/>'
                '<a:ext cx="11049000" cy="4400000"/></a:xfrm>')
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="{id}" name="{name}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr>{ph}</p:nvPr></p:nvSpPr>'
        '<p:spPr>{xfrm}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{paras}</p:txBody></p:sp>'
    ).format(id=idx_start, name=pid_name, ph=ph, paras=paras, xfrm=xfrm)


def slide_xml(n_title_paras, n_body_paras):
    shapes = sp("Title", "title", n_title_paras, 2)
    shapes += sp("Body", "body", n_body_paras, 3)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:sld xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>{shapes}</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    ).format(a=A, p=P, r=R, shapes=shapes)


def notes_xml(n_paras):
    paras = "".join("<a:p/>" for _ in range(n_paras))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:notes xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        "<p:grpSpPr/>"
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/><p:cNvSpPr/>'
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/>'
        "<p:txBody><a:bodyPr wrap=\"square\"/><a:lstStyle/>{paras}</p:txBody></p:sp>"
        "</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>"
    ).format(a=A, p=P, r=R, paras=paras)


NOTES_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<p:notesMaster xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}">'
    "<p:cSld><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
    'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
    'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    "</p:notesMaster>").format(a=A, p=P, r=R)

NOTES_MASTER_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="%s">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    "</Relationships>" % PKG_REL)


THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{a}" name="Synthetic"><a:themeElements><a:clrScheme name="Synthetic">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1F3864"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>
<a:accent1><a:srgbClr val="4472C4"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>
<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>
<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>
<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
</a:clrScheme><a:fontScheme name="Synthetic">
<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>
</a:fontScheme><a:fmtScheme name="Synthetic"><a:fillStyleLst>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:fillStyleLst><a:lnStyleLst>
<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
</a:lnStyleLst><a:effectStyleLst>
<a:effectStyle><a:effectLst/></a:effectStyle>
<a:effectStyle><a:effectLst/></a:effectStyle>
<a:effectStyle><a:effectLst/></a:effectStyle>
</a:effectStyleLst><a:bgFillStyleLst>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>""".format(a=A)

MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<p:sldMaster xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}"><p:cSld><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
    'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
    'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="3200" b="1"/></a:lvl1pPr></p:titleStyle>'
    '<p:bodyStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle>'
    '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>'
    "</p:txStyles></p:sldMaster>"
).format(a=A, p=P, r=R)

LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<p:sldLayout xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}" type="blank" preserve="1">'
    '<p:cSld name="Blank"><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr/></p:spTree></p:cSld>"
    "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
).format(a=A, p=P, r=R)

# (n_title_paras, n_body_paras) per skeleton slide
SHAPE_PLAN = [(1, 2), (1, 3), (1, 3), (1, 3), (1, 2)]

SLIDE_TEXTS = [
    {  # slide 1 — title
        "title": [SYN + " — SynGraph: Graph Kernels for Molecule "
                  "Property Prediction"],
        "body": ["A fictional study for skill demonstration. "
                 "Not real research.",
                 "Author: A. N. Example, Synthetic University"],
        "notes": [SYN + " title slide; no scientific claims."],
    },
    {  # slide 2 — background
        "title": ["Background: Molecule Property Prediction"],
        "body": ["Quantitative structure-activity relationship (QSAR) "
                 "tasks map molecules to properties.",
                 "Graph kernel (GK) methods compare molecular graphs "
                 "efficiently.",
                 "Standard baselines reach 88.1% accuracy on SynBench."],
        "notes": [SYN + ": context slide for peers."],
    },
    {  # slide 3 — gap
        "title": ["Gap and Motivation"],
        "body": ["Existing graph kernels ignore synthetic chirality cues.",
                 "We propose SynGraph (SG), a chirality-aware graph kernel.",
                 "The gap is 4.2 percentage points below the oracle."],
        "notes": [SYN + ": gap statement, invented."],
    },
    {  # slide 4 — method/results
        "title": ["SynGraph (SG) Method"],
        "body": ["SG extends the Weisfeiler-Lehman subtree kernel with "
                 "chirality features.",
                 "We achieve accuracy of 92.3% on SynBench, +4.2 points "
                 "over the 88.1% baseline.",
                 "Runtime is 3.5 s per 1,000 molecules."],
        "notes": [SYN + " numbers; do not cite."],
    },
    {  # slide 5 — backup
        "title": ["Backup: Ablation Details"],
        "body": ["Removing chirality features drops accuracy to 90.0%.",
                 "Hyperparameters: 12 epochs, learning rate 1e-3."],
        "notes": [SYN + ": backup absorbs detail."],
    },
]

PAPER = (
    "SynGraph: Graph Kernels for Molecule Property Prediction. "
    + SYN + ". Not real research.\n"
    "We propose SynGraph (SG), a chirality-aware graph kernel (GK) for "
    "molecule property prediction. Our task is Quantitative "
    "Structure-Activity Relationship (QSAR) prediction on the fictional "
    "SynBench benchmark.\n\f"
    "SG extends the Weisfeiler-Lehman subtree kernel. We achieve accuracy "
    "of 92.3% on SynBench, 4.2 percentage points over the 88.1% baseline. "
    "Runtime is 3.5 s per 1,000 molecules with 12 epochs at learning rate "
    "1e-3. Removing chirality features drops accuracy to 90.0%.\n\f"
)

GOOD_OPS = [
    {"op": "rewrite_paras", "slide": 1, "reason": (
        "brief section 5: merge background+gap first to free one slide; "
        "numbers 88.1% and 4.2 re-homed verbatim on the merged slide"),
     "paras": [
        {"pid": "s1p0", "text": "Background & Motivation (" + SYN + ")"},
        {"pid": "s1p1", "text": (
            "Quantitative structure-activity relationship (QSAR) tasks map "
            "molecules to properties.")},
        {"pid": "s1p2", "text": (
            "Graph kernel (GK) methods compare molecular graphs; baselines "
            "reach 88.1% accuracy on SynBench.")},
        {"pid": "s1p3", "text": (
            "Gap: existing kernels ignore chirality; we propose SynGraph "
            "(SG), 4.2 points below the oracle.")},
     ]},
    {"op": "delete_slide", "slide": 2, "reason": (
        "gap slide merged into slide 2 (index 1) by previous op; content "
        "preserved, no unique numbers lost")},
    {"op": "rewrite_paras", "slide": 2, "reason": (
        "audience switch peer->advisor: re-voice results as progress "
        "milestones; all numbers kept verbatim"),
     "paras": [
        {"pid": "s3p0", "text": "Progress: SynGraph (SG) Validated"},
        {"pid": "s3p1", "text": (
            "Completed: SG kernel extending the Weisfeiler-Lehman subtree "
            "kernel, validated on SynBench.")},
        {"pid": "s3p2", "text": (
            "Milestone reached: accuracy of 92.3% on SynBench, +4.2 points "
            "over the 88.1% baseline.")},
        {"pid": "s3p3", "text": (
            "Next step: advisor review of the experiment plan; runtime "
            "stays 3.5 s per 1,000 molecules.")},
     ]},
    {"op": "set_notes", "slide": 2, "text": (
        SYN + ": advisor meeting version; numbers unchanged from the "
        "peer version."), "reason": (
        "advisor needs the talking point that no number was altered")},
    {"op": "delete_slide", "slide": 3, "reason": (
        "backup slide absorbed to hit target_slides=4; its numbers "
        "(90.0%, 12, 1e-3) are declared dropped with this deletion"),
     "dropped_numbers": ["90.0%", "12", "1e-3"]},
    {"op": "add_slide", "after": 2, "donor": 0, "reason": (
        "advisor audience needs an explicit next-steps slide; cloned from "
        "the title slide as layout donor; introduces no new numbers"),
     "paras": [
        {"pid": "s0p0", "text": "Next Steps (" + SYN + ")"},
        {"pid": "s0p1", "text": "Run cross-validation and freeze the "
                               "thesis outline."},
        {"pid": "s0p2", "text": "Deliverable: thesis chapter draft for "
                               "advisor review."},
        {"pid": "s0p3", "text": SYN + ": closing slide, invented content."},
     ]},
]

BAD_OPS = json.loads(json.dumps(GOOD_OPS))
BAD_OPS[2]["paras"][2]["text"] = (
    "Milestone reached: accuracy of 97.1% on SynBench, +4.2 points "
    "over the 88.1% baseline.")

CASE = {
    "case_id": "synthetic-demo-003",
    "mode": "adapt",
    "synthetic_example": True,
    "output_contract": {
        "status": "success",
        "editable_source": "/app/output/presentation.pptx",
        "export_artifact": "/app/output/presentation.pdf",
        "content_map": "slide-index mapping before -> after",
        "compliance_checks": ["refit_audit.json verdict"],
        "exceptions": [],
    },
}

TASK_MD = """# Task (SYNTHETIC EXAMPLE)

Adapt the existing deck `starting-deck.pptx` (5 slides, peer audience,
English) for an **advisor** progress meeting, keeping English, ending at
**4 slides**.  The fictional paper text is in `paper.txt`; the work order
is in `workorder.json`.  Respect the locked terminology table and keep
every number either conserved or honestly declared.
"""

WORKORDER = {
    "mode": "adapt",
    "audience_from": "peer",
    "audience_to": "advisor",
    "language": "keep-en",
    "current_slides": 5,
    "target_slides": 4,
    "synthetic_example": True,
}


def build_skeleton(path):
    """Write a minimal but valid 5-slide pptx with empty paragraphs."""
    n_slides = len(SHAPE_PLAN)
    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.presentationml.'
        'presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/ppt/notesMasters/notesMaster1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'presentationml.notesMaster+xml"/>',
    ]
    for i in range(1, n_slides + 1):
        overrides.append(
            '<Override PartName="/ppt/slides/slide%d.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.presentationml.'
            'slide+xml"/>' % i)
        overrides.append(
            '<Override PartName="/ppt/notesSlides/notesSlide%d.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'presentationml.notesSlide+xml"/>' % i)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="%s"><Default Extension="rels" ContentType='
        '"application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>%s'
        "</Types>" % (CT, "".join(overrides)))

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="%s"><Relationship Id="rId1" Type='
        '"http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" Target="ppt/presentation.xml"/>'
        "</Relationships>" % PKG_REL)

    sld_ids = "".join(
        '<p:sldId id="%d" r:id="rId%d"/>' % (255 + i, i + 1)
        for i in range(1, n_slides + 1))
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<p:presentation xmlns:a="{a}" xmlns:p="{p}" xmlns:r="{r}">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        "</p:sldMasterIdLst>"
        '<p:notesMasterIdLst><p:notesMasterId r:id="rId100"/>'
        "</p:notesMasterIdLst>"
        "<p:sldIdLst>{sld_ids}</p:sldIdLst>"
        '<p:sldSz cx="12192000" cy="6858000"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr>'
        "</p:defaultTextStyle></p:presentation>").format(
        a=A, p=P, r=R, sld_ids=sld_ids)

    pres_rels = ['<Relationship Id="rId1" Type='
                 '"http://schemas.openxmlformats.org/officeDocument/2006/'
                 'relationships/slideMaster" Target="slideMasters/'
                 'slideMaster1.xml"/>',
                 '<Relationship Id="rId100" Type='
                 '"http://schemas.openxmlformats.org/officeDocument/2006/'
                 'relationships/notesMaster" Target="notesMasters/'
                 'notesMaster1.xml"/>']
    for i in range(1, n_slides + 1):
        pres_rels.append('<Relationship Id="rId%d" Type='
                         '"http://schemas.openxmlformats.org/officeDocument/'
                         '2006/relationships/slide" Target="slides/slide%d'
                         '.xml"/>' % (i + 1, i))
    pres_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="%s">%s</Relationships>'
        % (PKG_REL, "".join(pres_rels)))

    master_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="%s">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/slideLayout" Target='
        '"../slideLayouts/slideLayout1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/theme" Target="../theme/'
        'theme1.xml"/></Relationships>' % PKG_REL)

    layout_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="%s">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/slideMaster" Target='
        '"../slideMasters/slideMaster1.xml"/></Relationships>' % PKG_REL)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", pres_rels)
        z.writestr("ppt/slideMasters/slideMaster1.xml", MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",
                   master_rels)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels",
                   layout_rels)
        z.writestr("ppt/theme/theme1.xml", THEME)
        z.writestr("ppt/notesMasters/notesMaster1.xml", NOTES_MASTER)
        z.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels",
                   NOTES_MASTER_RELS)
        for i, (nt, nb) in enumerate(SHAPE_PLAN, start=1):
            z.writestr("ppt/slides/slide%d.xml" % i, slide_xml(nt, nb))
            z.writestr("ppt/slides/_rels/slide%d.xml.rels" % i, (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="%s">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats'
                '.org/officeDocument/2006/relationships/slideLayout" '
                'Target="../slideLayouts/slideLayout1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats'
                '.org/officeDocument/2006/relationships/notesSlide" '
                'Target="../notesSlides/notesSlide%d.xml"/></Relationships>'
                % (PKG_REL, i)))
            z.writestr("ppt/notesSlides/notesSlide%d.xml" % i, notes_xml(1))
            z.writestr(
                "ppt/notesSlides/_rels/notesSlide%d.xml.rels" % i, (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"'
                    '?>\n<Relationships xmlns="%s">'
                    '<Relationship Id="rId1" Type="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships/'
                    'slide" Target="../slides/slide%d.xml"/>'
                    '<Relationship Id="rId2" Type="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships/'
                    'notesMaster" Target="../notesMasters/notesMaster1.xml"/>'
                    '</Relationships>'
                    % (PKG_REL, i)))


def fill_model(model):
    for slide, content in zip(model["slides"], SLIDE_TEXTS):
        by_role = {"title": iter(content["title"]),
                   "body": iter(content["body"])}
        for para in slide["paras"]:
            if para["role"] == "notes":
                para["text"] = content["notes"][0]
            else:
                para["text"] = next(by_role[para["role"]])
    return model


def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)

    skeleton = os.path.join(WORK, "skeleton.pptx")
    deck_path = os.path.join(INPUT_DIR, "starting-deck.pptx")
    build_skeleton(skeleton)
    model = deck_io.read_deck(skeleton)
    model = fill_model(model)
    deck_io.write_deck(model, skeleton, deck_path)
    os.remove(skeleton)

    with open(os.path.join(WORK, "paper.txt"), "w", encoding="utf-8") as f:
        f.write(PAPER)
    with open(os.path.join(INPUT_DIR, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE, f, ensure_ascii=False, indent=1)
    with open(os.path.join(INPUT_DIR, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK_MD)
    with open(os.path.join(WORK, "workorder.json"), "w", encoding="utf-8") as f:
        json.dump(WORKORDER, f, ensure_ascii=False, indent=1)
    with open(os.path.join(WORK, "refit_ops.json"), "w", encoding="utf-8") as f:
        json.dump(GOOD_OPS, f, ensure_ascii=False, indent=1)
    with open(os.path.join(WORK, "refit_ops_bad.json"), "w",
              encoding="utf-8") as f:
        json.dump(BAD_OPS, f, ensure_ascii=False, indent=1)

    print("fixture ready (SYNTHETIC):")
    for p in (deck_path, os.path.join(WORK, "paper.txt"),
              os.path.join(INPUT_DIR, "case.json"),
              os.path.join(WORK, "workorder.json"),
              os.path.join(WORK, "refit_ops.json"),
              os.path.join(WORK, "refit_ops_bad.json")):
        print("  ", p)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Inspect a .pptx template and emit an authoritative template map (JSON).

The map records: slide size, per-master theme fonts (latin + East Asian) and
theme colors, and every layout's name, index, and placeholders with their
idx / type / geometry (or inherited-from-layout marker). This map — not
memory — must drive layout choice when building the deck.

Usage:
    python template_map.py TEMPLATE.pptx --out template_map.json

Requires python-pptx (pip install python-pptx). Stdlib otherwise.
"""
import argparse
import hashlib
import json
import sys
import zipfile

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def emu2cm(v):
    return None if v is None else round(v / 360000.0, 3)


def theme_info(prs):
    """Theme fonts and colors from the first master's theme part."""
    out = {'major_latin': None, 'minor_latin': None, 'major_ea': None,
           'minor_ea': None, 'colors': {}}
    try:
        theme = prs.slide_masters[0].element.getroottree()  # placeholder
    except Exception:
        pass
    try:
        part = prs.slide_masters[0].part
        # find theme part via relationships
        from pptx.opc.package import Part  # noqa
        theme_part = None
        for rel in part.rels.values():
            if 'theme' in rel.reltype:
                theme_part = rel.target_part
                break
        if theme_part is None:
            return out
        from lxml import etree
        root = etree.fromstring(theme_part.blob)
        scheme = root.find('.//a:themeElements/a:fontScheme', NS)
        if scheme is not None:
            for tag, key in (('majorFont', 'major'), ('minorFont', 'minor')):
                node = scheme.find('a:' + tag, NS)
                if node is not None:
                    lat = node.find('a:latin', NS)
                    ea = node.find('a:ea', NS)
                    if lat is not None:
                        out[key + '_latin'] = lat.get('typeface') or None
                    if ea is not None:
                        out[key + '_ea'] = ea.get('typeface') or None
        clr = root.find('.//a:themeElements/a:clrScheme', NS)
        if clr is not None:
            for child in clr:
                name = child.tag.split('}')[1]
                srgb = child.find('a:srgbClr', NS)
                sysc = child.find('a:sysClr', NS)
                if srgb is not None:
                    out['colors'][name] = '#' + srgb.get('val')
                elif sysc is not None:
                    out['colors'][name] = 'sys:' + str(sysc.get('lastClr'))
    except Exception as e:  # never let theme parsing kill the map
        out['theme_error'] = str(e)
    return out


def layout_ph(shape):
    ph = shape.placeholder_format
    geo = {}
    try:
        geo = {'left_cm': emu2cm(shape.left), 'top_cm': emu2cm(shape.top),
               'width_cm': emu2cm(shape.width), 'height_cm': emu2cm(shape.height)}
    except Exception:
        pass
    inherited = all(v is None for v in geo.values())
    return {'idx': ph.idx, 'ph_type': str(ph.type), 'name': shape.name,
            'geometry': geo, 'inherits_position': inherited}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('template')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    try:
        from pptx import Presentation
        from pptx.util import Emu  # noqa
    except ImportError:
        sys.exit('python-pptx missing: pip install python-pptx')
    prs = Presentation(args.template)
    layouts = []
    for mi, master in enumerate(prs.slide_masters):
        for li, layout in enumerate(master.slide_layouts):
            phs = [layout_ph(s) for s in layout.placeholders]
            layouts.append({
                'master_index': mi, 'layout_index_in_master': li,
                'name': layout.name, 'part_name': layout.part.partname,
                'placeholders': phs,
            })
    # global flat index as python-pptx exposes on prs.slide_layouts
    for gi, layout in enumerate(prs.slide_layouts):
        for rec in layouts:
            if rec['part_name'] == layout.part.partname:
                rec['global_index'] = gi
    masters = []
    for mi, master in enumerate(prs.slide_masters):
        masters.append({'index': mi, 'name': master.name,
                        'part_name': master.part.partname,
                        'n_layouts': len(master.slide_layouts)})
    # count media / embedded fonts
    media, fonts_embedded = [], False
    with zipfile.ZipFile(args.template) as z:
        media = [n for n in z.namelist() if n.startswith('ppt/media/')]
        fonts_embedded = any('fonts' in n for n in z.namelist())
    result = {
        'template': args.template,
        'sha256': sha256(args.template),
        'slide_width_cm': emu2cm(prs.slide_width),
        'slide_height_cm': emu2cm(prs.slide_height),
        'aspect': round(prs.slide_width / prs.slide_height, 4),
        'theme': theme_info(prs),
        'masters': masters,
        'layouts': layouts,
        'existing_slides': len(prs.slides.__iter__.__self__._sldIdLst),
        'embedded_fonts': fonts_embedded,
        'media_files': media,
    }
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # compact console digest for the agent
    print('slide size: %.2f x %.2f cm' % (result['slide_width_cm'],
                                          result['slide_height_cm']))
    print('theme: major=%s/%s minor=%s/%s' % (
        result['theme'].get('major_latin'), result['theme'].get('major_ea'),
        result['theme'].get('minor_latin'), result['theme'].get('minor_ea')))
    for rec in layouts:
        phs = ','.join('%s:%s' % (p['idx'], p['ph_type'].split(' ')[0])
                       for p in rec['placeholders'])
        print('layout[%s] "%s": %s' % (rec.get('global_index'),
                                       rec['name'], phs or '(no placeholders)'))
    print('map ->', args.out)


if __name__ == '__main__':
    main()

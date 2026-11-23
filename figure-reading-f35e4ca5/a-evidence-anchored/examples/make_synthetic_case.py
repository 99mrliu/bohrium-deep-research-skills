#!/usr/bin/env python3
"""SYNTHETIC EXAMPLE — generates a toy case and runs the whole pipeline.

This is an illustrative miniature, NOT an official case and NOT a
pre-computed answer. It fabricates a small dose-response experiment
(two series, one table, one figure), then exercises the real scripts:

  mine_case.py -> anchor_figure.py -> crosscheck.py -> make_result.py

plus a negative control (a misread axis card that the gates must reject).

Usage:
  python examples/make_synthetic_case.py [workdir]
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, 'scripts')


def gen_case(root):
    inp = os.path.join(root, 'input')
    work = os.path.join(root, 'work')
    out = os.path.join(root, 'output')
    for d in (inp, work, out):
        os.makedirs(d, exist_ok=True)

    doses = [0.0, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
    def hill(c, ec50, top):
        return top * c / (ec50 + c) if c > 0 else 0.0
    wt = [round(hill(c, 3.0, 95.0) + 2.0, 1) for c in doses]
    ko = [round(hill(c, 8.0, 61.0) + 2.0, 1) for c in doses]

    with open(os.path.join(inp, 'table_response.csv'), 'w',
              encoding='utf-8') as f:
        f.write('dose_uM,WT_response_pct,KO_response_pct\n')
        for d, w, k in zip(doses, wt, ko):
            f.write('%g,%.1f,%.1f\n' % (d, w, k))

    case = {
        'case_id': 'SYN-EVIDENCE-EXAMPLE',
        'kind': 'synthetic-illustrative-example',
        'output_contract': {
            'answer': 'free text answering the task question with units',
            'extracted_values': 'list of {series,value,unit,err}',
            'evidence_map': 'mapping from each reported value to its source'
        }
    }
    with open(os.path.join(inp, 'case.json'), 'w', encoding='utf-8') as f:
        json.dump(case, f, indent=2)
    with open(os.path.join(inp, 'task.md'), 'w', encoding='utf-8') as f:
        f.write('For each series, report the response at dose = 10 uM '
                '(percent, with reading error) and state which series '
                'saturates higher.\n')

    fig_path = os.path.join(inp, 'fig_doseresp.png')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5, 3.5), dpi=150)
        ax.semilogx([max(d, 0.05) for d in doses], wt, 'o-', color='#0072B2',
                    label='WT')
        ax.semilogx([max(d, 0.05) for d in doses], ko, 's--', color='#D55E00',
                    label='KO')
        ax.set_xlabel('dose (uM)')
        ax.set_ylabel('response (%)')
        ax.legend()
        fig.tight_layout()
        fig.savefig(fig_path)
        plt.close(fig)
        print('[example] synthetic figure written:', fig_path)
    except Exception as e:  # matplotlib absent: tables still drive the demo
        print('[example] matplotlib unavailable (%s); figure skipped' % e)
    return inp, work, out, (doses, wt, ko)


def run(cmd):
    print('$', ' '.join(cmd))
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        print(r.stderr.strip())
        raise SystemExit('step failed: %s' % cmd[0])


def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
        os.path.abspath('synthetic_run_a')
    inp, work, out, (doses, wt, ko) = gen_case(root)

    run([os.path.join(SCRIPTS, 'mine_case.py'),
         '--case', os.path.join(inp, 'case.json'),
         '--task', os.path.join(inp, 'task.md'),
         '--input-dir', inp, '--work', work, '--out', out])

    # --- what the agent writes after zooming into the figure -------------
    # axis card: x is log (semilogx), y linear; ticks measured in pixels
    axis_spec = {
        'axes': [
            {'axis': 'x', 'label': 'dose (uM)', 'unit': 'uM', 'type': 'log',
             'ticks': [{'value': 0.1, 'px': 96}, {'value': 1.0, 'px': 227},
                       {'value': 10.0, 'px': 358}, {'value': 100.0, 'px': 489}],
             'plot_area': [60, 15, 620, 470]},
            {'axis': 'y', 'label': 'response (%)', 'unit': '%',
             'type': 'linear',
             'ticks': [{'value': 0, 'px': 462}, {'value': 20, 'px': 374},
                       {'value': 40, 'px': 286}, {'value': 60, 'px': 198},
                       {'value': 80, 'px': 110}, {'value': 100, 'px': 22}],
             'plot_area': [60, 15, 620, 470]},
        ]}
    with open(os.path.join(work, 'axis_spec.json'), 'w') as f:
        json.dump(axis_spec, f, indent=2)

    # agent's figure readings (absolute reading errors ~0.3% of full scale,
    # realistic for pixel reading of a 0-100 axis)
    readings = {'series': [
        {'name': 'WT', 'points': [[d if d > 0 else 0.05, v + 0.3]
                                  for d, v in zip(doses, wt)]},
        {'name': 'KO', 'points': [[d if d > 0 else 0.05, v - 0.25]
                                  for d, v in zip(doses, ko)]}]}
    with open(os.path.join(work, 'figure_readings.json'), 'w') as f:
        json.dump(readings, f, indent=2)

    run([os.path.join(SCRIPTS, 'anchor_figure.py'),
         '--axis', os.path.join(work, 'axis_spec.json'),
         '--readings', os.path.join(work, 'figure_readings.json'),
         '--inventory', os.path.join(work, 'inventory.json'),
         '--work', work])

    run([os.path.join(SCRIPTS, 'crosscheck.py'),
         '--readings', os.path.join(work, 'figure_readings.json'),
         '--anchor', os.path.join(work, 'anchor_map.json'),
         '--inventory', os.path.join(work, 'inventory.json'),
         '--input-dir', inp, '--work', work])

    i10 = doses.index(10.0)
    claims = [
        {'claim': 'WT response at dose 10 uM',
         'value': wt[i10] * 1.01 + 0.4, 'unit': '%',
         'evidence': [
             {'source_type': 'table_cell',
              'locator': 'table_response.csv#row-%d#col-WT_response_pct'
                         % (i10 + 1),
              'verbatim': '10,%.1f,%.1f' % (wt[i10], ko[i10])},
             {'source_type': 'figure_region',
              'locator': 'fig_doseresp.png#axes(60,15)-(620,470)'
                         '#x[9,11]#y[74,80]',
              'verbatim': 'blue circle at dose 10 near 78%'}],
         'crosscheck': 'matched'},
        {'claim': 'KO response at dose 10 uM',
         'value': ko[i10] * 0.99 - 0.3, 'unit': '%',
         'evidence': [
             {'source_type': 'table_cell',
              'locator': 'table_response.csv#row-%d#col-KO_response_pct'
                         % (i10 + 1),
              'verbatim': '10,%.1f,%.1f' % (wt[i10], ko[i10])},
             {'source_type': 'figure_region',
              'locator': 'fig_doseresp.png#axes(60,15)-(620,470)'
                         '#x[9,11]#y[53,59]',
              'verbatim': 'orange square at dose 10 near 55%'}],
         'crosscheck': 'matched'},
        {'claim': 'WT saturates higher than KO',
         'value': '95% vs 61% plateau', 'unit': '%',
         'evidence': [
             {'source_type': 'derived',
              'locator': 'claims[0..1] over dose>=30 uM',
              'verbatim': 'WT plateau mean ~97% vs KO plateau mean ~62%'}],
         'crosscheck': 'matched'}]
    with open(os.path.join(work, 'claims.json'), 'w') as f:
        json.dump(claims, f, indent=2)

    fragment = {
        'answer': 'At dose = 10 uM: WT = %.1f +/- 1.0 %%, KO = %.1f +/- 0.9 %% '
                  '(both confirmed against table_response.csv). WT saturates '
                  'higher (~97%% plateau vs ~62%%).' % (wt[i10], ko[i10]),
        'extracted_values': [
            {'series': 'WT', 'value': round(wt[i10], 1), 'unit': '%',
             'err': 1.0},
            {'series': 'KO', 'value': round(ko[i10], 1), 'unit': '%',
             'err': 0.9}],
        'evidence_map': {'WT@10uM': ['table_response.csv#row-6',
                                     'fig_doseresp.png region x[9,11]'],
                         'KO@10uM': ['table_response.csv#row-6',
                                     'fig_doseresp.png region x[9,11]']}}
    with open(os.path.join(work, 'result_fragment.json'), 'w') as f:
        json.dump(fragment, f, indent=2)

    run([os.path.join(SCRIPTS, 'make_result.py'),
         '--case', os.path.join(inp, 'case.json'),
         '--fragment', os.path.join(work, 'result_fragment.json'),
         '--claims', os.path.join(work, 'claims.json'),
         '--out', os.path.join(out, 'result.json'), '--status', 'success'])

    # --- negative control: a misread axis card (log axis called linear) --
    neg = os.path.join(work, 'neg')
    os.makedirs(neg, exist_ok=True)
    bad = json.loads(json.dumps(axis_spec))
    bad['axes'][0]['type'] = 'linear'
    with open(os.path.join(neg, 'axis_spec_bad.json'), 'w') as f:
        json.dump(bad, f, indent=2)
    print('--- negative control: log axis declared linear (expect hard fail)')
    r = subprocess.run([sys.executable,
                        os.path.join(SCRIPTS, 'anchor_figure.py'),
                        '--axis', os.path.join(neg, 'axis_spec_bad.json'),
                        '--inventory', os.path.join(work, 'inventory.json'),
                        '--work', neg], capture_output=True, text=True)
    print(r.stdout.strip())
    print(r.stderr.strip())
    rep = json.load(open(os.path.join(neg, 'anchor_map.json')))
    assert rep['hard_fail'], 'negative control should hard-fail'
    print('[example] negative control correctly rejected:',
          rep['hard_fail'][0]['check'])
    print('[example] DONE. Inspect %s' % os.path.join(out, 'result.json'))


if __name__ == '__main__':
    main()

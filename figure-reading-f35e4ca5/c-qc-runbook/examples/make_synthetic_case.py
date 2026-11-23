#!/usr/bin/env python3
"""SYNTHETIC EXAMPLE — toy case + full six-gate run, plus fail-mode demo.

Illustrative miniature, NOT an official case and NOT a pre-computed
answer. It fabricates a small case (one figure, one table, a contract),
then runs a complete gated run:

  start_run.py -> gate 1..5 -> finalize.py      (all pass -> success)

and a second, deliberately broken run:

  axis card declaring the log axis "linear" -> gate 2 FAIL
  -> finalize decides honest "partial" with the failing gate named.

Usage:
  python examples/make_synthetic_case.py [workdir]
"""
import json
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
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        doses = [0.1, 0.3, 1, 3, 10, 30, 100]
        resp = [5, 12, 26, 49, 75, 90, 97]
        fig, ax = plt.subplots(figsize=(5, 3.5), dpi=150)
        ax.semilogx(doses, resp, 'o-', color='#0072B2', label='WT')
        ax.set_xlabel('dose (uM)')
        ax.set_ylabel('response (%)')
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(inp, 'fig_2b.png'))
        plt.close(fig)
    except Exception as e:
        print('[example] matplotlib unavailable (%s); figure skipped' % e)
    with open(os.path.join(inp, 'table_response.csv'), 'w') as f:
        f.write('dose_uM,WT_response_pct\n')
        for d, r in zip([0.1, 0.3, 1, 3, 10, 30, 100],
                        [5, 12, 26, 49, 75, 90, 97]):
            f.write('%g,%d\n' % (d, r))
    case = {
        'case_id': 'SYN-QC-EXAMPLE',
        'kind': 'synthetic-illustrative-example',
        'output_contract': {
            'answer': 'free text with units',
            'extracted_values': 'list of {series,value,unit,err}'
        }
    }
    with open(os.path.join(inp, 'case.json'), 'w') as f:
        json.dump(case, f, indent=2)
    with open(os.path.join(inp, 'task.md'), 'w') as f:
        f.write('Report the WT response at dose 10 uM with units and '
                'reading error.\n')
    return inp, work, out


def run(cmd, expect_rc=0):
    r = subprocess.run([sys.executable] + cmd, capture_output=True,
                       text=True)
    line = (r.stdout.strip().splitlines() or [''])[0]
    print('  $', os.path.basename(cmd[0]), ' '.join(
        c for c in cmd[1:] if not c.startswith('/')), '->', line[:150])
    if r.returncode != expect_rc:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit('unexpected rc=%d for %s (wanted %d)'
                         % (r.returncode, cmd[0], expect_rc))
    return r


def good_artifacts(inp, work):
    with open(os.path.join(work, 'inventory.json'), 'w') as f:
        json.dump({
            'files': [{'path': 'fig_2b.png', 'kind': 'figure'},
                      {'path': 'table_response.csv', 'kind': 'table'}],
            'figures': ['fig_2b.png'],
            'tables': ['table_response.csv'],
            'contract_fields': ['answer', 'extracted_values']}, f)
    axis_card = {
        'panel': 'b',
        'axes': [
            {'name': 'x', 'label': 'dose (uM)', 'unit': 'uM',
             'type': 'log',
             'ticks': [{'value': 0.1, 'px': 96}, {'value': 1.0, 'px': 227},
                       {'value': 10.0, 'px': 358},
                       {'value': 100.0, 'px': 489}],
             'plot_area': [60, 15, 620, 470]},
            {'name': 'y', 'label': 'response (%)', 'unit': '%',
             'type': 'linear',
             'ticks': [{'value': 0, 'px': 462}, {'value': 25, 'px': 352},
                       {'value': 50, 'px': 242}, {'value': 75, 'px': 132},
                       {'value': 100, 'px': 22}],
             'plot_area': [60, 15, 620, 470]}]}
    with open(os.path.join(work, 'axis_card.json'), 'w') as f:
        json.dump(axis_card, f, indent=2)
    ledger = {
        'legend_entries': 1,
        'entries': [
            {'element_type': 'series', 'id': 'WT dose-response',
             'status': 'read',
             'locator': 'fig_2b.png#axes(60,15)-(620,470)#x[0.05,100]'
                        '#y[2,98]',
             'value': '7 points, +/-1.0% FS reading error'},
            {'element_type': 'errorbar', 'id': 'WT error bars',
             'status': 'not_present',
             'locator': 'fig_2b.png#whole',
             'value': 'none drawn'},
            {'element_type': 'significance_mark', 'id': 'none',
             'status': 'not_present', 'locator': 'fig_2b.png#whole'}]}
    with open(os.path.join(work, 'element_ledger.json'), 'w') as f:
        json.dump(ledger, f, indent=2)
    with open(os.path.join(work, 'crosscheck.json'), 'w') as f:
        json.dump({
            'figure_vs_table': {'checked': 7, 'matched': 7,
                                'median_rel_err': 0.012},
            'caption_semantics_checked': True,
            'notes': ['table_response.csv row values match figure points '
                      'within reading tolerance; no caption shipped with '
                      'the synthetic case']}, f)


def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
        os.path.abspath('synthetic_run_c')
    inp, work, out = gen_case(root)
    case_p = os.path.join(inp, 'case.json')

    print('--- run 1: disciplined run (all gates should pass)')
    run([os.path.join(SCRIPTS, 'start_run.py'), '--case', case_p,
         '--task', os.path.join(inp, 'task.md'),
         '--work', work, '--out', out])
    good_artifacts(inp, work)
    for g in (1, 2, 3, 4):
        run([os.path.join(SCRIPTS, 'gate.py'), '--gate', str(g),
             '--work', work, '--case', case_p])
    # agent fills the contract fields between g4 and g5
    result = json.load(open(os.path.join(out, 'result.json')))
    result['answer'] = 'WT response at dose 10 uM is 75% +/- 1.5% ' \
                       '(figure reading confirmed by ' \
                       'table_response.csv row 5).'
    result['extracted_values'] = [
        {'series': 'WT', 'value': 75.2, 'unit': '%', 'err': 1.5}]
    with open(os.path.join(out, 'result.json'), 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    run([os.path.join(SCRIPTS, 'gate.py'), '--gate', '5',
         '--work', work, '--out', out, '--case', case_p])
    run([os.path.join(SCRIPTS, 'finalize.py'),
         '--work', work, '--out', out, '--case', case_p,
         '--claim-status', 'success'])
    r1 = json.load(open(os.path.join(out, 'result.json')))
    assert r1['status'] == 'success', r1
    print('  run 1 decided:', r1['status'])

    print('--- run 2: broken run (log axis declared linear; g2 must fail)')
    work2 = os.path.join(root, 'work_bad')
    out2 = os.path.join(root, 'output_bad')
    run([os.path.join(SCRIPTS, 'start_run.py'), '--case', case_p,
         '--task', os.path.join(inp, 'task.md'),
         '--work', work2, '--out', out2])
    good_artifacts(inp, work2)
    bad_card = json.load(open(os.path.join(work2, 'axis_card.json')))
    bad_card['axes'][0]['type'] = 'linear'
    with open(os.path.join(work2, 'axis_card.json'), 'w') as f:
        json.dump(bad_card, f, indent=2)
    run([os.path.join(SCRIPTS, 'gate.py'), '--gate', '1',
         '--work', work2, '--case', case_p])
    run([os.path.join(SCRIPTS, 'gate.py'), '--gate', '2',
         '--work', work2, '--case', case_p], expect_rc=2)
    # agent ships partial anyway (fields still null) and finalizes
    run([os.path.join(SCRIPTS, 'finalize.py'),
         '--work', work2, '--out', out2, '--case', case_p,
         '--claim-status', 'success'])
    r2 = json.load(open(os.path.join(out2, 'result.json')))
    assert r2['status'] == 'partial', r2
    assert 'g2' in r2.get('status_reason', ''), r2
    print('  run 2 decided:', r2['status'], '-', r2['status_reason'])
    print('[example] DONE. Reports: %s and %s'
          % (os.path.join(out, 'run_report.md'),
             os.path.join(out2, 'run_report.md')))


if __name__ == '__main__':
    main()

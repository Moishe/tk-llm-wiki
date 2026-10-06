"""Self-check for delta.py's shared_min_members filter: python3 test_delta.py"""
import pathlib, subprocess, sys, tempfile

d = pathlib.Path(tempfile.mkdtemp())
cols = 'id\tcreated_at\tupdated_at\tcreated_by_ai\tdaily_note_kind\ttags\ttitle\tis_shared_to_profile\tlibrary_ids'
rows = [
    'profile\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tA\ttrue\t',
    'biglib\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tB\tfalse\tbig',
    'smalllib\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tC\tfalse\tsmall',
    'unknownlib\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tD\tfalse\tgone',
    'private\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tE\tfalse\t',
    'mixed\t2026-09-01\t2026-09-01T00:00:00Z\tfalse\t\t\tF\tfalse\tsmall|big',
]
(d / 'all.tsv').write_text('\n'.join([cols] + rows) + '\n')
(d / 'filter.json').write_text('{"shared_min_members": 5}')
(d / 'libraries.tsv').write_text('big\t40\nsmall\t2\n')
(d / 'processed.tsv').write_text('')
out = subprocess.run([sys.executable, pathlib.Path(__file__).with_name('delta.py'), d], capture_output=True, text=True, check=True).stdout
got = {l.split('\t')[0] for l in (d / 'delta.tsv').read_text().splitlines()[1:]}
assert got == {'profile', 'biglib', 'mixed'}, got
print('ok:', out.strip())

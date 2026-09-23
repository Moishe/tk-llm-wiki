"""Verifies reader digests before synthesis: every delta id has exactly one entry,
updated_at copied exactly, and a verdict. Exits non-zero on any gap.

Usage: python3 check_digests.py <workdir>   (reads delta.tsv and digest-*.md)
"""
import csv, re, glob, collections, pathlib, sys

def main(d):
    d = pathlib.Path(d)
    want = {r['id']: r for r in csv.DictReader(open(d / 'delta.tsv'), delimiter='\t')}
    seen, bad_ts, dup, verdicts = {}, [], [], collections.Counter()
    for f in sorted(glob.glob(str(d / 'digest-*.md'))):
        for m in re.finditer(r'^### ([0-9a-f-]{36}) \|.*?(?=^### |\Z)', open(f).read(), re.M | re.S):
            i, body = m.group(1), m.group(0)
            if i in seen: dup.append(i)
            seen[i] = f
            t = re.search(r'updated_at: (\S+)', body)
            if i in want and (not t or t.group(1) != want[i]['updated_at']): bad_ts.append(i)
            v = re.search(r'verdict: ([a-z-]+)', body)
            verdicts[v.group(1) if v else 'MISSING'] += 1
    missing, extra = sorted(set(want) - set(seen)), sorted(set(seen) - set(want))
    print(f"entries={len(seen)} expected={len(want)} missing={len(missing)} extra={len(extra)} "
          f"dup={len(dup)} bad_updated_at={len(bad_ts)}")
    print('verdicts:', dict(verdicts))
    for label, xs in (('missing', missing), ('extra', extra), ('dup', dup), ('bad_updated_at', bad_ts)):
        if xs: print(label, xs[:10])
    return 1 if missing or extra or dup or bad_ts or verdicts['MISSING'] else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))

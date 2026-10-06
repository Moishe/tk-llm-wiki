"""Deterministic delta for a collection-scope batch ingest.

Usage: python3 delta.py <workdir>
Reads   <workdir>/all.tsv        every doc the user owns (id, created_at, updated_at,
                                 created_by_ai, daily_note_kind, tags "|"-joined, title)
        <workdir>/filter.json    the index's Scope filter (keys below; all optional)
        <workdir>/processed.tsv  processed-set: id <TAB> recorded updated_at (Sources + Skipped)
Writes  <workdir>/delta.tsv      matching docs that are new, or edited since recorded
Prints  counts, including departures (processed ids no longer in scope).

filter.json keys: created_by_ai (bool), created_after / created_before (ISO date),
tags_any / tags_none (list), daily_note_kind_none (list), title_excludes (list of substrings),
shared_min_members (int): on the profile, or in a library with >= N members. Needs all.tsv
columns is_shared_to_profile and library_ids ("|"-joined), and <workdir>/libraries.tsv
(library_id <TAB> member_count). A library missing from libraries.tsv counts as unshared.
"""
import csv, json, sys, pathlib
from datetime import datetime

ts = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))

def shared(r, n, members):
    libs = filter(None, r['library_ids'].split('|'))
    return r['is_shared_to_profile'] == 'true' or any(members.get(l, 0) >= n for l in libs)

def passes(r, f, members):
    tags = set(filter(None, r['tags'].split('|')))
    created = r['created_at'][:10]
    return all([
        'created_by_ai' not in f or (r['created_by_ai'] == 'true') == f['created_by_ai'],
        'created_after' not in f or created >= f['created_after'],
        'created_before' not in f or created < f['created_before'],
        'tags_any' not in f or tags & set(f['tags_any']),
        not tags & (set(f.get('tags_none', [])) | {'llm-wiki'}),  # the skill's own docs, always
        r['daily_note_kind'] not in f.get('daily_note_kind_none', []),
        not any(s in r['title'] for s in f.get('title_excludes', [])),
        'shared_min_members' not in f or shared(r, f['shared_min_members'], members),
    ])

def main(d):
    d = pathlib.Path(d)
    f = json.loads((d / 'filter.json').read_text())
    rows = list(csv.DictReader(open(d / 'all.tsv'), delimiter='\t'))
    ids = [r['id'] for r in rows]
    assert len(ids) == len(set(ids)), 'duplicate ids in all.tsv'
    processed = dict(l.rstrip('\n').split('\t') for l in open(d / 'processed.tsv') if l.strip())
    members = {}
    if 'shared_min_members' in f:
        members = {l: int(n) for l, n in (x.rstrip('\n').split('\t') for x in open(d / 'libraries.tsv') if x.strip())}
    match = [r for r in rows if passes(r, f, members)]
    delta = [r for r in match if r['id'] not in processed or ts(r['updated_at']) > ts(processed[r['id']])]
    departures = sorted(set(processed) - {r['id'] for r in match})
    with open(d / 'delta.tsv', 'w') as out:
        w = csv.DictWriter(out, fieldnames=rows[0].keys(), delimiter='\t')
        w.writeheader(); w.writerows(delta)
    print(f"rows={len(rows)} match={len(match)} delta={len(delta)} "
          f"edited={sum(r['id'] in processed for r in delta)} departures={len(departures)}")
    for i in departures: print('departure', i)

if __name__ == '__main__':
    main(sys.argv[1])

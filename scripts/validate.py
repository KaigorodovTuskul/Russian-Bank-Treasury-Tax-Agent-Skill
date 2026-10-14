#!/usr/bin/env python3
"""Validate Agent Skills structure and research-preview fixture metadata offline."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/russian-bank-treasury-tax/SKILL.md'
DATA=ROOT/'tests/fixtures/bond_synthetic_cases.json'

def validate():
    content=SKILL.read_text(encoding='utf-8')
    assert content.startswith('---\n'),'SKILL.md must have frontmatter'
    parts=content.split('---\n',2)
    assert len(parts)==3,'invalid frontmatter terminator'
    header=parts[1]
    match=re.search(r'^name:\s*(\S+)\s*$',header,re.M)
    assert match and match.group(1)==SKILL.parent.name,'invalid skill name'
    name=match.group(1)
    assert len(name)<=64 and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',name),'invalid slug'
    desc=re.search(r'^description:\s*(.+)$',header,re.M)
    assert desc and 1<=len(desc.group(1))<=1024,'invalid description'
    assert parts[2].strip(),'empty skill instructions'
    for link in re.findall(r'\]\(([^)]+)\)',parts[2]):
        if '://' in link or link.startswith('#'): continue
        path=(SKILL.parent/link.split('#',1)[0]).resolve()
        assert path.is_file(),f'broken relative link: {link}'
    data=json.loads(DATA.read_text(encoding='utf-8'))
    assert data['status']=='SYNTHETIC_ONLY_NOT_LEGALLY_VALIDATED'
    ids=set()
    for case in data['cases']:
        assert case['id'] not in ids,'duplicate fixture id'
        ids.add(case['id'])
        assert case['scope']=='synthetic'
        assert case['legal_status'] in ('PROVISIONAL','BLOCKED')
        assert case['decision']==case['legal_status']
        assert case['required_evidence'],'evidence checklist missing'
        if case['decision']=='BLOCKED':
            assert case['expected'].get('approved_tax_amount') is None
            assert case['expected'].get('stop_reason')
    assert len(data['cases'])>=7,'missing sample fixture coverage'
    print(f'PASS: skill metadata, linked references, {len(data["cases"])} provisional fixtures')

if __name__=='__main__': validate()

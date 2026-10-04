#!/usr/bin/env python3
"""Optional independent schema-conformance check. Never executes package content."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    print('Optional check needs jsonschema; runtime client and tests have no dependencies.',file=sys.stderr)
    raise SystemExit(2)
from depot.core import load_json
from scripts.make_demo import create_demo
root=Path(__file__).resolve().parents[1]
validators={}
for path in sorted((root/'schemas').glob('*.json')):
    schema=load_json(path.read_bytes());Draft202012Validator.check_schema(schema)
    validators[path.name.split('.')[0]]=Draft202012Validator(schema,format_checker=FormatChecker())
    print('PASS schema',path.name)
with tempfile.TemporaryDirectory(prefix='depot-schema-') as temporary:
    base=Path(temporary)/'demo';create_demo(base)
    files=[('package',p) for p in (base/'mirror/packages').rglob('*.json')]+[('audit',p) for p in (base/'mirror/audits').rglob('*.json')]+[('approval',p) for p in (base/'approvals').glob('*.json')]+[('catalog',base/'catalog/catalog/index.json')]
    for kind,path in files:validators[kind].validate(load_json(path.read_bytes()))
    print('PASS',len(files),'generated package/audit/approval/catalog documents against independent validator')

#!/usr/bin/env python3
"""Build an inert review packet from immutable local Git objects. Run no tests/hooks."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.core import (DepotError, archive_bytes, canonical, document, inspect_git,
                        regular_bytes, require, safe_directory, sha, tree_digest)


def make_report(manifest, data, entries, synthetic=False):
    require(tree_digest(entries)==manifest['tree_sha256'],'declared tree digest differs from immutable source')
    require([name for name,mode,_ in entries if mode==0o755]==sorted(manifest['executables']),'executable declaration mismatch')
    findings=[]
    for name,_,body in entries:
        try:
            text=body.decode('utf-8')
            require('\x00' not in text,'binary source requires separately explained review; unsupported in 0.1')
        except UnicodeError as exc:
            raise DepotError('binary source unsupported in 0.1') from exc
        for pattern,label in [(r'curl\s.*\|\s*(sh|bash)','pipe installer'),(r'\b(eval|exec)\s*\(','dynamic execution'),(r'\b(sudo|chmod\s+777)\b','privilege request'),(r'https?://','network reference')]:
            if re.search(pattern,text):
                findings.append({'file':name,'finding':label,'severity':'review-required'})
    return {'schema':'dots-depot-inspection/1','package':manifest['id'],'version':manifest['version'],
            'manifest_sha256':sha(data),'tree_sha256':manifest['tree_sha256'],'source':manifest['source'],
            'files':[{'path':n,'mode':format(m,'04o'),'bytes':len(b),'sha256':sha(b)} for n,m,b in entries],
            'dependencies':manifest['dependencies'],'requests':manifest['requests'],'executables':manifest['executables'],
            'findings':findings,'tests_executed':False,'synthetic':synthetic,
            'assessment':'Static enumeration only. Human review and trusted CI evidence remain required. No package code ran.'}
def inspect(repository, manifest_path, output, synthetic=False):
    data=regular_bytes(manifest_path)
    manifest=document(data,'package')
    entries=inspect_git(repository,manifest['source'])
    report=make_report(manifest,data,entries,synthetic)
    output=Path(output)
    output=safe_directory(output.parent,create=True)/output.name
    require(not output.exists() and not output.is_symlink(),'review packet output must be new')
    output.mkdir(mode=0o700)
    for name,body in [('manifest.json',data),('report.json',canonical(report)),('source.tar',archive_bytes(entries))]:
        (output/name).write_bytes(body)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',required=True,type=Path);p.add_argument('--manifest',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--synthetic',action='store_true')
    a=p.parse_args()
    try:
        print(json.dumps(inspect(a.repository,a.manifest,a.output,a.synthetic),indent=2));return 0
    except (DepotError,OSError) as exc:
        print('Depot refused: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

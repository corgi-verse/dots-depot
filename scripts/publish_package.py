#!/usr/bin/env python3
"""Record exact LOCAL maintainer approval. This script never publishes remotely.

Only a trusted human maintainer may invoke approve for real releases. A submitted
manifest, audit or claimed reviewer identity cannot grant this authority.
"""
import argparse
import datetime as dt
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.core import (DepotError, canonical, document, load_json, regular_bytes, require,
                        safe_directory, sha, tree_digest, unpack)
from depot.catalog import release_paths
from scripts.inspect_submission import make_report


def approval_token(manifest, manifest_data, report_data, archive, test_data=None):
    return ':'.join([manifest['id']+'@'+manifest['version'],sha(manifest_data),manifest['tree_sha256'],manifest['source']['commit'],manifest['source']['subtree'],sha(report_data),sha(archive),sha(test_data) if test_data is not None else 'not-run'])


def approve(packet, mirror, approvals, auditor, confirmation, tests_passed, synthetic=False, test_evidence=None):
    packet=safe_directory(packet)
    require(set(p.name for p in packet.iterdir())=={'manifest.json','report.json','source.tar'},'unexpected review packet files')
    mdata=regular_bytes(packet/'manifest.json');manifest=document(mdata,'package')
    report_data=regular_bytes(packet/'report.json');report=load_json(report_data)
    archive=regular_bytes(packet/'source.tar',10*1024*1024)
    entries=unpack(archive)
    require(tree_digest(entries)==manifest['tree_sha256'],'review packet tree mismatch')
    require(canonical(report) == canonical(make_report(manifest,mdata,entries,synthetic)),'review report mismatch: exact static enumeration required')
    require(report.get('findings')==[], 'static findings must be resolved in a new packet before approval')
    test_data = regular_bytes(test_evidence) if test_evidence is not None else None
    if test_data is None:
        require(tests_passed == 0, 'nonzero test count requires exact human-reviewed CI evidence')
    else:
        tests = document(test_data,'tests')
        require(tests['package']==manifest['id'] and tests['version']==manifest['version'] and tests['source']==manifest['source'] and tests['tree_sha256']==manifest['tree_sha256'], 'CI evidence release mismatch')
        require(tests['tests_passed']==tests_passed, 'CI evidence count mismatch')
    require(confirmation==approval_token(manifest,mdata,report_data,archive,test_data),'exact confirmation token required; print packet token for human review first')
    status='synthetic' if synthetic else 'approved'
    audit={'schema':'dots-depot-audit/1','package':manifest['id'],'version':manifest['version'],
           'source':manifest['source'],'tree_sha256':manifest['tree_sha256'],'manifest_sha256':sha(mdata),
           'permissions':manifest['requests'],'audit':{'status':status,'auditor':auditor,'reviewed_at':dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')},
           'verification':{'tests_passed':tests_passed,'static_scan':'pass','report_sha256':sha(report_data),
                           'tests_status':'human-reviewed-ci' if test_data is not None else 'not-run','tests_sha256':sha(test_data) if test_data is not None else 'not-run'}}
    adata=canonical(audit);document(adata,'audit')
    approval={'schema':'dots-depot-approval/1','package':manifest['id'],'version':manifest['version'],
              'manifest_sha256':sha(mdata),'audit_sha256':sha(adata),'tree_sha256':manifest['tree_sha256'],
              'commit':manifest['source']['commit'],'subtree':manifest['source']['subtree'],'kind':'synthetic' if synthetic else 'human'}
    pdata=canonical(approval);document(pdata,'approval')
    mirror=safe_directory(mirror,create=True);approvals=safe_directory(approvals,create=True)
    paths=release_paths(mirror,manifest['id'],manifest['version'])
    approval_path=approvals/(manifest['id']+'@'+manifest['version']+'.json')
    require(all(not p.exists() and not p.is_symlink() for p in (*paths,approval_path)),'immutable release already exists; never overwrite')
    for path,data in zip(paths,(mdata,adata,archive)):
        safe_directory(path.parent,create=True)
        with path.open('xb') as stream:stream.write(data)
    with approval_path.open('xb') as stream:stream.write(pdata)
    approval_path.chmod(0o600)
    return approval


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['token','approve']);p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--mirror',type=Path);p.add_argument('--approvals',type=Path)
    p.add_argument('--auditor');p.add_argument('--confirmation');p.add_argument('--tests-passed',type=int,default=0)
    p.add_argument('--test-evidence',type=Path,help='Human-reviewed isolated CI result; never executes tests')
    p.add_argument('--synthetic',action='store_true')
    a=p.parse_args()
    try:
        if a.action=='token':
            data=regular_bytes(a.packet/'manifest.json');report=regular_bytes(a.packet/'report.json');archive=regular_bytes(a.packet/'source.tar',10*1024*1024)
            tests=regular_bytes(a.test_evidence) if a.test_evidence is not None else None
            print(approval_token(document(data,'package'),data,report,archive,tests))
        else:
            require(all([a.mirror,a.approvals,a.auditor,a.confirmation]),'approve requires mirror, approvals, auditor and exact confirmation')
            print(canonical(approve(a.packet,a.mirror,a.approvals,a.auditor,a.confirmation,a.tests_passed,a.synthetic,a.test_evidence)).decode(),end='')
        return 0
    except (DepotError,OSError) as exc:
        print('Depot refused: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Reproducible original synthetic fixtures; never grants human release approval."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.core import canonical, git, tree_digest, require
from depot.catalog import build
from scripts.inspect_submission import inspect
from scripts.publish_package import approve, approval_token


def create_demo(base):
    base=Path(base);require(not base.exists(),'demo base must be new');base.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='depot-fixture-source-') as temporary:
        repo=Path(temporary)
        env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,
                 GIT_AUTHOR_NAME='Synthetic Fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',
                 GIT_COMMITTER_NAME='Synthetic Fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid',
                 GIT_AUTHOR_DATE='2026-10-04T00:00:00Z',GIT_COMMITTER_DATE='2026-10-04T00:00:00Z')
        subprocess.run(['git','init','-q','-b','main',str(repo)],check=True,env=env)
        items=[('warehouse-note','recipe',{'README.txt':b'SYNTHETIC WAREHOUSE NOTE\nThis original fixture is inert data, not the real Paste Inbox.\n'},[]),
               ('inert-tool','tool',{'README.txt':b'SYNTHETIC INERT TOOL\nNever execute this staged fixture.\n','run.sh':b'#!/bin/sh\nprintf executed > should-never-exist\n'},['run.sh'])]
        for slug,_,files,executables in items:
            folder=repo/'parts'/slug;folder.mkdir(parents=True)
            for name,data in files.items():
                target=folder/name;target.write_bytes(data);target.chmod(0o755 if name in executables else 0o644)
        subprocess.run(['git','-C',str(repo),'add','parts'],check=True,env=env)
        subprocess.run(['git','-C',str(repo),'-c','core.hooksPath='+os.devnull,'commit','-qm','Original synthetic fixtures'],check=True,env=env)
        commit=git(repo,'rev-parse','HEAD').decode().strip()
        for slug,kind,files,executables in items:
            source={'repository':'https://github.com/fixture/warehouse','commit':commit,'path':'parts/'+slug,
                    'subtree':git(repo,'rev-parse',commit+':parts/'+slug).decode().strip()}
            entries=[(n,0o755 if n in executables else 0o644,b) for n,b in files.items()]
            m={'schema':'dots-depot-package/1','id':'fixture.'+slug,'name':slug.replace('-',' ').title()+' (Synthetic)',
               'version':'0.1.0','type':kind,'summary':'An original synthetic fixture for inspecting the Depot pipeline. No human approval.',
               'license':'Apache-2.0','source':source,'tree_sha256':tree_digest(entries),
               'compatibility':{'dotsys':['0.1.0'],'platform':['macos-arm64','linux-x86_64'],'python':'>=3.12'},
               'requests':{'workspace_read':[],'workspace_write':[],'network':[],'credentials':[],
                           'public_publish':False,'account_changes':False,'paid_services':False},
               'dependencies':[],'executables':executables,'audit':'audits/fixture.'+slug+'/0.1.0.json'}
            data=canonical(m);mp=base/(slug+'.json');mp.write_bytes(data);packet=base/'packets'/slug
            inspect(repo,mp,packet,synthetic=True)
            approve(packet,base/'mirror',base/'approvals','Synthetic fixture simulator',approval_token(m,data,(packet/'report.json').read_bytes(),(packet/'source.tar').read_bytes()),0,synthetic=True)
        return build(base/'mirror',base/'approvals',base/'catalog',demo=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(create_demo(a.output))
if __name__=='__main__':main()

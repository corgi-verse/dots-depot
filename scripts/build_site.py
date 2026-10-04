#!/usr/bin/env python3
"""Create a static site using explicit public catalogs and original web assets."""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.catalog import build, load_catalog
from depot.core import require, safe_directory
ROOT=Path(__file__).resolve().parents[1]

def build_site(output,mirror=None,approvals=None):
    output=Path(output);output=safe_directory(output.parent,create=True)/output.name
    require(not output.exists() and not output.is_symlink(),'site output must be a new directory')
    require((mirror is None)==(approvals is None),'mirror and maintainer approvals must be supplied together')
    if mirror is not None:
        build(mirror,approvals,output)
    else:
        # Trusted catalog deliberately empty until actual human approvals exist.
        with tempfile.TemporaryDirectory(prefix='depot-empty-') as temporary:
            base=Path(temporary);(base/'mirror').mkdir();(base/'approvals').mkdir()
            build(base/'mirror',base/'approvals',output)
    for item in (ROOT/'apps/web').iterdir():
        destination=output/item.name
        if item.is_dir():shutil.copytree(item,destination)
        else:shutil.copyfile(item,destination)
    shutil.copytree(ROOT/'schemas',output/'schemas')
    demo=ROOT/'build/demo/catalog'
    if demo.exists():
        load_catalog(demo,allow_synthetic=True);shutil.copytree(demo,output/'demo')
    return output
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--mirror',type=Path);p.add_argument('--approvals',type=Path)
    a=p.parse_args();print(build_site(a.output,a.mirror,a.approvals))

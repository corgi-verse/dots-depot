#!/usr/bin/env python3
"""Create a static site using explicit public catalogs and original web assets."""
import argparse
from html import escape
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.catalog import build, load_catalog
from depot.core import require, safe_directory
ROOT=Path(__file__).resolve().parents[1]

DEFAULT_INSTANCE_NAME='Dots Depot'

def render_instance(html,instance_name):
    """Render display-only branding without changing package or trust identities."""
    name=escape(instance_name,quote=True)
    html=html.replace('data-instance-name="Dots Depot"',f'data-instance-name="{name}"')
    html=html.replace('aria-label="Dots Depot home"',f'aria-label="{name} home"')
    html=html.replace('name="application-name" content="Dots Depot"',f'name="application-name" content="{name}"')
    html=re.sub(r'<title>(.*?)</title>',lambda m:'<title>'+m[1].replace('Dots Depot',name)+'</title>',html)
    if instance_name != DEFAULT_INSTANCE_NAME:
        html=re.sub(r'<span data-instance-name>.*?</span>',lambda _m:f'<span data-instance-name>{name}</span>',html)
        html=html.replace('data-instance-attribution>BY CORGI-VERSE SOFTWARE','data-instance-attribution>Powered by Dots Depot')
    return html

def build_site(output,mirror=None,approvals=None,instance_name=DEFAULT_INSTANCE_NAME):
    require(isinstance(instance_name,str),'instance name must be text')
    instance_name=instance_name.strip()
    require(1<=len(instance_name)<=80 and all(c.isprintable() for c in instance_name),'instance name must be 1–80 printable characters')
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
    for page in output.glob('*.html'):
        page.write_text(render_instance(page.read_text(encoding='utf-8'),instance_name),encoding='utf-8')
    demo=ROOT/'build/demo/catalog'
    if demo.exists():
        load_catalog(demo,allow_synthetic=True);shutil.copytree(demo,output/'demo')
        # Navigation is offered only in outputs containing validated fixtures.
        for page in output.glob('*.html'):
            html=page.read_text(encoding='utf-8')
            html=html.replace('<body', '<body data-demo-available="true"', 1)
            page.write_text(html,encoding='utf-8')
    return output
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--mirror',type=Path);p.add_argument('--approvals',type=Path)
    p.add_argument('--instance-name',default=os.environ.get('DEPOT_INSTANCE_NAME',DEFAULT_INSTANCE_NAME),help='Public display name (or DEPOT_INSTANCE_NAME); defaults to Dots Depot')
    a=p.parse_args();print(build_site(a.output,a.mirror,a.approvals,a.instance_name))

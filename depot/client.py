"""Standard-library local client. No network, package execution or activation."""
from pathlib import Path
import argparse
import json
import os
import shutil
import stat
import tempfile
from .catalog import load_catalog, release
from .core import DepotError, canonical, document, regular_bytes, require, safe_directory, tree_digest


def receipt(manifest,entry,pin):
    return {'schema':'dots-depot-stage/1','package':manifest['id'],'version':manifest['version'],
            'catalog_sha256':pin,'manifest_sha256':entry['manifest_sha256'],
            'audit_sha256':entry['audit_sha256'],'tree_sha256':manifest['tree_sha256'],
            'commit':manifest['source']['commit'],'subtree':manifest['source']['subtree'],'executed':False}


def stage(root, package, version, destination, pin, demo=False):
    require(pin is not None, 'stage requires an independently trusted --catalog-sha256 pin')
    manifest,audit,entries,entry,fingerprint = release(root,package,version,pin,demo)
    parent = safe_directory(destination,create=True)
    destination = parent / (manifest['id'] + '@' + manifest['version'])
    require(not destination.exists() and not destination.is_symlink(), 'stage already exists; verify or choose another staging directory')
    temporary = Path(tempfile.mkdtemp(prefix='.depot-stage-',dir=parent))
    try:
        content = temporary/'content'
        content.mkdir(mode=0o700)
        for name,_,data in entries:
            target = content/name
            target.parent.mkdir(mode=0o700, parents=True,exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(0o600)  # Never preserve executable bits while staging.
        target = temporary/'receipt.json'
        target.write_bytes(canonical(receipt(manifest,entry,fingerprint)))
        target.chmod(0o600)
        verify(root,temporary,pin,demo)
        os.rename(temporary,destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def verify(root, stage_path, pin, demo=False):
    require(pin is not None, 'verify requires independently trusted --catalog-sha256 pin')
    stage_path = safe_directory(stage_path)
    require(set(p.name for p in stage_path.iterdir())=={'content','receipt.json'}, 'unexpected staging metadata')
    record = document(regular_bytes(stage_path/'receipt.json'), 'receipt')
    require(stat.S_IMODE((stage_path/'receipt.json').stat().st_mode)==0o600, 'receipt permissions changed')
    manifest,_,expected,entry,fingerprint = release(root,record['package'],record['version'],pin,demo)
    require(record==receipt(manifest,entry,fingerprint), 'staging receipt mismatch')
    content = safe_directory(stage_path/'content')
    wanted = {name:mode for name,mode,_ in expected}
    directories = {str(Path(name).parent) for name in wanted}
    for name in list(directories):
        directories.update(str(p) for p in Path(name).parents)
    actual = []
    for current, dirs, files in os.walk(content,followlinks=False):
        for name in dirs:
            p = Path(current)/name
            require(not p.is_symlink() and str(p.relative_to(content)) in directories, 'unexpected or symlink staging directory')
        for name in files:
            p = Path(current)/name
            relative = p.relative_to(content).as_posix()
            require(relative in wanted, 'extra staging file')
            require(not p.is_symlink() and stat.S_IMODE(p.stat().st_mode)==0o600, 'unsafe staging file mode or symlink')
            actual.append((relative,wanted[relative],regular_bytes(p,1024*1024)))
    require(len(actual)==len(expected) and tree_digest(actual)==manifest['tree_sha256'], 'staged tree tampered or incomplete')
    return record


def main(argv=None):
    parser=argparse.ArgumentParser(description='Dots Depot 0.1 — inspect, stage and verify. Nothing is activated.')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'site')
    parser.add_argument('--catalog-sha256',help='Pin obtained from the trusted maintainer, independently of downloaded metadata')
    parser.add_argument('--demo',action='store_true',help='Explicitly allow synthetic fixtures; never human audited')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('search');p.add_argument('query',nargs='?',default='')
    p=sub.add_parser('info');p.add_argument('package');p.add_argument('--version',required=True)
    p=sub.add_parser('stage');p.add_argument('package');p.add_argument('--version',required=True);p.add_argument('--destination',type=Path,required=True)
    p=sub.add_parser('verify');p.add_argument('path',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=='search':
            index,_=load_catalog(args.root,args.catalog_sha256,args.demo)
            entries=[e for e in index['packages'] if args.query.casefold() in ' '.join(str(e[k]) for k in ('name','summary','id','type')).casefold()]
            print(json.dumps(entries,indent=2))
        elif args.command=='info':
            # Info enumerates the pinned source and declarations; no stage side effect.
            index,pin=load_catalog(args.root,args.catalog_sha256,args.demo)
            m,a,_,_,_=release(args.root,args.package,args.version,pin,args.demo)
            print(json.dumps({'package':m,'audit':a,'authority':'Metadata grants no permissions. Stage does not activate.'},indent=2))
        elif args.command=='stage':
            print(stage(args.root,args.package,args.version,args.destination,args.catalog_sha256,args.demo))
        elif args.command=='verify':
            print(json.dumps(verify(args.root,args.path,args.catalog_sha256,args.demo),indent=2))
        return 0
    except (DepotError,OSError,TypeError,KeyError,ValueError) as exc:
        print('Depot refused: '+str(exc),file=__import__('sys').stderr)
        return 2

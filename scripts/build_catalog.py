#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.catalog import build
from depot.core import DepotError

def main():
    p=argparse.ArgumentParser(description='Generate a NEW local allowlist mirror from exact maintainer approval records.')
    p.add_argument('--mirror',type=Path,required=True);p.add_argument('--approvals',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--demo',action='store_true')
    a=p.parse_args()
    try:
        print(build(a.mirror,a.approvals,a.output,a.demo));return 0
    except (DepotError,OSError) as exc:
        print('Depot refused: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())

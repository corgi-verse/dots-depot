#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from depot.core import DepotError, regular_bytes, tree_digest, unpack
p=argparse.ArgumentParser(description='Digest canonical inert USTAR package bytes.')
p.add_argument('archive',type=Path);a=p.parse_args()
try: print(tree_digest(unpack(regular_bytes(a.archive,10*1024*1024))))
except DepotError as exc: print('Depot refused: '+str(exc),file=sys.stderr);raise SystemExit(2)

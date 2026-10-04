"""A generated allowlist is the trust root; peer receipts are never approvals."""
from pathlib import Path
import os
import shutil
import tempfile
from .core import (DepotError, archive_bytes, bind, canonical, document, load_json,
                   path_label, regular_bytes, require, safe_directory, sha, tree_digest, unpack)


def release_paths(root, package, version):
    # Validate identifiers before constructing any filesystem path.
    import re
    require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*', package)), 'invalid package id')
    require(bool(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version)), 'invalid version')
    return (root / 'packages' / package / (version + '.json'),
            root / 'audits' / package / (version + '.json'),
            root / 'artifacts' / package / (version + '.tar'))


def checked_file(root, relative, limit):
    path_label(relative)
    path = root / relative
    safe_directory(path.parent)
    return regular_bytes(path, limit)


def build(root, approvals, output, demo=False):
    """Local build only. Approval directory belongs to the maintainer, not submitters."""
    root = safe_directory(root)
    approvals = safe_directory(approvals)
    output = Path(os.path.abspath(output))
    # Rebuilding into an existing output could retain private/stale bytes. Never
    # delete it silently. The user chooses a new clean output per build.
    output = safe_directory(output.parent, create=True) / output.name
    require(not output.exists() and not output.is_symlink(), 'output must be a new directory')
    require(not output.is_relative_to(root) and not root.is_relative_to(output), 'output must be separate from release mirror')
    entries = []
    assets = []
    seen = set()
    for approval_path in sorted(approvals.iterdir()):
        require(approval_path.suffix == '.json', 'unexpected file in approval store')
        approval = document(regular_bytes(approval_path), 'approval')
        kind = 'synthetic' if demo else 'human'
        require(approval['kind'] == kind, 'approval type does not match build mode')
        key = (approval['package'], approval['version'])
        require(key not in seen, 'duplicate approved release')
        seen.add(key)
        paths = release_paths(root, *key)
        mdata, adata, archive = [checked_file(root, str(p.relative_to(root)), limit) for p, limit in zip(paths, (128*1024,128*1024,10*1024*1024))]
        manifest, audit = bind(mdata, adata, allow_synthetic=demo)
        require(audit['audit']['status'] == ('synthetic' if demo else 'approved'), 'audit status does not match approval')
        for field, actual in [('manifest_sha256', sha(mdata)), ('audit_sha256', sha(adata)), ('tree_sha256',manifest['tree_sha256']), ('commit',manifest['source']['commit']), ('subtree',manifest['source']['subtree'])]:
            require(approval[field] == actual, 'approval does not bind exact release: ' + field)
        source_entries = unpack(archive)
        require(tree_digest(source_entries) == manifest['tree_sha256'], 'release tree digest mismatch')
        actual_executables = [name for name, mode, _ in source_entries if mode == 0o755]
        require(actual_executables == sorted(manifest['executables']), 'executable declaration mismatch')
        entry = {key:manifest[key] for key in ('id','version','name','type','summary','tree_sha256')}
        entry.update(manifest_sha256=sha(mdata), audit_sha256=sha(adata), archive_sha256=sha(archive), synthetic=demo)
        entries.append(entry)
        assets.extend(zip(paths, (mdata, adata, archive)))
    index = {'schema':'dots-depot-catalog/1', 'mode':'synthetic' if demo else 'trusted', 'packages':entries}
    temporary = Path(tempfile.mkdtemp(prefix='.depot-build-', dir=output.parent))
    try:
        for source_path, data in assets:
            destination = temporary / source_path.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (temporary / 'catalog').mkdir()
        data = canonical(index)
        (temporary / 'catalog/index.json').write_bytes(data)
        os.rename(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return sha(data)


def load_catalog(root, pin=None, allow_synthetic=False):
    root = safe_directory(root)
    data = checked_file(root, 'catalog/index.json', 128*1024)
    if pin is not None:
        import re
        require(bool(re.fullmatch(r'[0-9a-f]{64}', pin)), 'SHA-256 catalog pin required')
        require(sha(data) == pin, 'catalog pin mismatch')
    value = document(data, 'catalog')
    require(isinstance(value, dict) and set(value) == {'schema','mode','packages'}, 'invalid catalog')
    require(value['schema'] == 'dots-depot-catalog/1' and value['mode'] in ('trusted','synthetic'), 'unsupported catalog')
    require(value['mode'] == 'trusted' or allow_synthetic, 'demo catalog requires explicit --demo')
    require(isinstance(value['packages'],list) and len(value['packages']) <= 256, 'catalog size limit')
    seen = set()
    for entry in value['packages']:
        require(isinstance(entry, dict) and set(entry)=={'id','version','name','type','summary','tree_sha256','manifest_sha256','audit_sha256','archive_sha256','synthetic'}, 'invalid catalog entry')
        paths = release_paths(root, entry['id'], entry['version'])
        key = (entry['id'],entry['version'])
        require(key not in seen, 'duplicate catalog release')
        seen.add(key)
        require(type(entry['synthetic']) is bool and entry['synthetic'] == (value['mode']=='synthetic'), 'catalog trust-mode mismatch')
        # Do not follow package/audit URLs from metadata. Layout is fixed.
        mdata, adata = [checked_file(root, str(p.relative_to(root)),128*1024) for p in paths[:2]]
        manifest, audit = bind(mdata, adata, allow_synthetic)
        require(audit['audit']['status'] == ('synthetic' if value['mode']=='synthetic' else 'approved'), 'catalog audit trust-mode mismatch')
        for key in ('id','version','name','type','summary','tree_sha256'):
            require(entry[key] == manifest[key], 'catalog manifest mismatch')
        require(entry['manifest_sha256']==sha(mdata) and entry['audit_sha256']==sha(adata), 'catalog document digest mismatch')
        import re
        require(isinstance(entry['archive_sha256'],str) and bool(re.fullmatch(r'[0-9a-f]{64}',entry['archive_sha256'])), 'invalid archive digest')
    return value, sha(data)


def release(root, package, version, pin, demo=False):
    index, fingerprint = load_catalog(root, pin, demo)
    matches = [e for e in index['packages'] if e['id']==package and (version is None or e['version']==version)]
    require(len(matches)==1, 'select an exact published version; unaudited/new releases fail closed')
    entry = matches[0]
    paths = release_paths(Path(root),entry['id'],entry['version'])
    mdata, adata, archive = [checked_file(Path(root),str(p.relative_to(root)),limit) for p,limit in zip(paths,(128*1024,128*1024,10*1024*1024))]
    manifest,audit = bind(mdata,adata,demo)
    require(sha(archive)==entry['archive_sha256'], 'archive digest mismatch')
    entries = unpack(archive)
    require(tree_digest(entries)==manifest['tree_sha256'], 'package tree digest mismatch')
    require([n for n,m,_ in entries if m==0o755]==sorted(manifest['executables']), 'undeclared executable')
    return manifest,audit,entries,entry,fingerprint

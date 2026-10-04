"""Original Depot implementation. Package content is always inert data."""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import tarfile
import time

SCHEMAS = Path(__file__).resolve().parents[1] / 'schemas'
MAX_JSON = 128 * 1024
MAX_FILES = 256
MAX_FILE = 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_ARCHIVE = 10 * 1024 * 1024

class DepotError(ValueError):
    """Fail-closed user-facing error."""


def require(condition, message):
    if not condition:
        raise DepotError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode() + b'\n'


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load_json(data):
    require(len(data) <= MAX_JSON, 'JSON byte limit exceeded')
    def finite(_):
        raise DepotError('non-finite JSON number')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=no_duplicates, parse_constant=finite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DepotError('invalid UTF-8 JSON') from exc
    def bounded(v, depth=0):
        require(depth <= 12, 'JSON depth limit exceeded')
        if isinstance(v, float):
            require(math.isfinite(v), 'non-finite JSON number')
        if isinstance(v, dict):
            for item in v.values():
                bounded(item, depth + 1)
        elif isinstance(v, list):
            for item in v:
                bounded(item, depth + 1)
    bounded(value)
    return value


def regular_bytes(path, limit=MAX_JSON):
    path = Path(path)
    require(not path.is_symlink(), 'symlink file rejected')
    # O_NOFOLLOW closes the last-component lstat/open race on supported hosts.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            st = os.fstat(stream.fileno())
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'regular, non-hardlinked file required')
            require(st.st_size <= limit, 'file byte limit exceeded')
            data = stream.read(limit + 1)
            require(len(data) <= limit, 'file byte limit exceeded')
            return data
    except OSError as exc:
        raise DepotError('cannot read regular file') from exc


def safe_directory(path, create=False):
    path = Path(os.path.abspath(path))
    # macOS ships these root-owned aliases. Normalize only these known system
    # aliases; all user-controlled symlink components still fail closed.
    if __import__('sys').platform == 'darwin' and len(path.parts) > 1 and path.parts[1] in ('var', 'tmp'):
        alias = Path('/') / path.parts[1]
        canonical_root = Path('/private') / path.parts[1]
        require(alias.resolve() == canonical_root, 'unexpected system directory alias')
        path = canonical_root.joinpath(*path.parts[2:])
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise DepotError('symlink directory rejected')
        if not current.exists() and create:
            current.mkdir(mode=0o700)
        require(current.is_dir(), 'directory missing or unsafe')
    return path


def path_label(value):
    require(isinstance(value, str) and len(value) <= 240, 'invalid path')
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', value)), 'unsafe path characters')
    parts = value.split('/')
    require(all(p not in ('.', '..') and p.casefold() not in ('.git', '.depot') for p in parts), 'reserved/traversal path')
    return value


def validate(value, schema, label='$'):
    """Enforce the complete keyword subset used by our shipped closed schemas.

    This is not a general JSON Schema engine. Schema files are trusted local code;
    no remote references or attacker-provided schemas are evaluated.
    """
    if 'const' in schema:
        require(type(value) is type(schema['const']) and value == schema['const'], label + ': wrong constant')
    if 'enum' in schema:
        require(value in schema['enum'], label + ': unsupported value')
    kind = schema.get('type')
    if kind == 'object':
        require(isinstance(value, dict), label + ': object required')
        require(set(value) == set(schema['properties']), label + ': missing or unknown fields')
        for key, spec in schema['properties'].items():
            validate(value[key], spec, label + '.' + key)
    elif kind == 'array':
        require(isinstance(value, list), label + ': array required')
        require(len(value) <= schema['maxItems'], label + ': too many items')
        require(len({canonical(item) for item in value}) == len(value), label + ': duplicate items')
        for item in value:
            validate(item, schema['items'], label + '[]')
    elif kind == 'string':
        require(isinstance(value, str), label + ': string required')
        require(schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 1000), label + ': string length')
        require(not any(ord(c) < 32 or ord(c) == 127 for c in value), label + ': control characters')
        if 'pattern' in schema:
            require(bool(re.fullmatch(schema['pattern'], value)), label + ': invalid format')
        if schema.get('format') == 'date-time':
            require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value)), label + ': UTC date-time required')
            try:
                dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
            except ValueError as exc:
                raise DepotError(label + ': invalid date-time') from exc
    elif kind == 'integer':
        require(type(value) is int and schema['minimum'] <= value <= schema['maximum'], label + ': integer range')
    elif kind == 'boolean':
        require(type(value) is bool, label + ': boolean required')


def document(data, kind):
    value = load_json(data)
    validate(value, load_json(regular_bytes(SCHEMAS / (kind + '.schema.json'))))
    if kind in ('package', 'audit', 'tests'):
        path_label(value['source']['path'])
    if kind == 'package':
        require(value['audit'] == f"audits/{value['id']}/{value['version']}.json", 'audit path must bind exact release')
        for name in value['executables']:
            path_label(name)
    if kind in ('package', 'audit'):
        requests = value['requests'] if kind == 'package' else value['permissions']
        for field in ('workspace_read', 'workspace_write'):
            for pattern in requests[field]:
                # Only a final /** is supported; never an absolute/parent path.
                path_label(pattern[:-3] if pattern.endswith('/**') else pattern)
    if kind == 'audit':
        verification = value['verification']
        require((verification['tests_status'] == 'not-run' and verification['tests_passed'] == 0 and verification['tests_sha256'] == 'not-run') or
                (verification['tests_status'] == 'human-reviewed-ci' and verification['tests_passed'] > 0 and verification['tests_sha256'] != 'not-run'), 'inconsistent test evidence claim')
    return value


def bind(manifest_data, audit_data, allow_synthetic=False):
    manifest = document(manifest_data, 'package')
    audit = document(audit_data, 'audit')
    require(audit['package'] == manifest['id'] and audit['version'] == manifest['version'], 'audit release mismatch')
    require(audit['source'] == manifest['source'] and audit['tree_sha256'] == manifest['tree_sha256'], 'audit source mismatch')
    require(audit['manifest_sha256'] == sha(manifest_data), 'audit manifest hash mismatch')
    require(audit['permissions'] == manifest['requests'], 'audit permissions mismatch')
    require(audit['audit']['status'] == 'approved' or allow_synthetic, 'synthetic release requires explicit demo mode')
    require(audit['verification']['static_scan'] == 'pass', 'static review not complete')
    return manifest, audit


def entries_checked(entries):
    require(0 < len(entries) <= MAX_FILES, 'file count limit or empty package')
    folded = set()
    total = 0
    paths = set()
    for name, mode, data in entries:
        path_label(name)
        require(name.casefold() not in folded, 'duplicate/case-colliding file')
        folded.add(name.casefold())
        require(mode in (0o644, 0o755), 'unsupported file mode')
        require(len(data) <= MAX_FILE, 'per-file size limit')
        total += len(data)
        require(total <= MAX_TOTAL, 'tree size limit')
        paths.add(name)
    for name in paths:
        require(all('/'.join(name.split('/')[:i]) not in paths for i in range(1, len(name.split('/')))), 'file/directory collision')
    # Case collisions in ancestor directories matter on macOS too.
    ancestors = {}
    for name in paths:
        parts = name.split('/')
        for i in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:i])
            require(ancestors.setdefault(prefix.casefold(), prefix) == prefix, 'case-colliding directory')
    return sorted(entries, key=lambda item: item[0].encode('ascii'))


def tree_digest(entries):
    entries = entries_checked(entries)
    # Length-prefix every name and file; normalize modes; include empty files.
    digest = hashlib.sha256(b'dots-depot-tree/1\0')
    for name, mode, data in entries:
        encoded = name.encode('ascii')
        digest.update(len(encoded).to_bytes(4, 'big') + encoded)
        digest.update(mode.to_bytes(4, 'big') + len(data).to_bytes(8, 'big') + data)
    return digest.hexdigest()


def archive_bytes(entries):
    stream = io.BytesIO()
    try:
        with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name, mode, data in entries_checked(entries):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode, entry.mtime = len(data), mode, 0
                archive.addfile(entry, io.BytesIO(data))
    except (ValueError, tarfile.TarError) as exc:
        raise DepotError('path not representable in canonical USTAR') from exc
    result = stream.getvalue()
    require(len(result) <= MAX_ARCHIVE, 'archive limit')
    return result


def unpack(data):
    require(len(data) <= MAX_ARCHIVE, 'archive byte limit exceeded')
    require(len(data) % 512 == 0, 'truncated archive')
    entries = []
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
            for entry in archive:
                require(entry.isfile() and not entry.pax_headers and entry.type == tarfile.REGTYPE, 'only plain regular tar files allowed')
                require(entry.mode in (0o644, 0o755), 'unsafe archive mode')
                require(entry.size <= MAX_FILE and entry.size >= 0, 'archive member size limit')
                require(len(entries) < MAX_FILES, 'archive file count limit')
                require(sum(len(item[2]) for item in entries) + entry.size <= MAX_TOTAL, 'archive expanded size limit')
                path_label(entry.name)
                stream = archive.extractfile(entry)
                require(stream is not None, 'missing archive bytes')
                payload = stream.read(MAX_FILE + 1)
                require(len(payload) == entry.size, 'truncated member')
                entries.append((entry.name, entry.mode, payload))
    except (tarfile.TarError, OSError) as exc:
        raise DepotError('invalid plain tar archive') from exc
    checked = entries_checked(entries)
    # Reject concatenation, ignored tails and alternate headers. Artifacts use
    # one deterministic USTAR encoding, so ambiguous archives cannot pass.
    require(data == archive_bytes(checked), 'noncanonical archive or trailing content')
    return checked


def git(repo, *args):
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')
    limit = MAX_FILE if args[:2] == ('cat-file', 'blob') else MAX_JSON
    try:
        with subprocess.Popen(['git', '--no-replace-objects', '-C', str(repo), '-c', 'core.hooksPath=' + os.devnull, *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env) as process:
            output = bytearray()
            deadline = time.monotonic() + 20
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        require(remaining > 0, 'local Git inspection deadline exceeded')
                        require(bool(selector.select(remaining)), 'local Git inspection deadline exceeded')
                        chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(output)))
                        if not chunk:
                            selector.unregister(process.stdout)
                            break
                        output.extend(chunk)
                        require(len(output) <= limit, 'local Git output byte limit exceeded')
                require(process.wait(timeout=max(.01, deadline-time.monotonic())) == 0, 'local immutable Git inspection failed')
            except BaseException:
                process.kill()
                process.wait()
                raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise DepotError('local immutable Git inspection failed') from exc
    return bytes(output)


def inspect_git(repo, source):
    repo = safe_directory(repo)
    path_label(source['path'])
    commit = git(repo, 'rev-parse', '--verify', source['commit'] + '^{commit}').decode().strip()
    require(commit == source['commit'], 'exact commit object required')
    subtree = git(repo, 'rev-parse', '--verify', commit + ':' + source['path']).decode().strip()
    require(subtree == source['subtree'], 'Git subtree hash mismatch')
    require(git(repo, 'cat-file', '-t', subtree).strip() == b'tree', 'source path must be a Git tree')
    records = git(repo, 'ls-tree', '-r', '-z', subtree).split(b'\0')
    entries = []
    for record in records:
        if not record:
            continue
        header, raw_name = record.split(b'\t', 1)
        mode, kind, blob = header.split(b' ')
        require(kind == b'blob' and mode in (b'100644', b'100755'), 'symlink, gitlink or special source rejected')
        require(len(entries) < MAX_FILES, 'source file count limit')
        size = int(git(repo, 'cat-file', '-s', blob.decode()).strip())
        require(size <= MAX_FILE, 'source file size limit')
        try:
            name = raw_name.decode('ascii')
        except UnicodeError as exc:
            raise DepotError('nonportable source path') from exc
        data = git(repo, 'cat-file', 'blob', blob.decode())
        entries.append((name, 0o755 if mode == b'100755' else 0o644, data))
        require(sum(len(item[2]) for item in entries) <= MAX_TOTAL, 'source tree size limit')
    return entries_checked(entries)

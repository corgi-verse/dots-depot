# Dots Depot 0.1 — The Warehouse

**Parts for your System.** An original Apache-2.0 static catalog and local Python client for inspecting exact releases of apps, skills, recipes, tools and starters. Discovery and metadata grant no execution authority.

The trusted catalog contains **zero approved releases**. Depot provides inert discovery and staging; it does not install, activate, or execute packages. The optional demo build uses two original synthetic fixtures, with no human-audited badge or claim that package tests ran. Real Paste Inbox remains unapproved; its restricted source is excluded from this repository.

## Run locally

Requirements: Python >=3.12, Git and a modern browser. Node >=22 runs web regression tests. Runtime uses only the Python standard library; no credentials, accounts, paid services or downloaded packages are needed.

A clean checkout includes `site/`, containing the original web assets, schemas and empty trusted catalog. Preview it:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8765`; stop with Ctrl-C. Serve **only generated static output**, never a repository/workspace with private approvals, review packets or receipts. Publishing this source repository does not deploy a site.

To build an optional synthetic demonstration, choose new output directories:

```sh
python3 scripts/make_demo.py build/demo
python3 scripts/build_site.py site-demo
python3 -m http.server 8765 --bind 127.0.0.1 --directory site-demo
```

Without `build/demo`, `build_site.py` emits only an empty trusted catalog. Outputs cannot already exist. Demo navigation is hidden in the trusted-only site and enabled only in outputs containing validated local fixtures. A demo URL on the trusted-only site returns to its trusted catalog. Synthetic records are separate and can never enter the trusted catalog.

## Search, inspect, stage and verify

```sh
python3 -m depot search
python3 -m depot --root site-demo/demo --demo search inert
python3 -m depot --root site-demo/demo --demo info fixture.inert-tool --version 0.1.0
```

Stage and verify require an exact version and a catalog SHA-256 fingerprint obtained independently from the trusted maintainer. Metadata, a peer audit, an approval claim, or a fingerprint displayed by a downloaded page cannot grant trust. For a synthetic exercise you generated yourself, inspect and hash the local `site-demo/demo/catalog/index.json`; regenerate timestamped audit records only when you intend to change its pin.

```sh
python3 -m depot --root site-demo/demo --demo \
  --catalog-sha256 <independently-trusted-demo-fingerprint> \
  stage fixture.inert-tool --version 0.1.0 --destination .depot/staging
python3 -m depot --root site-demo/demo --demo \
  --catalog-sha256 <same-fingerprint> \
  verify .depot/staging/fixture.inert-tool@0.1.0
```

Private staging contains `content/` and a mode-0600 receipt binding catalog, manifest, audit, tree, commit and subtree. Source execute bits are stripped; files become 0600. No package imports, hooks, tests, builds or commands run. Source addition, installation and activation are future work.

Repeating stage fails rather than overwriting. Changed bytes, missing/extra files, symlinks, hardlinks, executable permissions or modified receipts fail verification. Verify requires the independently trusted pin again; a receipt cannot authorize itself.

## Maintainer pipeline

Submissions never enter the catalog by discovery alone. Acquire a local Git repository independently and use a closed-schema manifest pinning full commit, source path, Git subtree and canonical tree SHA-256. The public repository URL is declarative: immutable local Git bytes do not prove remote ownership. A human independently establishes provenance, licensing and permission scope.

```sh
python3 scripts/inspect_submission.py --repository /absolute/local/source \
  --manifest /absolute/submission.json --output .review/exact-release
python3 scripts/publish_package.py token --packet .review/exact-release
```

Preflight reads raw Git objects, never working-tree code, hooks or archive filters. It enumerates modes/hashes/declarations and creates an inert canonical archive/report. It runs no submitted tests. Binary source and unresolved static findings are unsupported for release in 0.1. The lexical scanner is conservative: documentation URLs also require resolution. Do not edit its report to fabricate a pass. Untrusted tests need separately authorized ephemeral, no-secrets CI.

**Only a trusted human maintainer may approve a real release.** The token binds id/version, manifest, tree, commit, subtree, report, archive and optional CI evidence. These commands describe a future actual human-approved release; none were used to approve a real package for this source publication:

```sh
python3 scripts/publish_package.py approve --packet .review/exact-release \
  --mirror releases --approvals .approvals --auditor 'actual human maintainer' \
  --confirmation '<exact token reviewed and approved by the human>'
python3 scripts/build_catalog.py --mirror releases --approvals .approvals \
  --output public-catalog
python3 scripts/build_site.py site-approved --mirror releases --approvals .approvals
```

Scripts write locally; they do not publish remotely. Keep the owner-controlled approval store distinct from submissions. Never import submitter approvals. Releases cannot be overwritten; approval is written last, so incomplete records cannot enter the catalog. Versions inherit no approvals.

Nonzero package test counts require `--test-evidence /path/ci.json --tests-passed N` and the same evidence when generating the token. The strict CI schema binds exact source/tree, counts, runner and timestamp; its hash enters the audit. This is human-reviewed evidence, not cryptographic attestation. Without evidence, count is zero and status says tests not run. `--synthetic` and `--demo` are explicit fixture modes, with matching audit/approval kinds.

## Contracts and limits

- Closed schemas for package, audit, catalog, approval, receipt and CI evidence. Unknown fields/versions, duplicate keys, BOM, numeric overflow/nonfinite values, invalid dates and JSON bounds fail closed. Validators cover the subset used in shipped schemas; they do not fetch schema references.
- Immutable Git commit/subtree and canonical SHA-256 over sorted ASCII paths, source modes, lengths and every byte. Framing: `dots-depot-tree/1` plus NUL; per file, 4-byte big-endian path length, path, 4-byte mode, 8-byte body length and body.
- Canonical plain USTAR only. No extraction API. Reject symlinks, hardlinks, gitlinks, devices/FIFOs, directories, PAX, compression, trailing/concatenated archives, traversal, reserved paths and collisions. ASCII paths exclude dot/parent and `.git`/`.depot` segments.
- Bounds: 128 KiB JSON, nesting depth 12, 256 files, 1 MiB per file, 8 MiB tree, 10 MiB archive. Browser enforces streaming limits.
- Private owner-controlled trust/staging paths. Known root-owned Mac `/tmp` and `/var` aliases normalize; other symlinks fail. This is not an OS sandbox against a hostile process running as the same user.
- Static views use text nodes, pinned document hashes, closed schemas, CSP and no external requests/telemetry. Browser discovery is separate from local authority.
- No remote fetching, payment, accounts, credentials, auto-update, installation, activation or automatic package execution.

## Verify

```sh
python3 -m unittest discover -s tests -v
node --test tests/web.test.cjs
node --check apps/web/depot.js
python3 scripts/check_schemas.py  # optional checker; requires jsonschema
```

Tests cover strict schemas, approvals/report integrity, malicious archives/source paths, receipts, byte/mode tampering, CLI integration, synthetic separation and public-output privacy. CI executes only original Depot code and synthetic fixtures on Python 3.12/3.13 with a read-only token and no deployment. See `EVIDENCE.md`, `SECURITY.md`, `BLUEPRINT.md`, `LICENSE-REVIEW.md` and `PUBLICATION-MANIFEST.json` for verified scope and limits.

# Dots Depot 0.1 — The Warehouse

Scope: original Apache-2.0 application in this directory only. No execution of third-party packages. The public output is a static allowlist-generated site; the client uses a user-supplied local mirror and an independently trusted SHA-256 catalog pin. Source publication is separate from deployment or package approval. Client remote fetching, activation and updates are outside 0.1.

Build: strict declarative package/audit/approval/receipt schemas and a bounded standard-library validator; raw immutable Git blob inspection into deterministic tar artifacts; canonical file tree digests; separate maintainer-owned exact release approvals; catalog generator; read-only catalog/detail/audit views; Python search/info/stage/verify client with private staging receipts. Demo catalog is separate and explicitly synthetic. No real Paste Inbox badge or fabricated approval.

Protected invariants: unknown fields/schema versions fail closed; approval binds manifest, permissions, commit, subtree and tree digest; new versions inherit nothing; no hooks/scripts/builds/imports from packages; reject traversal, symlinks, hardlinks, devices, duplicate/case-colliding entries, limits and schema ambiguity; verify every staged byte and reject extra files; receipts never enter static output.

Checks: malformed/schema/approval/catalog privacy cases; malicious archive and source tree cases; hash/mode/extra-file/receipt tampering; CLI integration; deterministic generation; clean CI; desktop/mobile navigation, search, filters, empty/error states and accessible controls. Python 3.12 execution and independent review are reported according to actual availability.

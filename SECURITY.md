# Security and authority

Metadata is untrusted data and grants no authority. Keep the local mirror pin and maintainer approval store trusted independently of submissions. A valid schema, claimed auditor name, passed static scan, public badge or staging receipt is not permission to run anything.

The client executes only original Depot code and read-only system Git operations. It never imports or executes package files. Staging strips execute bits. Canonical archive/tree/receipt verification is mandatory. No install/add/activate command is included.

Serve only generated `site/`; keep approvals, review packets, staged files and receipts private. The catalog generator copies explicit approved release files, not repository trees or submissions. Do not use an arbitrary submitted directory as your approval store.

This candidate is a local standard-library tool, not a hardened same-user concurrency sandbox. Do not allow hostile processes to modify its private working paths while it runs. No guarantee of safety or CI authenticity is made. A human reviews provenance, licensing, declarations and independently obtained test evidence for the exact release.

Report suspected defects privately to the actual project maintainer through an existing trusted channel. No fabricated security inbox or automatic disclosure is configured.

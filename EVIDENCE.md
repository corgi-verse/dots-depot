# Depot 0.1 release verification

Original Apache-2.0 Depot application source and static output. **No package approval or site deployment.** The committed trusted catalog is empty; real Paste Inbox and its restricted source are excluded. Optional demo generation uses original synthetic fixtures only.

| Check | Result | Evidence / limit |
|---|---|---|
| Mac Python 3.12 runtime | PASS | Python 3.12.15 built from official Python.org source, SHA-256 `c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a`; configure/make/altinstall into a separate local prefix. Existing Python 3.13.7 and shell defaults retained. |
| Python security/CLI contracts | PASS | 50 tests, zero skipped, on Python 3.12.15. Original source/path/archive/symlink/schema/approval/report/receipt/CLI/privacy tests; no submitted code executed. Earlier 3.13.7 run also passed. |
| Browser data contracts | PASS | Six Node tests, zero skipped, Node 22.19.0; strict schema/parser, bounded streaming, digest/mode checks. JavaScript syntax passes. |
| Clean empty static build | PASS | Original `build_site.py` creates public assets/schemas and trusted catalog with zero entries. Optional synthetic pipeline is checked separately and never changes trusted status. |
| Immutable source boundaries | PASS within tested scope | Full Git commit/subtree, canonical file tree hash/archive, exact maintainer authority bindings, no inherited approval, private inert staging and receipt verification. |
| Prior desktop/mobile acceptance | PASS within observed scope | Same original web implementation checked at 1280×900 and 390×844: navigation/search/filter/empty/retry/detail/audit/copy/keyboard skip-link, no measured horizontal overflow or normal-flow console errors. Synthetic test data only. |
| License boundary | PASS | Complete Apache-2.0 license for original implementation and fixtures; restricted Dotsys source excluded. Independently installed Python/Git/browser are not redistributed. |
| Public source scope | PASS | Explicit allowlist and per-file publication manifest; no private reviews, approval stores, staged files/receipts, runtime builds, credentials or unrelated projects. |
| Independent review | Recorded before publication | Separate read-only reviewer checks the exact public candidate and release scope; any blockers are resolved before upload. This is not a security certification. |
| GitHub CI | Live result external to this snapshot | Workflow runs the original tests/build on Python 3.12/3.13, read-only token, no persisted Git credentials, secrets, package execution or deployment. Check the run for the exact commit in GitHub Actions rather than infer success from this document. |
| Real package/host acceptance | NOT_RUN | No real Paste Inbox approval, package execution, native installation/activation or host integration claimed. |

Local Python's optional `_gdbm`, `_lzma` and `_tkinter` modules were not built; Depot does not need them and its complete suite passes. OpenSSL support is present (OpenSSL 3.6.4). No additional runtime packages were installed.

Limits: private directories must be owner-controlled. This is not atomic defense against hostile same-user concurrent path replacement. Git hashes verify inspected bytes, not remote ownership. Human-reviewed CI evidence is not cryptographic attestation. No automatic publication, paid services or wider project changes are implied.

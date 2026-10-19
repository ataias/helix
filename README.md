# helix master, vendored

Builds of [helix](https://github.com/helix-editor/helix) master, published as
[packslip](https://packslip.dev)-signed releases you can install with mise.

Everything the build needs is committed under `vendor/`, so building needs no
network access once the Rust toolchain is installed:

| Path | Contents |
|---|---|
| `vendor/helix/` | helix source at the commit in `helix.toml` |
| `vendor/cargo/` | `cargo vendor` output for helix's `Cargo.lock` (used via `.cargo/config.toml`) |
| `vendor/grammars/` | tree-sitter grammar sources at the revs pinned in helix's `languages.toml`, trimmed to the files the build reads plus licenses |
| `vendor/grammars.toml` | the source (git, rev, subpath) each vendored grammar came from |
| `helix.toml` | the vendored commit, the release version derived from it, and the `Cargo.lock` hash the crates were vendored from |

## Install

```toml
# mise.toml
[tools]
"packslip:github.com/OWNER/REPO" = "25.7.1-master.20260929023219.gba40e54742"
```

Versions are `<helix version>-master.<commit time, UTC>.g<commit>`, so they are
semver prereleases ordered by commit time. Pin exact versions as above. Pinned
versions also skip mise's `minimum_release_age` wait. To track the newest
version instead, use `{ version = "latest", prerelease = true }`.

`hx` finds `runtime/` (queries, themes, compiled grammars) next to the
executable, so `HELIX_RUNTIME` doesn't need to be set.

## Update helix

```sh
mise run bump            # or: mise run bump <branch|tag|commit>
mise run setup           # install the toolchain pinned by helix (network)
mise run build:offline   # optional: check it builds with networking disabled
git add vendor .cargo helix.toml && git commit -m "helix: bump" && git push
```

`bump` only fetches what changed. If the ref still points at the vendored
commit, it stops after one `git ls-remote`. Otherwise it reruns `cargo vendor`
only when the set of crates in `Cargo.lock` changed. It refetches only the
grammars whose entry in `vendor/grammars.toml` changed, and deletes grammars
helix dropped. It prints which crates and grammars changed, and the commit diff
shows the same through `helix.toml`, `vendor/grammars.toml` and
`vendor/helix/Cargo.lock`. Pass `--force` to `scripts/vendor.py` to refetch
everything. A full refetch reproduces `vendor/` byte-for-byte.

A push to `main` that changes `helix.toml` runs `.github/workflows/release.yml`.
That workflow builds `x86_64`/`aarch64` Linux and `aarch64` macOS with
networking disabled (bubblewrap on Linux, `sandbox-exec` on macOS). It then
creates the `v<version>` release and signs it with packslip.

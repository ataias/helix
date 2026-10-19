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
| `helix.toml` | the vendored commit, the release version assigned to it, and the `Cargo.lock` hash the crates were vendored from |

## Install

```toml
# mise.toml
[tools]
"packslip:ataias/helix" = "latest" # or pin one, e.g. "26.10.1"
```

Versions are `YY.M.N`. `mise run bump` assigns the next one when helix moves
to a new commit: `26.10.1` is the first build in October 2026, `26.10.2` the
second, and so on. `hx --version` still reports helix's own version and commit,
e.g. `25.07.1 (ba40e547)`. mise only offers releases older than its
`minimum_release_age` (24h by default) for `latest`; a pinned version installs
right away.

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

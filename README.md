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
| `helix.toml` | the vendored commit and the release version derived from it |

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

A push to `main` that changes `helix.toml` runs `.github/workflows/release.yml`.
That workflow builds `x86_64`/`aarch64` Linux and `aarch64` macOS with
networking disabled (bubblewrap on Linux, `sandbox-exec` on macOS). It then
creates the `v<version>` release and signs it with packslip.

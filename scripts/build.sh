#!/usr/bin/env bash
# Build helix from vendor/ and package it as dist/helix-<version>-<target>.tar.xz.
#
# Needs no network access: crates come from vendor/cargo (see .cargo/config.toml)
# and grammar sources from vendor/grammars. The Rust toolchain pinned in
# vendor/helix/rust-toolchain.toml must already be installed (`mise run setup`).
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

version=$(sed -n 's/^version = "\(.*\)"$/\1/p' helix.toml)
commit=$(sed -n 's/^commit = "\(.*\)"$/\1/p' helix.toml)
target=$(cd vendor/helix && rustc -vV | sed -n 's/^host: //p')
name="helix-$version-$target"
pkg="$root/dist/$name"

# Don't hand credentials (e.g. GH_TOKEN from a local .env) to crate build scripts.
unset GH_TOKEN GITHUB_TOKEN

export CARGO_TARGET_DIR="$root/target"
# helix-term's build.rs would git clone every grammar; we build them below instead.
export HELIX_DISABLE_AUTO_GRAMMAR_BUILD=1
# helix puts $CARGO_MANIFEST_DIR/../runtime first in its runtime search path.
unset CARGO_MANIFEST_DIR
# helix-loader's build.rs takes the hash for `hx --version` from `git rev-parse
# HEAD`, which would find this repo; hide it so it falls back to this variable.
export HELIX_NIX_BUILD_REV="$commit" GIT_DIR=/nonexistent

echo "==> cargo build ($target)"
# Run from vendor/helix so rustup picks up its rust-toolchain.toml.
(cd vendor/helix && cargo build --frozen --release --package helix-term)

echo "==> package $name"
rm -rf "$pkg" "$pkg.tar.xz"
mkdir -p "$pkg"
cp "$CARGO_TARGET_DIR/release/hx" "$pkg/hx"
cp -R vendor/helix/runtime "$pkg/runtime"
# helix's .gitignore drops runtime/grammars/.gitkeep, so the dir may not exist.
rm -f "$pkg/runtime/grammars/.gitkeep"
mkdir -p "$pkg/runtime/grammars"

echo "==> tree-sitter grammars"
# `hx --grammar build` reads sources from, and writes libraries to, the first
# runtime dir: $XDG_CONFIG_HOME/helix/runtime. Point that at the package.
config=$(mktemp -d)
trap 'rm -rf "$config"' EXIT
mkdir -p "$config/helix"
ln -s "$pkg/runtime" "$config/helix/runtime"
cp -R vendor/grammars "$pkg/runtime/grammars/sources"
XDG_CONFIG_HOME="$config" "$pkg/hx" --grammar build
rm -rf "$pkg/runtime/grammars/sources"

# The executable finds runtime/ next to itself, so no wrapper or HELIX_RUNTIME is needed.
"$pkg/hx" --version
tar -C dist -cJf "$pkg.tar.xz" "$name"
echo "==> dist/$name.tar.xz"

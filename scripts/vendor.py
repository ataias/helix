#!/usr/bin/env python3
"""Vendor helix at a given commit together with everything its build downloads.

Populates:
  vendor/helix/          helix source tree at the requested commit (no .git)
  vendor/cargo/          `cargo vendor` output for helix's Cargo.lock
  vendor/grammars/       tree-sitter grammar sources at the revs pinned in languages.toml
  vendor/grammars.toml   the source each vendored grammar was fetched from
  helix.toml             what was vendored, and the packslip version derived from it

Only what changed is fetched again: helix is skipped when the requested ref still
points at the vendored commit, crates when Cargo.lock is unchanged, and each
grammar when its source (git, rev, subpath) is unchanged. State is written last,
so an interrupted run redoes whatever it did not finish.

After this, `scripts/build.sh` needs no network access.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
STATE = ROOT / "helix.toml"
GRAMMAR_LOCK = VENDOR / "grammars.toml"
HELIX_REPO = "https://github.com/helix-editor/helix"

INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.M)
LICENSE_RE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE)", re.I)


def run(*cmd, cwd=None, capture=False):
    result = subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


# Fetch grammars independently of the user's git config (url rewrites, object format, ...).
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(*args, cwd):
    result = subprocess.run(("git", *args), cwd=cwd, env=GIT_ENV, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def shallow_fetch(url, rev, dest, attempts=4):
    """Fetch a single commit into a fresh repo at dest and check it out."""
    for attempt in range(1, attempts + 1):
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        try:
            git("init", "-q", "--object-format=sha1", cwd=dest)
            git("fetch", "-q", "--depth", "1", url, rev, cwd=dest)
            git("-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD", cwd=dest)
            return
        except RuntimeError:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def load_toml(path):
    return tomllib.loads(path.read_text()) if path.exists() else {}


def resolve(rev):
    """The commit a branch or tag points at, without fetching it; None if rev
    is not a ref (e.g. an abbreviated sha), in which case we must fetch."""
    if re.fullmatch(r"[0-9a-f]{40}", rev):
        return rev
    refs = dict(
        reversed(line.split("\t"))
        for line in git("ls-remote", HELIX_REPO, rev, cwd=ROOT).splitlines()
    )
    for ref in (f"refs/heads/{rev}", f"refs/tags/{rev}^{{}}", f"refs/tags/{rev}", rev):
        if ref in refs:
            return refs[ref]
    return None


def semver_part(n):
    return str(int(n))  # semver forbids leading zeros: 25.07.1 -> 25.7.1


def vendor_helix(rev, tmp):
    src = tmp / "helix"
    shallow_fetch(HELIX_REPO, rev, src)
    commit = git("rev-parse", "HEAD", cwd=src)
    committed = git("show", "-s", "--format=%ct", "HEAD", cwd=src)
    committed = datetime.datetime.fromtimestamp(int(committed), datetime.timezone.utc)

    dest = VENDOR / "helix"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    archive = subprocess.Popen(["git", "archive", "HEAD"], cwd=src, env=GIT_ENV, stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest), "-f", "-"], stdin=archive.stdout, check=True)
    if archive.wait() != 0:
        sys.exit("git archive failed")
    return commit, committed


def lock_packages(lock):
    """{name: {versions}} of the crates.io packages in a Cargo.lock's contents."""
    packages = {}
    for package in tomllib.loads(lock).get("package", []) if lock else []:
        if "source" in package:
            packages.setdefault(package["name"], set()).add(package["version"])
    return packages


def crate_changes(old_lock, new_lock):
    old, new = lock_packages(old_lock), lock_packages(new_lock)
    changes = []
    for name in sorted(old.keys() | new.keys()):
        before, after = sorted(old.get(name, ())), sorted(new.get(name, ()))
        if before != after:
            changes.append(f"{name} {', '.join(before) or '(new)'} -> {', '.join(after) or '(removed)'}")
    return changes


def vendor_cargo(tmp):
    dest = VENDOR / "cargo"
    shutil.rmtree(dest, ignore_errors=True)
    config = run(
        "cargo", "vendor", "--locked", "--versioned-dirs",
        "--manifest-path", str(VENDOR / "helix" / "Cargo.toml"),
        str(dest),
        cwd=tmp,  # don't pick up our own .cargo/config.toml, which points at dest
        capture=True,
    )
    # cargo prints the source replacement config with an absolute path; make it
    # relative to the repo root (cargo resolves it against the .cargo dir's parent).
    config = config.replace(str(dest), "vendor/cargo")
    header = "# Generated by `mise run bump`: build helix only from vendored crates.\n"
    (ROOT / ".cargo").mkdir(exist_ok=True)
    (ROOT / ".cargo" / "config.toml").write_text(header + config + "\n\n[net]\noffline = true\n")


def grammar_files(root, src):
    """Files the grammar build reads: src/ (minus JSON metadata), anything outside
    src/ that those files #include, and the license, as paths relative to root.
    Symlinks are kept at their own path (and copied as files), but never followed
    out of the grammar."""
    real_root, keep = root.resolve(), set()
    pending = [p for p in src.rglob("*") if p.is_file() and p.suffix != ".json"]
    pending += [p for p in root.iterdir() if p.is_file() and LICENSE_RE.match(p.name)]
    while pending:
        path = Path(os.path.normpath(pending.pop()))
        real = path.resolve()
        if path in keep or not real.is_file() or not real.is_relative_to(real_root):
            continue
        keep.add(path)
        if path.suffix in {".c", ".cc", ".cpp", ".h", ".hpp", ".inc"}:
            for include in INCLUDE_RE.findall(real.read_text(errors="replace")):
                pending.append(path.parent / include)
    return sorted(p.relative_to(root) for p in keep)


def vendor_grammars(tmp, jobs, force):
    """Fetch grammars whose source differs from the lock; returns (sources, report)."""
    languages = tomllib.loads((VENDOR / "helix" / "languages.toml").read_text())
    sources = {g["name"]: g["source"] for g in languages["grammar"]}
    for name, source in sources.items():
        if "git" not in source:
            sys.exit(f"grammar {name}: unsupported source {source}")
    locked = {} if force else load_toml(GRAMMAR_LOCK)
    dest = VENDOR / "grammars"
    dest.mkdir(parents=True, exist_ok=True)

    removed = sorted(p.name for p in dest.iterdir() if p.name not in sources)
    for name in removed:
        shutil.rmtree(dest / name)
    stale = sorted(n for n, s in sources.items() if locked.get(n) != s or not (dest / n).is_dir())

    def fetch(name):
        source = sources[name]
        work = tmp / "grammars" / name
        shallow_fetch(source["git"], source["rev"], work)
        src = work / source.get("subpath", "") / "src"
        if not (src / "parser.c").exists():
            raise RuntimeError(f"no parser.c in {src.relative_to(work)}")
        shutil.rmtree(dest / name, ignore_errors=True)
        for rel in grammar_files(work, src):
            (dest / name / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(work / rel, dest / name / rel)
        shutil.rmtree(work)

    failures = []
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        futures = {pool.submit(fetch, name): name for name in stale}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
                if sys.stdout.isatty():
                    print(f"\r    fetched {i}/{len(stale)}", end="", flush=True)
            except (RuntimeError, OSError) as e:
                failures.append(f"{futures[future]}: {e}")
    if sys.stdout.isatty() and stale:
        print()
    if failures:
        sys.exit("failed to vendor grammars:\n  " + "\n  ".join(sorted(failures)))

    added = [n for n in stale if n not in locked]
    updated = [n for n in stale if n in locked]
    return sources, {"added": added, "updated": updated, "removed": removed}


def write_grammar_lock(sources):
    lines = ["# Generated by `mise run bump`: the source each grammar in vendor/grammars came from.\n"]
    for name in sorted(sources):
        fields = ", ".join(f"{k} = {json.dumps(v)}" for k, v in sorted(sources[name].items()))
        lines.append(f"{json.dumps(name)} = {{ {fields} }}\n")
    GRAMMAR_LOCK.write_text("".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rev", nargs="?", default="master", help="helix branch, tag or commit (default: master)")
    parser.add_argument("--jobs", type=int, default=8, help="parallel grammar fetches")
    parser.add_argument("--force", action="store_true", help="refetch everything, even if unchanged")
    args = parser.parse_args()

    state = load_toml(STATE)
    complete = state.get("cargo_lock_sha256") and GRAMMAR_LOCK.exists()
    if not args.force and complete and resolve(args.rev) == state.get("commit"):
        print(f"==> helix {args.rev} is still {state['commit']}: nothing to do")
        return

    with tempfile.TemporaryDirectory(prefix="helix-vendor-") as tmp:
        tmp = Path(tmp)
        print(f"==> helix {args.rev}")
        old_lock = state.get("cargo_lock_sha256")
        old_lock_text = (VENDOR / "helix" / "Cargo.lock").read_text() if (VENDOR / "helix" / "Cargo.lock").exists() else None
        commit, committed = vendor_helix(args.rev, tmp)
        if commit == state.get("commit"):
            print(f"    still {commit}")
        else:
            print(f"    {state.get('commit', '(none)')} -> {commit}")

        lock = VENDOR / "helix" / "Cargo.lock"
        changes = crate_changes(old_lock_text, lock.read_text())
        # The old lock only counts as vendored if the last run finished with it.
        vendored = old_lock_text is not None and old_lock == hashlib.sha256(old_lock_text.encode()).hexdigest()
        if args.force or changes or not vendored or not (VENDOR / "cargo").is_dir():
            print(f"==> crates: {len(changes)} changed" + "".join(f"\n    {c}" for c in changes))
            vendor_cargo(tmp)
        else:
            print("==> crates: unchanged")

        sources, report = vendor_grammars(tmp, args.jobs, args.force)
        print("==> grammars: " + ", ".join(f"{len(v)} {k}" for k, v in report.items()))
        for kind, names in report.items():
            if names:
                more = f" (+{len(names) - 30} more)" if len(names) > 30 else ""
                print(f"    {kind}: {' '.join(names[:30])}{more}")

    helix = tomllib.loads((VENDOR / "helix" / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    base = ".".join(semver_part(n) for n in helix.split("."))
    # Prerelease of the upstream version, ordered by commit time; the short sha is
    # for humans (prefixed with "g" so it can never be a numeric identifier).
    version = f"{base}-master.{committed:%Y%m%d%H%M%S}.g{commit[:10]}"
    toolchain = load_toml(VENDOR / "helix" / "rust-toolchain.toml")["toolchain"]["channel"]

    # Written last: their absence/staleness is what makes the next run redo work.
    write_grammar_lock(sources)
    STATE.write_text(
        "# Generated by `mise run bump`. Pushing a change to this file to main publishes a release.\n"
        f'version = "{version}"\n'
        f'commit = "{commit}"\n'
        f'committed_at = "{committed:%Y-%m-%dT%H:%M:%SZ}"\n'
        f'cargo_version = "{helix}"\n'
        f'cargo_lock_sha256 = "{sha256(lock)}"\n'
        f'rust_toolchain = "{toolchain}"\n'
        f"grammars = {len(sources)}\n"
    )
    print(f"==> vendored helix {version}")


if __name__ == "__main__":
    main()

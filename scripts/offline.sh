#!/usr/bin/env bash
# Run a command with no network access, to prove the build is self-contained.
#   Linux: bubblewrap in a new user + network namespace (only loopback exists).
#   macOS: sandbox-exec with a profile denying all network operations.
set -euo pipefail

case "$(uname -s)" in
Linux)
	sandbox=(bwrap --unshare-user --unshare-net --dev-bind / / --proc /proc --)
	;;
Darwin)
	sandbox=(sandbox-exec -p '(version 1) (allow default) (deny network*)')
	;;
*)
	echo "offline: unsupported OS $(uname -s)" >&2
	exit 1
	;;
esac

# Prove the sandbox starts and blocks the network before trusting it: this
# succeeds only if it ran inside the sandbox and the request failed.
if ! "${sandbox[@]}" sh -c '! curl -sS -m 10 -o /dev/null https://github.com 2>/dev/null'; then
	echo "offline: could not start a sandbox without network access" >&2
	exit 1
fi
echo "offline: verified that github.com is unreachable inside the sandbox" >&2

exec "${sandbox[@]}" "$@"

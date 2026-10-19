#!/usr/bin/env bash
# Run a command with no network access, to prove the build is self-contained.
#   Linux: bubblewrap in a new user + network namespace (only loopback exists).
#   macOS: sandbox-exec with a profile denying all network operations.
set -euo pipefail

case "$(uname -s)" in
Linux)
	# Probe first: unprivileged user namespaces can be disabled (e.g. by
	# Ubuntu's AppArmor policy), and a silent fallback would defeat the point.
	if ! bwrap --unshare-user --unshare-net --dev-bind / / true 2>/dev/null; then
		echo "offline: bwrap cannot create a network namespace here" >&2
		exit 1
	fi
	exec bwrap --unshare-user --unshare-net --dev-bind / / --proc /proc -- "$@"
	;;
Darwin)
	exec sandbox-exec -p '(version 1) (allow default) (deny network*)' "$@"
	;;
*)
	echo "offline: unsupported OS $(uname -s)" >&2
	exit 1
	;;
esac

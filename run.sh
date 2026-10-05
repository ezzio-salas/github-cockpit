#!/bin/bash
# Runs GitHub Cockpit from this checkout, without installing it.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

# gtk4-layer-shell has to be loaded before libwayland, which a plain import cannot
# guarantee; without this the card silently falls back to an ordinary window.
# `awk` reads to the end rather than exiting at the first match, because exiting early
# would kill `ldconfig` with SIGPIPE and `pipefail` would take that for a real failure.
layer_shell=$(ldconfig -p 2>/dev/null | awk '!found && /libgtk4-layer-shell\.so/ { print $NF; found = 1 }')
if [ -n "$layer_shell" ]; then
    export LD_PRELOAD="$layer_shell${LD_PRELOAD:+:$LD_PRELOAD}"
fi

exec python3 -m github_cockpit "$@"

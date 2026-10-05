#!/bin/bash
# Runs GitHub Cockpit from this checkout, without installing it.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
# gtk4-layer-shell has to be loaded before GTK is, which a plain import cannot guarantee.
layer_shell=$(ldconfig -p 2>/dev/null | awk '/libgtk4-layer-shell\.so/ {print $NF; exit}')
if [ -n "$layer_shell" ]; then
    export LD_PRELOAD="$layer_shell${LD_PRELOAD:+:$LD_PRELOAD}"
fi
exec python3 -m github_cockpit "$@"

#!/bin/bash
# Builds GitHubCockpit.app next to this script.
set -euo pipefail
cd "$(dirname "$0")"

app="GitHubCockpit.app"

swift build -c release

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp .build/release/GitHubCockpit "$app/Contents/MacOS/"
cp Info.plist "$app/Contents/"
cp ../resources/Orbitron.ttf ../resources/Orbitron-OFL.txt "$app/Contents/Resources/"
codesign --force --sign - "$app"

echo "Built $(pwd)/$app"

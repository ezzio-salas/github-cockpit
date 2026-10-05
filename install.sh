#!/bin/bash
# Installs GitHub Cockpit for the current user: a launcher on PATH, a desktop entry and
# the bundled font. Nothing is written outside ~/.local.
set -euo pipefail
cd "$(dirname "$0")"
source_dir="$PWD"

bin_dir="$HOME/.local/bin"
desktop_dir="$HOME/.local/share/applications"
font_dir="$HOME/.local/share/fonts/github-cockpit"

mkdir -p "$bin_dir" "$desktop_dir" "$font_dir"

# The launcher runs the widget from this checkout, so `git pull` is all an update takes.
cat > "$bin_dir/github-cockpit" <<LAUNCHER
#!/bin/bash
exec "$source_dir/run.sh" "\$@"
LAUNCHER
chmod +x "$bin_dir/github-cockpit"

cat > "$desktop_dir/github-cockpit.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=GitHub Cockpit
Comment=Open pull requests, floating above your windows
Exec=$bin_dir/github-cockpit
Terminal=false
Categories=Development;
X-GNOME-Autostart-enabled=true
DESKTOP

cp resources/Orbitron.ttf resources/Orbitron-OFL.txt "$font_dir/"
fc-cache -f "$font_dir" >/dev/null

echo "Installed. Run 'github-cockpit', or add it to your compositor's autostart."
if ! ldconfig -p 2>/dev/null | grep -q libgtk4-layer-shell; then
    echo
    echo "gtk4-layer-shell is missing. Without it the card is an ordinary window."
    echo "  sudo pacman -S gtk4-layer-shell"
fi

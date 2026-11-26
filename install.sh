#!/usr/bin/env bash
# Install Quantru for the current Linux user, without importing another installation.
set -euo pipefail
umask 077
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(id -u)" == 0 ]]; then echo "Run as your normal user, not root."; exit 1; fi
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then echo "Quantru's current Vulkan releases require Linux x86_64."; exit 1; fi
skip=0; check=0; update=0
for arg in "$@"; do
  case "$arg" in
    --skip-system-packages) skip=1;;
    --check) check=1;;
    --update) update=1; skip=1;;
    --help) echo "Usage: ./install.sh [--skip-system-packages] [--check] [--update]"; exit 0;;
    *) echo "Unknown argument: $arg"; exit 2;;
  esac
done
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/quantru"
DEST="$DATA/app"
if [[ "$DEST" == "$SOURCE" ]]; then echo "Run install.sh from a separate source checkout."; exit 1; fi
# Only package installation requires administrator privileges. No firewall packages.
if (( !skip && !check )); then
  . /etc/os-release
  family=" ${ID:-} ${ID_LIKE:-} "
  if [[ "$family" == *" arch "* ]]; then
    packages=(python python-gobject gtk4 libadwaita webkitgtk-6.0 curl bash ffmpeg poppler iproute2 qrencode vulkan-icd-loader noto-fonts polkit gst-plugins-base gst-plugins-good)
    if grep -q 0x1002 /sys/class/drm/card*/device/vendor 2>/dev/null; then packages+=(vulkan-radeon); fi
    if grep -q 0x8086 /sys/class/drm/card*/device/vendor 2>/dev/null; then packages+=(vulkan-intel); fi
    sudo pacman -S --needed "${packages[@]}"
  elif [[ "$family" == *" debian "* || "$family" == *" ubuntu "* ]]; then
    sudo apt-get update
    sudo apt-get install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-webkit-6.0 curl bash ffmpeg poppler-utils iproute2 qrencode libvulkan1 mesa-vulkan-drivers fonts-noto-core polkitd pkexec gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-pulseaudio
  elif [[ "$family" == *" fedora "* ]]; then
    sudo dnf install python3 python3-gobject gtk4 libadwaita webkitgtk6.0 curl bash ffmpeg-free poppler-utils iproute qrencode vulkan-loader mesa-vulkan-drivers google-noto-sans-fonts polkit gstreamer1-plugins-base gstreamer1-plugins-good
  else
    echo "Distribution not recognized. Install the runtime dependencies listed in INSTALL.md, then run with --skip-system-packages."
    exit 1
  fi
fi
for tool in python3 curl bash ffmpeg pdfinfo pdftotext pdftoppm ip qrencode; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool"; exit 1; }
done
python3 -B "$SOURCE/install.py" --check
if (( check )); then exit 0; fi
if (( update )); then
  if [[ ! -f "$DEST/.installed" ]]; then echo "No completed installation to update. Run ./install.sh first."; exit 1; fi
  if curl -fsS --max-time 2 http://127.0.0.1:8765/__version >/dev/null 2>&1; then
    echo "Close Quantru and its server before updating."; exit 1
  fi
else
  if [[ -e "$DEST/.installed" ]]; then
    echo "Quantru is already installed. Run ./install.sh --update to refresh the app without replacing personal data."
    exit 0
  fi
  if [[ -e "$DEST" && ! -f "$DEST/.installing" ]]; then echo "Refusing to overwrite an existing directory: $DEST"; exit 1; fi
  mkdir -p "$DEST/backend" "$DEST/web"
  touch "$DEST/.installing"
fi
# Explicit source allowlist. Never copy databases, settings, invitations,
# update state, downloaded weights, native builds or caches from the source.
cp "$SOURCE/app.py" "$SOURCE/tray.py" "$SOURCE/server.py" "$SOURCE/native-scroll.js" "$SOURCE/native-model-picker.js" "$SOURCE/native-focus.js" "$SOURCE/run.sh" "$SOURCE/run-web.sh" "$SOURCE/install.py" "$SOURCE/install.sh" "$SOURCE/INSTALL.md" "$DEST/"
cp "$SOURCE"/backend/*.py "$DEST/backend/"
cp -R "$SOURCE/web/." "$DEST/web/"
if (( update )); then
  echo "Quantru updated. Models, history and settings preserved."
  exit 0
fi
python3 -B "$DEST/install.py" --install
mv "$DEST/.installing" "$DEST/.installed"
printf '\nQuantru installed: %s\nOpen it from your application menu.\nClose any other Quantru server using ports 8765/8766 before launching.\n' "$DEST"

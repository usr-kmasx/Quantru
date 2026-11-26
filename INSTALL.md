# Installing Quantru on Linux

Run `./install.sh` as the user who will use Quantru (never as root).
The installer installs packages through pacman (Arch), apt (Debian/Ubuntu),
or dnf (Fedora). On other distributions install equivalent dependencies
and run `./install.sh --skip-system-packages`. Use `--check` for a
non-installing runtime check.

Requirements: Linux x86_64, Python 3.12+, GTK 4.10+, libadwaita 1.5+,
WebKitGTK 6.0, Python GObject bindings, SQLite FTS5, curl, Bash,
FFmpeg, Poppler utilities, iproute2, qrencode, compatible Vulkan loader
and GPU driver, C/C++ runtime, OpenMP and OpenSSL. Audio capture also
requires a working desktop audio system and GStreamer support.
Polkit is optional for automatic firewall changes; UFW/firewalld are optional.
NVIDIA users need their distribution's working Vulkan-capable NVIDIA driver.
Not all distribution releases provide the required APIs or a compatible
glibc for upstream release binaries. Older releases may need a newer OS
or native builds. No Docker, Node, pip, ROCm or CUDA is required.

This creates an independent installation under
`$XDG_DATA_HOME/quantru/app` (default `~/.local/share/quantru/app`).
It copies application source only, downloads official Vulkan engines and
pinned audio GGUF/safetensors models (about 1.17 GB before engines), checks
model sizes and SHA-256, and installs the existing SVG and freedesktop
launcher. Model licenses remain those of their upstream repositories.
Only voice isolation and Parakeet TDT 0.6B v3 Q8_0 are installed.
Chat and image models start unconfigured; select your own local model files
in the llama.cpp and stable-diffusion.cpp settings. No chat or image model
is downloaded by the installer. Downloads resume on retry. No user settings,
history, pairing secrets or locally downloaded models are imported.
Existing completed installations are not overwritten by a normal install.
Close Quantru and its server, then use `./install.sh --update` from the source
checkout to refresh the app code without downloading models again or replacing
personal settings and history.

Open Quantru from your desktop's application menu. The app does not load
models until used. Ports 8765 and 8766 must be free; stop another Quantru
instance before testing with a second Linux user on the same machine.
Desktop integration uses the freedesktop standard, not a GNOME extension.

The native app registers a StatusNotifierItem tray when a compatible desktop
tray is available. Its three actions are Open Quantru, Stop/Start server, and
Quit Quantru. GNOME requires a user-installed indicator extension to display
StatusNotifierItem icons; Quantru does not install desktop extensions.

Closing the window hides Quantru in the tray when registered. Quit Quantru
exits the application; without a working tray, closing the window exits normally.

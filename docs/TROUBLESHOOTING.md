# Troubleshooting

## Installation fails

Run `./install.sh --check` to validate installed dependencies. Use a recent Linux distribution with the required GTK, libadwaita, WebKitGTK 6.0, Python, and Vulkan APIs. Upstream binaries may require a newer glibc than an older distribution provides. For manually installed dependencies, use `./install.sh --skip-system-packages`.

Failed downloads can normally be resumed by running the installer again. Ensure sufficient disk space and a working network connection.

## No model is configured

A fresh installation intentionally has no chat or image weights. Open the relevant settings and choose existing compatible files using the native folder button or absolute paths. A projector must match the model.

## Model is slow or fails to load

Check that the Vulkan driver exposes the GPU. Reduce context length, model size, image resolution, or batch size as appropriate. Use a compatible quantization and memory allocation mode. Speculative decoding requires support from both the model and engine. Model speed varies with hardware and workload.

## Port already in use

Quantru needs ports 8765 and 8766. Close other instances, including servers launched from a terminal or another Linux account. A native window can hide into the tray without stopping its server.

## Tray icon does not appear

Your desktop must support StatusNotifierItem. GNOME typically needs a compatible indicator extension installed and enabled by the user. Without a registered tray, closing the window exits the app normally.

## Updates do not appear

Use **Quit Quantru** rather than closing the window into the tray. Stop any independently launched server, then run `git pull` and `./install.sh --update` from the source checkout. Restart the application afterward.

## Phone cannot connect

Use the same trusted private network, verify firewall access to the displayed address and port, and make sure the pairing has not expired. Guest Wi-Fi or client isolation may prevent communication. Do not disable your firewall or configure public port forwarding.

## Voice recording fails

Check microphone permission, your desktop audio system, and GStreamer support. Voice models must pass the installer's integrity checks. Mobile browsers may block microphone use over local HTTP.

## Reporting a bug

Include the distribution, driver, engine version, relevant settings (without personal paths), and concise reproduction steps. Redact private content, secrets, and identifiers.

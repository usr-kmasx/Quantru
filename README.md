<p align="center"><img src="web/logo.svg" width="88" alt="Quantru logo"></p>

# Quantru

A local multimodal AI desktop application for Linux, powered by Vulkan.

Quantru combines local language models, image generation, voice transcription, document context, and optional terminal tools in a single chat interface. It runs on your own computer, without requiring a cloud AI account.

## Features

- Local GGUF chat and multimodal models through llama.cpp, with reasoning, speculative decoding, and GPU memory controls.
- Image generation and reference images through stable-diffusion.cpp, with configurable models, LoRAs, samplers, and resolutions.
- Local voice isolation and speech-to-text through audio.cpp and Parakeet.
- Persistent conversations, document attachments, Markdown, syntax highlighting, math rendering, and isolated HTML previews.
- Streaming responses with a subtle token fade, live token count, average decoding speed, and context occupancy.
- Native GTK4/libadwaita window, model file picker, keyboard navigation, and system tray.
- Optional phone pairing over a trusted local network, synchronized conversations, and explicit shell-tool access with streamed command previews and terminal output.
- On-demand model loading and independent engine updates.

## Installation

Use a modern Linux x86_64 system with a working Vulkan driver.

```bash
git clone https://github.com/usr-kmasx/Quantru.git
cd Quantru
./install.sh
```

Run the installer as your regular user. It installs system dependencies on supported distributions, downloads Vulkan engines and the two voice models, and registers Quantru in the desktop application menu.

Chat and image models are **not included or downloaded automatically**. Bring compatible local model files and select them in the settings. See [Installation](INSTALL.md) for prerequisites, storage, supported platforms, and update instructions.

## Getting started

1. Open Quantru from your application menu.
2. Open the sidebar and select **llama.cpp**.
3. Select a local GGUF model using the folder button or enter its absolute path. Select a compatible multimodal projector if needed, then apply the settings.
4. Start a conversation. The chat model loads on demand.
5. For image generation, configure **stable-diffusion.cpp**, then enable the image tool with `@image`.

The microphone records, isolates, and transcribes speech locally into the message field. Review the text before sending it.

For browser-only use, start the installed server with:

```bash
"${XDG_DATA_HOME:-$HOME/.local/share}/quantru/app/run-web.sh"
```

Open http://127.0.0.1:8765 in your browser. Native file selection and tray integration are desktop-only features.

## Updating

Close the application using **Quit Quantru** in the tray and ensure the server has stopped. From the source checkout:

```bash
git pull
./install.sh --update
```

This updates application code without replacing downloaded models, settings, or chat history.

## Documentation

- [Installation and updates](INSTALL.md)
- [User guide](docs/USER_GUIDE.md)
- [Architecture and data storage](docs/ARCHITECTURE.md)
- [Security and privacy](docs/SECURITY.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Third-party components](docs/THIRD_PARTY.md)

## Compatibility and status

Quantru has been tested on Arch Linux with an AMD Radeon RX 580 8 GB using Vulkan. The installer also provides Debian/Ubuntu and Fedora package commands, but those distributions have not been validated end to end. Model support and performance depend on upstream engines, drivers, model architecture, and available memory.

This is the initial public version. The application is feature-complete for its current scope; further changes may follow as issues are found.

## Credits

Quantru builds on [llama.cpp](https://github.com/ggml-org/llama.cpp), [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp), [audio.cpp](https://github.com/0xShug0/audio.cpp), GTK, libadwaita, and WebKitGTK. Third-party libraries and models retain their respective licenses.

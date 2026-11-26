# Third-party components

Quantru integrates independently developed software and model artifacts. Their upstream terms apply separately from the application source.

| Component | Upstream |
| --- | --- |
| llama.cpp | https://github.com/ggml-org/llama.cpp |
| stable-diffusion.cpp | https://github.com/leejet/stable-diffusion.cpp |
| audio.cpp | https://github.com/0xShug0/audio.cpp |
| Inworld voice isolator | https://huggingface.co/Inworld/voice-isolator |
| Parakeet TDT GGUF | https://huggingface.co/audio-cpp/audio.cpp-gguf |
| GTK | https://www.gtk.org/ |
| libadwaita | https://gnome.pages.gitlab.gnome.org/libadwaita/ |
| WebKitGTK | https://webkitgtk.org/ |
| markdown-it | https://github.com/markdown-it/markdown-it |
| DOMPurify | https://github.com/cure53/DOMPurify |
| Highlight.js | https://github.com/highlightjs/highlight.js |
| KaTeX | https://github.com/KaTeX/KaTeX |
| markdown-it-texmath | https://github.com/goessner/markdown-it-texmath |

The bundled frontend license notices are preserved in `web/vendor/LICENSE-*.txt`. Frontend dependency versions are recorded in `frontend-deps/package.json` and its lockfile. Engine binaries and voice models are obtained from upstream during installation and are not redistributed in this repository. Check upstream model cards and licenses before redistributing model files or outputs.

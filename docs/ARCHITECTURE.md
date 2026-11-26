# Architecture and storage

Quantru uses Python and a bundled HTML/CSS/JavaScript interface. It does not require a Node.js server or a cloud inference service.

| Component | Responsibility |
| --- | --- |
| app.py, tray.py | GTK4/libadwaita desktop window, WebKitGTK, native dialogs, tray |
| server.py | Local HTTP API, streaming proxy, request and model lifecycle |
| backend/engine.py | llama.cpp Vulkan engine selection and launch |
| backend/image_generation.py | stable-diffusion.cpp image tool and model switching |
| backend/voice_capture.py | Local audio isolation and transcription |
| backend/chat_history.py | SQLite conversation archive |
| backend/context_memory.py, documents.py | Context budgeting, document extraction and retrieval |
| backend/attachment_store.py | Content-addressed attachment storage |
| backend/chat_sync.py, token_stats.py | Live conversation snapshots and measured inference statistics |
| backend/mobile_access.py, mobile_firewall.py | LAN pairing and scoped firewall assistance |
| backend/engine_updates.py | Staged image/audio engine updates |
| web/ | Bundled client, styles, and third-party frontend assets |

The local server listens on loopback port 8765. The internal llama.cpp server uses loopback port 8766. The optional phone feature adds an authenticated listener on the selected private network interface. Models are loaded on demand; inference speed and offloading depend on available GPU memory and the chosen model.

## Storage

The default installation is under `${XDG_DATA_HOME:-$HOME/.local/share}/quantru/app`. The backend directory contains local settings, a SQLite archive, downloaded engines, voice models, and pairing state. WebKit session data and caches use the corresponding XDG data/cache directories. User-selected chat and image weights remain in their original locations.

SQLite uses foreign keys, transactional archive mutations, FTS5 retrieval, and content-addressed attachment deduplication. Live synchronization state, including unfinished shell command previews, is transient. Completed responses retain inference statistics and reasoning-round boundaries alongside the existing shell transcripts. Voice processing uses temporary shared-memory storage; no separate persistent recording history is required for transcription.

Keep the installation directory private. Back up the archive and settings only while the server is stopped, and protect the backup as you would your conversations. Deleting a chat removes associated records and unreferenced attachment blobs; it is not a guarantee of forensic erasure.

## Source distribution

The repository includes application source and bundled frontend dependencies. Engine binaries, model weights, SQLite databases, local settings, pairing credentials, logs, and caches are excluded. The installer downloads the necessary public engines and pinned voice models separately.

Frontend dependency metadata is in `frontend-deps/`; the runtime uses vendored assets in `web/vendor/`.

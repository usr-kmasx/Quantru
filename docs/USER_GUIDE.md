# User guide

## Chat and models

Open the sidebar and select **llama.cpp**. Choose an existing GGUF file with the native folder picker or type its absolute path. For supported vision models, select the matching GGUF multimodal projector. Select a speculative decoding method only when the model and engine support it; some methods require a separate draft GGUF.

Configure context length, GPU allocation, cache precision, reasoning, sampling, and batch settings as needed. Apply changes before starting a conversation. Changes that require a model reload are labeled accordingly.

The chat model loads on the first request and unloads after inactivity. Streaming responses support Markdown, math, code highlighting, and reasoning blocks. Use the message actions to copy, edit, or regenerate a response. Editing or regenerating an earlier message replaces subsequent conversation messages after confirmation.

The response footer shows generated token count and cumulative decoding throughput. Throughput appears after an initial stabilization period and refreshes approximately once per second. The footer also shows context occupancy when supported by the engine, including cached and newly processed prompt tokens and tokens generated in the current inference round. Hover over the percentage to see the token counts and context capacity. Final statistics are saved with the response. Decoding throughput and generated token count include reasoning and tool tokens but exclude prompt processing.

## Image generation

Open **stable-diffusion.cpp** settings and select compatible local diffusion model, text encoder, and VAE files. Optional vision encoders and LoRAs can be selected separately. Choose resolution, steps, sampler, scheduler, CFG, seed, and memory options appropriate to the model; the defaults are not universal recommendations.

Type `@image` and select the image tool to permit the model to generate an image. Attach a reference image or refer to an image in the current conversation when using a compatible model. The image tool becomes available after applying valid image settings, without restarting the app. A configured chat model is required to plan the tool call; the chat engine releases memory for image generation and is restored afterward. Sampling progress and estimated remaining sampling time are displayed when reported by the image engine. Images are retained in the conversation archive.

## Voice and documents

Select the microphone, speak, and select it again to stop. The recording is processed locally and the transcription is inserted into the composer; it is not automatically sent. Microphone permission may be requested by the desktop.

Attach supported images, audio, PDF, DOCX, XLSX, or text/code files. Documents are extracted locally and relevant portions are selected to fit the context budget. Attached images appear separately from the text bubble. Attachments and generated images are stored in the local archive. Delete a conversation to remove its associated data, subject to shared attachment references.

## Terminal tool

Select `@shell` to explicitly allow the configured language model to execute shell commands for that request. Commands run under the desktop user's ordinary permissions, **not in a sandbox**. Review the implications before enabling this tool. Commands are displayed as the model writes them, followed by live terminal output and exit status. Each subsequent inference round has its own reasoning block below the preceding commands. The image and shell tools are mutually exclusive per request.

## Phone access

Use **Connect phone** in the desktop sidebar, then scan the QR code from a device on the same trusted local network. Pairings expire after seven days. Revoke access when no longer needed. Mobile clients share the same history and generation state. The connection is local HTTP, not encrypted HTTPS; do not expose it to the internet. Mobile microphone recording may be unavailable in an insecure browser context.

## Desktop controls

Move the mouse to the left edge of the window or click the app icon to open the sidebar. Drag the invisible top area to move the window. Tab and Shift+Tab navigate controls in both directions. The native model picker opens existing files without importing or copying weights. HTML previews run in an isolated iframe.

When a supported tray is registered, closing the window hides it. **Open Quantru** restores it, **Stop server** stops an idle server owned by the app, and **Quit Quantru** exits the application. Active requests are protected from interruption by the tray shutdown policy. A server started separately must be stopped separately.

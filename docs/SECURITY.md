# Security and privacy

Quantru is intended for local, single-user use. Inference, attachment extraction, and voice transcription are performed on the host. Installation and optional engine update checks make outbound requests to upstream GitHub and Hugging Face services. Do not interpret local inference as a guarantee of complete network isolation.

## Local access

The loopback API is intended for the trusted local desktop user. Do not forward its ports to the internet or expose them through an unauthenticated reverse proxy. Other processes with access to the local interface may be able to use the API.

Phone pairing is opt-in and restricted to a private local network. Pairing and session tokens are checked by the server. Network traffic is plain HTTP: anyone capable of intercepting it on the network may be able to read sensitive data. Use trusted networks only, and revoke pairings when finished.

If an active UFW or firewalld configuration is detected, Quantru can request authorization to add a narrowly scoped rule. It does not install, disable, or reset the firewall. If automatic configuration is unavailable, follow the displayed manual instructions.

## Shell access

The shell tool is explicitly enabled per request. It executes model-selected commands as the desktop user without filesystem isolation. Commands may read, modify, or delete files or use the network. Never enable it for untrusted instructions or sensitive environments. Paired phone access can also request shell execution, so protect pairing links and devices.

## Model files and updates

Use model files and engine releases from trusted sources. The installer verifies pinned voice model sizes and SHA-256 digests. The image/audio updater checks release integrity and validates candidate binaries before activation; previous builds are retained pending a successful inference. Automatic updates can introduce upstream changes. Review model licenses and compatibility before use.

## Reporting issues

Open a GitHub issue with a minimal reproduction for ordinary bugs. Do not publish private conversations, full local paths, pairing tokens, databases, credentials, or sensitive logs. For security-sensitive findings, avoid posting exploit details publicly; contact the repository owner through a suitable private channel if available.

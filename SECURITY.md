# Security

Tabletop Librarian is intended primarily for trusted self-hosted/LAN environments, but it still handles accounts, uploaded files, archives, and network-accessible AI services.

## Reporting

Please report security issues privately to the repository owner rather than publishing exploit details in a public issue before a fix is available.

## Deployment guidance

- Use strong account passwords.
- Do not expose TTL directly to the public internet without an appropriate reverse proxy/TLS/security configuration.
- Restrict firewall access to networks that need it.
- Treat imported `.ttlsys` and `.ttlchar` files as untrusted input; TTL validates paths, sizes, and package structure, but users should still obtain packs from trusted sources.
- Protect AI Backend API keys and do not expose the backend port broadly.

# Installation

Tabletop Librarian Server and TTL Local AI Backend are separate products. You may install only the Server, only the Backend, or place them on different machines.

## Windows Server

Run `TTL-Server-Windows-x64-1.0.0.exe`.

The installer:

- installs the Server under `C:\Program Files\Tabletop Librarian Server`;
- stores persistent application data under `C:\ProgramData\Tabletop Librarian`;
- defaults to TCP port 8080 and checks for a conflict;
- optionally creates a firewall rule for LAN access;
- installs **TTL Server Manager**, which provides Start, Stop, Open TTL, View Log, and Open Data Folder controls;
- preserves user data during normal upgrades and uninstall.

The Server itself is headless. Use **TTL Server Manager** from the Start Menu for normal start/stop operation.

## Windows Local AI Backend

Run `TTL-AI-Windows-x64-1.0.0.exe`.

The installer creates the Backend Manager and defaults to TCP port 8081. Runtime files, downloaded models, API key, and user settings are preserved across normal upgrades/uninstall.

The Manager downloads the selected llama.cpp runtime and GGUF model on demand; these are not bundled with the installer.

## Ubuntu 26.04 Server

Extract the Linux Server archive and run:

```bash
sudo ./install.sh
```

The installer creates a private Python environment and installs:

- application files under `/opt/tabletop-librarian`;
- persistent data under `/var/lib/tabletop-librarian`;
- cache under `/var/cache/tabletop-librarian`;
- logs under `/var/log/tabletop-librarian`;
- environment configuration in `/etc/tabletop-librarian.env`;
- a systemd service named `tabletop-librarian`.

Useful service commands:

```bash
sudo systemctl status tabletop-librarian
sudo systemctl restart tabletop-librarian
sudo systemctl stop tabletop-librarian
sudo systemctl start tabletop-librarian
journalctl -u tabletop-librarian -n 100 --no-pager
```

Normal uninstall preserves data:

```bash
sudo ./uninstall.sh
```

Only use `--purge-data` when you intentionally want to remove persistent TTL data.

## Ubuntu 26.04 Local AI Backend

Install as the desktop user, not root:

```bash
./install.sh
```

The launcher is installed under the user's local application directories and appears in the desktop application menu. The Manager downloads its own llama.cpp runtime and models.

## Network access

The Server binds to all interfaces by default and therefore can be reached from another LAN machine when the host firewall allows the configured port. Use authentication even on a trusted LAN.

The Local AI Backend can also be placed on a different LAN host. Configure the Server with the Backend's OpenAI-compatible base URL and API key.

## Upgrades

Release installers are designed to preserve:

- Server users/configuration/library/characters/System Packs/knowledgebase state;
- Backend model/runtime downloads and settings.

Back up important application data before any major upgrade.

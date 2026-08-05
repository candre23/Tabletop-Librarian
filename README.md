# Tabletop Librarian v0.1.10

Self-hosted tabletop RPG library, rules helper, and character resource server.

## v0.1 functionality

- First-run GM account setup and player management
- Filesystem-backed virtual library folders
- Multiple directories and individual files per virtual folder
- Folder and per-document visibility controls
- Automatic and manually overridden covers
- PDF, image, CBR, CBZ, TXT, and Markdown readers
- PDF range streaming
- Basic in-document search
- Player uploads with GM assignment into virtual folders
- Scanned-PDF detection for future OCR support

## Run

```bash
source .venv/bin/activate
python run.py
```

Open `http://SERVER-IP:8080/`.

Stop with `Ctrl+C`.

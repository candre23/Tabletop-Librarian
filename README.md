# Tabletop Librarian v0.2.1

Self-hosted tabletop RPG library, rules helper, and character resource server.

## Phase 0.2 work

- Page-aware text extraction for searchable PDFs
- Text extraction for TXT and Markdown
- Disposable extracted-text cache
- Source size/mtime validation so changed documents are re-extracted
- Scanned PDFs skipped pending OCR support
- GM Search Index management page

## Run

```bash
source .venv/bin/activate
python run.py
```

Open `http://SERVER-IP:8080/`.

Stop with `Ctrl+C`.

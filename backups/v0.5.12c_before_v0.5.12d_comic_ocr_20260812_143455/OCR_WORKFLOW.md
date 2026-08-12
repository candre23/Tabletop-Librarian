# Tabletop Librarian OCR Workflow

TTLibrarian treats OCR as an ingestion/preprocessing step for scanned PDFs. It does not modify the source library.

## Storage model

The physical RPG library may be mounted read-only. TTL therefore keeps OCR results permanently on the TTL host:

- `data/ocr/pdf/` — searchable PDF derivatives
- `data/ocr/meta/` — source identity/signature metadata

Each derivative is keyed to the absolute source path and records the source file size and modification timestamp. If the source PDF changes, the old derivative is no longer considered current and the book returns to **Need OCR** status. The old local file is replaced only after a new OCR run succeeds.

The normal extracted-text cache continues to identify the book by its original source path. This keeps retrieval, citations, visibility rules, and library organization tied to the real library document rather than to TTL's private OCR copy.

## Dependencies

OCR uses the `ocrmypdf` command and Tesseract OCR. For Debian/Ubuntu systems, install OCRmyPDF with:

```bash
sudo apt install ocrmypdf
```

TTL detects the required executables and disables OCR controls with an explanatory warning when they are unavailable.

## Default processing

The initial workflow is intentionally conservative:

- English OCR
- one OCR job at a time
- one OCRmyPDF worker (`--jobs 1`)
- automatic page rotation
- deskewing
- existing text pages are preserved/skipped rather than rasterized and OCRed again
- output is a standard PDF rather than PDF/A

Source PDFs are never overwritten.

## Knowledgebase integration

Knowledgebase Tools lists PDFs that TTL's existing text detector considers scanned. Each can be OCRed individually, or the GM can choose **OCR All Required PDFs**.

After a successful OCR batch TTL automatically:

1. refreshes extracted text;
2. rebuilds context chunks;
3. invalidates stale semantic vectors; and
4. starts a fresh embedding build.

The OCR job itself can be cancelled. An incomplete working PDF is deleted and never replaces a previously completed derivative.

## Progress

While OCRmyPDF exposes progress information, exact page progress varies somewhat by OCRmyPDF version and processing stage. TTL reports the current file, known page count, and any percentage/page progress emitted by OCRmyPDF; otherwise the progress bar remains indeterminate for that stage. The subsequent extracted-text/chunk/embedding stages are reported separately.

## Future extensions

The preset is English-only for now. Additional OCR languages can be added later by exposing Tesseract language selection after installing the corresponding host language packs. Worker count can also become an advanced setting if faster hosts benefit from parallel OCR.

## v0.5.12b behavior

OCR progress is reported through OCRmyPDF's supported `get_progressbar_class` plugin hook rather than by parsing terminal progress output. TTLibrarian shows the current OCRmyPDF phase and page progress when the phase reports page units.

Completing OCR does **not** automatically rebuild extracted text, chunks, or embeddings. It marks the knowledgebase as needing an update and leaves the existing knowledgebase usable until the GM explicitly chooses **Update Knowledgebase**.

Library Management continues to classify the read-only source PDF as scanned, but overlays the persistent derivative state: **OCR required** means no current local derivative exists; **OCR complete** means a current local derivative is available under `data/ocr`.

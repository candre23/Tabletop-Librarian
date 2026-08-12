# Tabletop Librarian OCR Workflow

TTLibrarian treats OCR as an ingestion/preprocessing step for image-only documents. It never modifies the source library, so read-only network shares are fully supported.

## Supported source formats

OCR currently supports:

- scanned/image-only PDF files;
- CBZ comic/image archives; and
- CBR comic/image archives.

For PDF sources, OCRmyPDF processes the source directly. For CBZ/CBR sources, TTL first assembles the archive's page images into a temporary local image-only PDF, preserving the reader's page order, then sends that temporary PDF through the same OCRmyPDF workflow. The temporary assembly is deleted after the OCR attempt.

CBR extraction reuses TTL's existing `unrar`/7-Zip support. CBZ uses Python's ZIP support. No additional OCR dependency is required beyond OCRmyPDF and Tesseract.

## Storage model

TTL keeps completed OCR results permanently on the TTL host:

- `data/ocr/pdf/` — searchable PDF derivatives;
- `data/ocr/meta/` — source identity/signature metadata; and
- `data/ocr/work/` — temporary comic-to-PDF assembly files, removed after processing.

Each derivative is keyed to the absolute source path and records the source file size and modification timestamp. If the original PDF, CBR, or CBZ changes, its old OCR derivative is no longer considered current and the document returns to **OCR required** status.

The extracted-text cache continues to identify every document by its original library path. Retrieval, citations, visibility rules, and library organization therefore remain tied to the real source document rather than TTL's private OCR PDF.

## Dependencies

OCR uses OCRmyPDF and Tesseract. On Debian/Ubuntu:

```bash
sudo apt install ocrmypdf tesseract-ocr
```

TTL detects these executables and disables OCR controls with an explanatory warning when they are unavailable.

## Default processing

The workflow is intentionally conservative:

- English OCR;
- one OCR job at a time;
- one OCRmyPDF worker (`--jobs 1`);
- automatic page rotation;
- deskewing;
- existing PDF text pages are preserved with `--skip-text`; and
- standard PDF output rather than PDF/A.

Source files are never overwritten.

## Comic archive conversion

CBZ/CBR archives are page-image containers, so TTL treats them as OCR candidates automatically. Pages are assembled into a temporary PDF using PyMuPDF before OCR. JPEG and PNG pages are embedded directly; other supported reader image formats are normalized to PNG when necessary.

Page ordering uses the same natural-sort logic as the comic reader so filenames such as `1.jpg`, `2.jpg`, and `10.jpg` remain in the expected order.

The original CBR/CBZ remains the document users open in the Library. The generated searchable PDF exists only as TTL's local text/OCR derivative for knowledgebase extraction.

## Knowledgebase integration

Knowledgebase Tools lists all scanned PDFs and CBR/CBZ archives. Each can be OCRed individually, or the GM can choose **OCR All Required**.

Completing OCR does not automatically rebuild the knowledgebase. TTL marks the knowledgebase as needing an update and leaves the existing knowledgebase usable until the GM explicitly chooses **Update Knowledgebase**.

On the next manual update, text extraction reads the persistent OCR PDF for scanned PDFs and comic archives, then proceeds through the normal chunk and embedding workflow.

## Progress and cancellation

TTL reports OCR progress through OCRmyPDF's supported progress hook rather than parsing terminal UI output. PDF OCR displays scanning/OCR page progress when available.

For CBR/CBZ sources, TTL additionally reports per-page progress while assembling the temporary PDF before OCR begins.

The OCR job can be cancelled. Incomplete output PDFs and temporary comic assembly PDFs are deleted and never replace a previously completed derivative.

## Library status

Library Management shows a quick visual OCR state for image-only documents:

- **OCR required** in orange; and
- **OCR complete** in green.

For scanned PDFs and comic archives, **OCR complete** means a current persistent searchable derivative exists under `data/ocr`; it does not mean the original source file was modified.

## Future extensions

The default is English-only. Additional Tesseract languages and configurable worker counts can be exposed later without changing the derivative format or knowledgebase integration.

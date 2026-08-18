# OCR Workflow

TTL treats OCR as a persistent preprocessing step. Source books are never overwritten.

## Storage model

OCR results are stored under TTL's writable data directory. A derivative is associated with the source document identity/signature. If the source changes, the derivative is considered stale and the document returns to an OCR-required state.

Extracted text and citations continue to use the original library path as the document identity.

## Processing

The default workflow is conservative:

- Tesseract OCR;
- one OCR job at a time;
- one OCRmyPDF worker;
- automatic rotation;
- deskewing;
- pages that already contain text are preserved/skipped;
- standard searchable PDF output rather than PDF/A.

OCR jobs can be cancelled. An incomplete working file never replaces a previously completed derivative.

## Platform dependencies

Ubuntu release installation uses the host OCRmyPDF/Tesseract packages.

The Windows Server build bundles a private OCRmyPDF helper and Tesseract runtime so the end user does not need to install them separately.

## Knowledgebase interaction

Completing OCR marks the Knowledgebase as needing an update. The existing Knowledgebase remains usable until the GM explicitly chooses **Update Knowledgebase**. The subsequent update is incremental, so unchanged documents retain existing chunks and semantic vectors.

# Third-Party Notices

Tabletop Librarian itself is distributed under the Unlicense. Third-party works and components retain their own licenses; the Unlicense does not replace or override them.

## System Reference Document 5.2.1

The repository includes `docs/reference/SRD_CC_v5.2.1.pdf`, and the built-in **Generic D20** System Pack contains material adapted from the System Reference Document 5.2.1 ("SRD 5.2.1") by Wizards of the Coast LLC.

The SRD 5.2.1 is licensed under the **Creative Commons Attribution 4.0 International License (CC BY 4.0)**.

Attribution:

> This work includes material from the System Reference Document 5.2.1 ("SRD 5.2.1") by Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd. The SRD 5.2.1 is licensed under the Creative Commons Attribution 4.0 International License, available at https://creativecommons.org/licenses/by/4.0/legalcode.

The SRD PDF and SRD-derived material are not dedicated to the public domain by Tabletop Librarian. The `Generic D20` pack declares `CC-BY-4.0` in its manifest.

`docs/reference/SRD_5.2_cover.png` is project artwork created for Tabletop Librarian and is not part of the SRD.

## Windows Server bundled tools

The Windows Server build incorporates third-party runtime components so end users do not have to install them separately:

- **7-Zip** for CBR/RAR extraction. The Windows build copies the 7-Zip binary license file alongside the redistributed binaries.
- **Tesseract OCR** for optical character recognition. Tesseract is distributed under the Apache License 2.0.
- **OCRmyPDF** for searchable OCR PDF generation. OCRmyPDF is distributed under the Mozilla Public License 2.0 (MPL-2.0); some of its bundled/non-core components have separate licenses documented by that project.

The Windows build process preserves/carries the applicable upstream license materials with the bundled components. Do not remove those notices when redistributing a compiled installer.

## Python and other dependencies

Tabletop Librarian depends on third-party Python packages listed in `pyproject.toml` and, for the AI Backend, runtime components downloaded by the Backend Manager. Those projects retain their respective licenses and copyrights. Installing or redistributing Tabletop Librarian does not relicense those third-party works under the Unlicense.

from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, Response, StreamingResponse

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def stream_pdf(request: Request, path: Path):
    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{path.name}"',
        "Cache-Control": "private, max-age=0, must-revalidate",
    }

    if not range_header:
        return FileResponse(path, media_type="application/pdf", headers=headers)

    match = RANGE_RE.fullmatch(range_header.strip())
    if not match:
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{file_size}"},
        )

    start_text, end_text = match.groups()

    if start_text == "":
        suffix_length = int(end_text or "0")
        if suffix_length <= 0:
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{file_size}"},
            )
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1

    if start < 0 or start >= file_size or end < start:
        return Response(
            status_code=416,
            headers={**headers, "Content-Range": f"bytes */{file_size}"},
        )

    end = min(end, file_size - 1)
    length = end - start + 1

    def body():
        remaining = length
        with path.open("rb") as handle:
            handle.seek(start)
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        body(),
        status_code=206,
        media_type="application/pdf",
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
        },
    )

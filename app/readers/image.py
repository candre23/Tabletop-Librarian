from pathlib import Path

from fastapi.responses import FileResponse

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def serve_image(path: Path):
    return FileResponse(
        path,
        media_type=MEDIA_TYPES.get(path.suffix.casefold(), "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )

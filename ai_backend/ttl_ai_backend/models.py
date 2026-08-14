from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    name: str
    filename: str
    repo: str
    description: str
    approximate_gb: float
    alias: str
    recommended: bool = False

    @property
    def url(self) -> str:
        quoted = urllib.parse.quote(self.filename)
        return f"https://huggingface.co/{self.repo}/resolve/main/{quoted}?download=true"


CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel(
        id="qwen35-9b-ud-q5xl",
        name="Qwen 3.5 9B UD-Q5_K_XL",
        filename="Qwen3.5-9B-UD-Q5_K_XL.gguf",
        repo="unsloth/Qwen3.5-9B-GGUF",
        description="Recommended TTL model. Best match for the development/reference configuration.",
        approximate_gb=6.74,
        alias="qwen3.5-9b-q5",
        recommended=True,
    ),
    CatalogModel(
        id="qwen35-9b-ud-q4xl",
        name="Qwen 3.5 9B UD-Q4_K_XL",
        filename="Qwen3.5-9B-UD-Q4_K_XL.gguf",
        repo="unsloth/Qwen3.5-9B-GGUF",
        description="Lower-memory 9B option with a modest quality tradeoff.",
        approximate_gb=5.97,
        alias="qwen3.5-9b-q4",
    ),
    CatalogModel(
        id="qwen35-4b-ud-q5xl",
        name="Qwen 3.5 4B UD-Q5_K_XL",
        filename="Qwen3.5-4B-UD-Q5_K_XL.gguf",
        repo="unsloth/Qwen3.5-4B-GGUF",
        description="Smaller option for low-memory or CPU-oriented systems.",
        approximate_gb=3.25,
        alias="qwen3.5-4b-q5",
    ),
)


def installed_models(models_dir: Path) -> list[Path]:
    if not models_dir.exists():
        return []
    return sorted((p for p in models_dir.glob("*.gguf") if p.is_file()), key=lambda p: p.name.lower())


def download_model(
    model: CatalogModel,
    models_dir: Path,
    progress: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    models_dir.mkdir(parents=True, exist_ok=True)
    target = models_dir / model.filename
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(model.url, headers={"User-Agent": "TTL-AI-Backend/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, partial.open("wb") as fh:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel and cancel():
                    raise InterruptedError("Download cancelled")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        partial.replace(target)
        return target
    except Exception:
        try:
            partial.unlink()
        except OSError:
            pass
        raise

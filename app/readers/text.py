from pathlib import Path

import bleach
import markdown

ALLOWED_TAGS = {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "u", "s",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "a",
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
}


def read_plain_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def render_markdown(path: Path) -> str:
    source = read_plain_text(path)
    rendered = markdown.markdown(
        source,
        extensions=["tables", "fenced_code"],
    )
    return bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )

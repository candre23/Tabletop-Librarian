from __future__ import annotations
import html
import re
from markupsafe import Markup

INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
CITATION_RE = re.compile(r"(?<!\w)\[(\d{1,2})\]")


def _inline(text: str, source_count: int) -> str:
    escaped = html.escape(text, quote=False)
    slots: list[str] = []

    def stash(match: re.Match[str]) -> str:
        slots.append(f"<code>{html.escape(match.group(1), quote=False)}</code>")
        return f"\x00CODE{len(slots)-1}\x00"

    escaped = INLINE_CODE_RE.sub(stash, escaped)
    escaped = BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = ITALIC_RE.sub(r"<em>\1</em>", escaped)

    def cite(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if 1 <= number <= source_count:
            return f'<a class="answer-citation" href="#source-{number}" data-source-number="{number}">[{number}]</a>'
        return match.group(0)

    escaped = CITATION_RE.sub(cite, escaped)
    for i, code in enumerate(slots):
        escaped = escaped.replace(f"\x00CODE{i}\x00", code)
    return escaped


def render_answer_markdown(text: str, source_count: int = 0) -> Markup:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            content = " ".join(x.strip() for x in paragraph if x.strip())
            if content:
                out.append(f"<p>{_inline(content, source_count)}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            flush_paragraph(); close_list()
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_lines), quote=False) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw); continue
        if not line.strip():
            flush_paragraph(); close_list(); continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph(); close_list()
            level = len(heading.group(1)) + 1
            out.append(f"<h{level}>{_inline(heading.group(2), source_count)}</h{level}>")
            continue

        unordered = re.match(r"^\s*[-*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            wanted = "ul" if unordered else "ol"
            if list_type != wanted:
                close_list(); out.append(f"<{wanted}>"); list_type = wanted
            out.append(f"<li>{_inline((unordered or ordered).group(1), source_count)}</li>")
            continue

        if line.lstrip().startswith(">"):
            flush_paragraph(); close_list()
            out.append(f"<blockquote>{_inline(line.lstrip()[1:].lstrip(), source_count)}</blockquote>")
            continue

        paragraph.append(line)

    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_lines), quote=False) + "</code></pre>")
    flush_paragraph(); close_list()
    return Markup("\n".join(out))

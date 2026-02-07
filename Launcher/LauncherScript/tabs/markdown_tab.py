# tabs/markdown_tab.py - Markdown rendering tab using tkinterweb
from __future__ import annotations

import os
import re
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit

import mistune
from tkinterweb import HtmlFrame

from .base import Tab


class MarkdownTab(Tab):
    """A tab that renders a Markdown file with GitHub-like dark styling."""

    def __init__(
        self,
        title: str,
        md_file_path: str,
        open_tab: Callable[[Tab], None] | None = None,
        fragment: str | None = None,
    ) -> None:
        super().__init__(title)
        self.md_file_path: str = md_file_path
        self.open_tab: Callable[[Tab], None] | None = open_tab
        self.fragment: str | None = fragment
        self.html_widget: HtmlFrame | None = None

    def build_content(self) -> None:
        """Read Markdown, convert to HTML, and render it in HtmlFrame."""
        md_path: Path = Path(self.md_file_path).resolve()
        md_dir: Path = md_path.parent

        with open(md_path, "r", encoding="utf-8-sig") as f:
            md_content: str = f.read()

        html_body: str = mistune.html(md_content)
        html_body = self._add_heading_ids(html_body)
        html_body = self._inject_inline_code_styles(html_body)

        document: str = self._build_document(html_body)

        self.html_widget = HtmlFrame(
            self.frame,
            on_link_click=self._handle_link_click,
            messages_enabled=False,
            dark_theme_enabled=True,
            shrink=False,
        )
        self.html_widget.pack(expand=True, fill="both")

        base_url: str = md_dir.as_uri() + "/"
        self.html_widget.load_html(document, base_url=base_url, fragment=self.fragment)

    def _handle_link_click(self, url: str) -> None:
        """Open .md links in new app tabs, external links in browser, others in-frame."""
        if self.html_widget is None:
            return

        parts = urlsplit(url)

        if parts.scheme in ("http", "https", "mailto"):
            webbrowser.open(url)
            return

        path_part: str = parts.path or ""
        fragment: str | None = parts.fragment if parts.fragment else None

        # Handle relative or file:// markdown links by opening in a new app tab.
        if path_part and path_part.lower().endswith(".md") and self.open_tab:
            resolved = self._resolve_local_path(parts.scheme, path_part)
            if resolved and resolved.lower().endswith(".md") and os.path.isfile(resolved):
                self.open_tab(
                    MarkdownTab(
                        title=os.path.basename(resolved),
                        md_file_path=resolved,
                        open_tab=self.open_tab,
                        fragment=fragment,
                    )
                )
                return

        # Let tkinterweb handle anchors and non-markdown local links.
        self.html_widget.load_url(url)

    def _resolve_local_path(self, scheme: str, path_part: str) -> str | None:
        """Resolve link paths from relative/file URLs to local absolute paths."""
        if scheme == "file":
            local: str = unquote(path_part)
            # file:///C:/... => /C:/... on Windows
            if re.match(r"^/[A-Za-z]:/", local):
                local = local[1:]
            return os.path.normpath(local)

        if scheme:
            return None

        md_dir: str = os.path.dirname(os.path.abspath(self.md_file_path))
        return os.path.normpath(os.path.join(md_dir, unquote(path_part)))

    def _build_document(self, html_body: str) -> str:
        """Wrap rendered Markdown body in a full HTML document with dark theme styles."""
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="dark">
  <style>
    :root {{
      --bg: #0d1117;
      --fg: #c9d1d9;
      --heading: #f0f6fc;
      --muted: #8b949e;
      --border: #30363d;
      --code-bg: #30363d;
      --link: #58a6ff;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      line-height: 1.5;
      font-size: 16px;
    }}
    body {{
      padding: 12px 14px;
      overflow-x: auto;
    }}
    h1, h2, h3, h4, h5, h6 {{
      color: var(--heading);
      margin: 18px 0 12px;
      line-height: 1.25;
    }}
    h1, h2 {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.3em;
    }}
    p, ul, ol, pre, blockquote {{
      margin: 0 0 12px;
    }}
    ul, ol {{
      padding-left: 1.7em;
    }}
    li + li {{
      margin-top: 0.25em;
    }}
    a {{
      color: var(--link);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    code {{
      background-color: var(--code-bg) !important;
      color: #e6edf3 !important;
      border: none !important;
      border-radius: 4px !important;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 88% !important;
      font-weight: 600 !important;
      letter-spacing: 0 !important;
      padding: 0.16em 0.4em !important;
      text-shadow: none !important;
    }}
    pre {{
      background: #161b22;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: auto;
      padding: 12px;
    }}
    pre code {{
      background: transparent;
      border: 0;
      border-radius: 0;
      font-weight: 400;
      padding: 0;
      font-size: 100%;
    }}
    img {{
      max-width: none;
      height: auto;
    }}
    hr {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 20px 0;
    }}
    blockquote {{
      color: var(--muted);
      border-left: 0.25em solid var(--border);
      padding: 0 1em;
    }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""

    def _add_heading_ids(self, html_body: str) -> str:
        """Add GitHub-style slug ids to headings so #fragment links can scroll reliably."""
        slug_counts: dict[str, int] = {}

        def repl(match: re.Match[str]) -> str:
            level: str = match.group(1)
            inner_html: str = match.group(2)
            text: str = re.sub(r"<[^>]+>", "", inner_html).strip()
            base_slug: str = self._make_slug(text)
            count: int = slug_counts.get(base_slug, 0)
            slug_counts[base_slug] = count + 1
            slug: str = base_slug if count == 0 else f"{base_slug}-{count}"
            return f'<h{level} id="{slug}">{inner_html}</h{level}>'

        return re.sub(r"<h([1-6])>(.*?)</h\1>", repl, html_body, flags=re.DOTALL)

    def _inject_inline_code_styles(self, html_body: str) -> str:
        """Force code-chip styling inline so it is honored even if CSS selectors are limited."""
        code_style = (
            "background-color:#30363d !important;"
            "color:#e6edf3 !important;"
            "border:none !important;"
            "border-radius:4px !important;"
            "font-size:88% !important;"
            "font-weight:600 !important;"
            "letter-spacing:0 !important;"
            "padding:0.16em 0.4em !important;"
            "text-shadow:none !important;"
        )

        def repl(match: re.Match[str]) -> str:
            attrs: str = match.group(1) or ""
            if 'style="' in attrs:
                attrs = re.sub(r'style="([^"]*)"', lambda m: f'style="{m.group(1)};{code_style}"', attrs)
                return f"<code{attrs}>"
            return f'<code{attrs} style="{code_style}">'

        return re.sub(r"<code([^>]*)>", repl, html_body)

    @staticmethod
    def _make_slug(text: str) -> str:
        slug: str = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug)
        return slug

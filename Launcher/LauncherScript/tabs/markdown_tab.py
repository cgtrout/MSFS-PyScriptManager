# tabs/markdown_tab.py - Markdown rendering tab

import os
import re
import threading
import tkinter as tk
from tkinter import ttk

import mistune
from tkhtmlview import HTMLScrolledText
import tkhtmlview.html_parser as _tkhtmlview_parser

from .base import Tab
from config import TEXT_WIDGET_BG_COLOR


class MarkdownTab(Tab):
    """A tab that renders a Markdown file as HTML."""
    def __init__(self, title, md_file_path, open_tab=None, fragment=None):
        super().__init__(title)
        self.md_file_path = md_file_path
        self.open_tab = open_tab
        self.fragment = fragment

    def build_content(self):
        """Read the Markdown file and render it as HTML."""
        with open(self.md_file_path, "r", encoding="utf-8") as f:
            self._md_content = f.read()

        html_body = mistune.html(self._md_content)

        # CommonMark "loose lists" wrap every <li> content in <p>, which tkhtmlview renders as a blank line
        # before the text — splitting bullet numbers from their content. Strip the <p> wrapper; where a
        # list item has multiple paragraphs (e.g. text + image), collapse the </p><p> boundary to <br>.
        html_body = re.sub(r'<li>\s*<p>', '<li>', html_body)
        html_body = re.sub(r'</p>\s*</li>', '</li>', html_body)
        html_body = re.sub(r'</p>\s*<p>', '<br>', html_body)

        # Apply GitHub dark mode colors via inline styles (tkhtmlview supports per-element inline styles)
        html_body = re.sub(r'<a\s', '<a style="color: #58a6ff" ', html_body)
        html_body = re.sub(r'<h([1-6])>', r'<h\1 style="color: #f0f6fc">', html_body)
        html_body = re.sub(r'<pre>', '<pre style="background-color: #1e1e2e">', html_body)

        # tkhtmlview fetches remote images synchronously (requests.get per <img>).  Render
        # immediately with placeholders so the tab appears fast, then fetch in the background
        # and re-render once they are cached.
        remote_img_urls = re.findall(r'<img\s[^>]*src="(https?://[^"]*)"[^>]*/?>',  html_body)
        if remote_img_urls:
            self._html_body = html_body  # full version for the background re-render
            html_body = re.sub(r'<img\s[^>]*src="https?://[^"]*"[^>]*/?>',
                               '<em style="color: #484f58">[image]</em>', html_body)

        # tkhtmlview defaults foreground to "black" via DEFAULT_STACK regardless of the widget fg kwarg.
        # Patch it to a soft dark-mode gray before set_html (which deepcopies DEFAULT_STACK), then restore.
        _orig_fg = _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"]
        _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"] = [("__DEFAULT__", "#c9d1d9")]

        # Note: must use background= (long form) — tkhtmlview's _w_init checks for that key specifically
        self.html_widget = HTMLScrolledText(
            self.frame,
            background=TEXT_WIDGET_BG_COLOR,
            padx=10,
            pady=5,
        )
        self.html_widget.set_html(html_body)

        _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"] = _orig_fg

        self._apply_content_fixes()

        # Replace tkhtmlview's plain tk.Scrollbar with a ttk.Scrollbar so it picks up the app dark theme
        self.html_widget.vbar.destroy()
        scrollbar = ttk.Scrollbar(self.html_widget.frame, orient="vertical", command=self.html_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.html_widget.configure(yscrollcommand=scrollbar.set)

        self.html_widget.pack(expand=True, fill="both")

        # Scroll to the heading that matches the #fragment, if one was specified
        if self.fragment:
            self._scroll_to_heading(self.fragment)

        # Kick off background fetch for remote images; widget re-renders when they arrive
        if remote_img_urls:
            threading.Thread(target=self._fetch_and_rerender,
                             args=(remote_img_urls,), daemon=True).start()

    def _apply_content_fixes(self):
        """Re-apply widget-content fixes after every set_html()."""
        self._rebind_links()

        # tkhtmlview positions bullets via tab stops (bullet at px 30, text at px 35) but never sets
        # lmargin2, so wrapped lines fall back to the left edge.  Fix the indent.
        for line_num, line in enumerate(self.html_widget.get("1.0", tk.END).split('\n'), start=1):
            if line.startswith('\t'):
                self.html_widget.tag_add("_li_indent", f"{line_num}.0", f"{line_num}.end")
        self.html_widget.tag_config("_li_indent", lmargin2=35)

        self.html_widget.config(state=tk.DISABLED)

    def _fetch_and_rerender(self, urls):
        """Fetch remote images in parallel, then schedule a re-render on the main thread."""
        from concurrent.futures import ThreadPoolExecutor
        import requests
        from PIL import Image
        from io import BytesIO
        from copy import deepcopy

        def fetch_one(url):
            try:
                return url, Image.open(BytesIO(requests.get(url, timeout=15).content))
            except Exception:
                return url, None

        with ThreadPoolExecutor(max_workers=len(urls)) as pool:
            results = list(pool.map(fetch_one, urls))

        # Pre-populate the parser's image cache so set_html() won't re-fetch
        for url, img in results:
            if img is not None:
                self.html_widget.html_parser.cached_images[url] = deepcopy(img)

        # Schedule re-render on the Tk main thread
        self.html_widget.after(0, self._rerender_with_images)

    def _rerender_with_images(self):
        """Re-render the widget with remote images now that they are cached."""
        if not self.frame or not self.frame.winfo_exists():
            return  # tab was closed while images were downloading

        # Preserve scroll position across the re-render
        yview_top = self.html_widget.yview()[0]

        _orig_fg = _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"]
        _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"] = [("__DEFAULT__", "#c9d1d9")]

        self.html_widget.set_html(self._html_body)

        _tkhtmlview_parser.DEFAULT_STACK["config"]["foreground"] = _orig_fg

        self._apply_content_fixes()

        # Restore scroll position
        self.html_widget.yview_moveto(yview_top)

    def _rebind_links(self):
        """Rebind relative .md links to open as new tabs; anchor links to scroll; leave http(s) to browser."""
        md_dir = os.path.dirname(os.path.abspath(self.md_file_path))
        for slot in self.html_widget.html_parser.hlink_slots:
            url = slot.URL
            # Leave absolute URLs to tkhtmlview's default webbrowser handler
            if url.startswith(("http://", "https://", "mailto:")):
                continue
            # Split into path and #fragment
            parts = url.split("#", 1)
            path_part = parts[0]
            fragment = parts[1] if len(parts) > 1 else None

            if not path_part:
                # Anchor-only link (#section) — scroll to heading in current tab
                if fragment:
                    self.html_widget.tag_unbind(slot.tag_name, "<Button-1>")
                    self.html_widget.tag_bind(
                        slot.tag_name, "<Button-1>",
                        lambda event, frag=fragment: self._scroll_to_heading(frag)
                    )
                continue

            if not self.open_tab:
                continue
            resolved = os.path.normpath(os.path.join(md_dir, path_part))
            if resolved.lower().endswith(".md") and os.path.isfile(resolved):
                self.html_widget.tag_unbind(slot.tag_name, "<Button-1>")
                self.html_widget.tag_bind(
                    slot.tag_name, "<Button-1>",
                    lambda event, path=resolved, frag=fragment: self.open_tab(MarkdownTab(
                        title=os.path.basename(path),
                        md_file_path=path,
                        open_tab=self.open_tab,
                        fragment=frag
                    ))
                )

    def _scroll_to_heading(self, fragment):
        """Find the heading whose slug matches fragment and scroll the widget to it."""
        for line in self._md_content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            heading_text = stripped.lstrip("#").strip()
            # Render through mistune so CommonMark rules apply (e.g. mid-word underscores in
            # filenames stay literal), then strip the HTML tags to get the plain text that
            # tkhtmlview actually inserted into the widget.
            plain = re.sub(r'<[^>]+>', '', mistune.html(heading_text)).strip()
            if self._make_slug(plain) == fragment:
                # search() returns the first match — skip any hits that are inside list
                # items or body text (e.g. the same word in a ToC entry) by requiring the
                # match to be the only content on its line.
                idx = "1.0"
                while True:
                    idx = self.html_widget.search(plain, idx, tk.END)
                    if not idx:
                        break
                    line_start = self.html_widget.index(f"{idx} linestart")
                    line_end   = self.html_widget.index(f"{idx} lineend")
                    if self.html_widget.get(line_start, line_end) == plain:
                        self.html_widget.see(idx)
                        # see() does the minimum scroll to make idx visible,
                        # which often lands it in the centre.  Nudge it near
                        # the top (2 lines of context above) so it feels like
                        # a normal "jump to heading".
                        self.html_widget.update_idletasks()
                        target_line = int(self.html_widget.index(idx).split('.')[0])
                        top_line    = int(self.html_widget.index("@0,0").split('.')[0])
                        scroll_by   = (target_line - top_line) - 2
                        if scroll_by > 0:
                            self.html_widget.yview_scroll(scroll_by, "units")
                        break
                    idx = self.html_widget.index(f"{idx} +1c")
                return

    @staticmethod
    def _make_slug(text):
        """GitHub-style heading slug: lowercase, punctuation stripped, whitespace collapsed to hyphens."""
        slug = text.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        return slug

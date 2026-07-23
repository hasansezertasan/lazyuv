"""Cache panel: uv cache location, size (on demand), and clean/prune hints."""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import Static


class CachePanel(Static):
    BORDER_TITLE = "Cache"

    def __init__(self) -> None:
        super().__init__(id="cache")

    def show(self, cache_dir: str | None, size: str | None) -> None:
        """Render the cache dir and size. `size` None -> not computed yet.

        `size` is a display string ("calculating…", a formatted size, or "—") the
        app supplies; the panel itself never walks the filesystem.
        """
        if not cache_dir:
            self.update("Cache location unknown.")
            return
        self.update(
            f"[b]Cache[/b]\n"
            f"dir:   {escape(cache_dir)}\n"
            f"size:  {escape(size) if size else '— (press z)'}\n"
            f"\nc clean · P prune"
        )

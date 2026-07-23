"""lazyuv - a terminal UI for uv project workflows."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lazyuv")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0"

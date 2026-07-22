# lazyuv

A keyboard-driven terminal UI for the [`uv`](https://docs.astral.sh/uv/) project
workflow — view dependencies, add/remove them, sync/lock, and run scripts without
leaving the terminal. In the spirit of `lazygit`.

## Install

lazyuv is not on PyPI yet, so install it from a local checkout:

```bash
git clone https://github.com/hasansezertasan/lazyuv
uv tool install ./lazyuv
```

Once published, this becomes `uv tool install lazyuv` (see `ROADMAP.md`).

Requires Python 3.14+ (installed automatically in lazyuv's isolated tool
environment) and `uv` on your PATH.

## Usage

Run inside any uv project directory:

```bash
lazyuv
```

## Keybindings

| Key            | Action                          |
|----------------|---------------------------------|
| `j`/`k`, arrows| Navigate within a panel         |
| `Tab`          | Cycle panel focus               |
| `a`            | Add dependencies                |
| `d`            | Remove selected dependency      |
| `s`            | Sync                            |
| `l`            | Lock                            |
| `r`            | Run selected script             |
| `/`            | Filter dependencies             |
| `?`            | Help                            |
| `q`            | Quit                            |

## Development

```bash
uv sync
uv run pytest
uv run lazyuv
```

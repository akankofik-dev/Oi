"""Shared CLI styling helpers — colors, symbols, banner, loading indicators.

All styling goes through :func:`click.style`, which automatically disables
colors when stdout is not a TTY or when ``NO_COLOR`` is set, so output stays
clean in pipes, logs, and CI. The ``--json`` code paths must never call these
helpers — JSON output stays machine-readable.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import threading
import time

import click

# Minimal, professional symbols. ✓/✗/⚠ are already used elsewhere in the CLI
# (see main.py UTF-8 note) and render fine on all supported terminals.
CHECK = "\u2713"  # ✓
CROSS = "\u2717"  # ✗
WARN = "\u26a0"  # ⚠
ARROW = "\u2192"  # →


# ---------------------------------------------------------------------------
# Elegant color palette
# ---------------------------------------------------------------------------
#
# Muted, sophisticated tones inspired by Vercel / Linear / Stripe — never
# the loud default ANSI brights. Colors are xterm 256-palette indices,
# which click.style renders natively (``38;5;{n}``); NO_COLOR / non-TTY
# handling is automatic via click. The palette stays readable on BOTH
# dark and light backgrounds: no neon, no washed-out pastels.
#
# (Hex strings are NOT used: click.style does not accept them — it takes
# named colors, 0-255 palette ints, or (r, g, b) tuples.)
#
# Approximate hex shown for reference:
ELEGANT = {
    "success": 108,  # sage green      #87af87 — calm, confident
    "error": 131,  # terracotta        #af5f5f — serious, not alarming
    "active": 67,  # steel blue        #5f87af — focused, trustworthy
    "warning": 179,  # muted amber     #d7af5f — caution without noise
    "info": 103,  # cool gray          #8787af — quiet secondary info
    "teal": 73,  # muted teal          #5fafaf — gateway accent
    "mauve": 139,  # muted mauve       #af87af — memory accent
}

_NAMED_FALLBACK = {
    "success": "green",
    "error": "red",
    "active": "blue",
    "warning": "yellow",
    "info": "white",
    "teal": "cyan",
    "mauve": "magenta",
}


def _supports_256color() -> bool:
    """Best-effort 256-color check; conservative on dumb terminals."""
    return os.environ.get("TERM", "") != "dumb"


def _fg(role: str):
    """Return the elegant foreground for *role*.

    A 256-palette index on capable terminals, the closest named ANSI
    color on dumb terminals. Never emits color on non-TTY / NO_COLOR —
    click.style handles that automatically.
    """
    if _supports_256color():
        return ELEGANT.get(role, ELEGANT["info"])
    return _NAMED_FALLBACK.get(role, "white")


def fg(role: str):
    """Public alias for the elegant foreground color of *role*.

    Use for custom-styled output that the ``success``/``error``/``info``/
    ``warning`` helpers don't cover (e.g. highlighted URLs, banners).
    """
    return _fg(role)


def success(text: str) -> str:
    """Style text as a success message (sage green)."""
    return click.style(f"{CHECK} {text}", fg=_fg("success"))


def error(text: str) -> str:
    """Style text as an error message (terracotta)."""
    return click.style(f"{CROSS} {text}", fg=_fg("error"))


def info(text: str) -> str:
    """Style text as informational (cool gray)."""
    return click.style(text, fg=_fg("info"))


def warning(text: str) -> str:
    """Style text as a warning (muted amber)."""
    return click.style(f"{WARN} {text}", fg=_fg("warning"))


def highlight(text: str) -> str:
    """Bold text for emphasis (labels, key names)."""
    return click.style(text, bold=True)


def dim(text: str) -> str:
    """Dimmed text for secondary info (hints, paths)."""
    return click.style(text, dim=True)


def echo_success(text: str) -> None:
    """Print a green success line to stdout."""
    click.echo(success(text))


def echo_error(text: str) -> None:
    """Print a red error line to stderr."""
    click.echo(error(text), err=True)


def echo_info(text: str) -> None:
    """Print a cyan info line to stdout."""
    click.echo(info(text))


def echo_warning(text: str) -> None:
    """Print a yellow warning line to stdout."""
    click.echo(warning(text))


_OI_BANNER = r"""
 ██████╗ ██╗
██╔═══██╗██║
██║   ██║██║
██║   ██║██║
╚██████╔╝██║
 ╚═════╝ ╚═╝
""".rstrip("\n")


def banner() -> str:
    """Return the Oi ASCII banner (styled, color-safe)."""
    return click.style(_OI_BANNER, fg=_fg("active"), bold=True)


def echo_banner() -> None:
    """Print the Oi ASCII banner to stdout."""
    click.echo(banner())


# ---------------------------------------------------------------------------
# Loading indicators
# ---------------------------------------------------------------------------

#: Width of the long loading/progress bar, in characters.
BAR_WIDTH = 40

_FILL_CHAR = "\u2588"  # █ FULL BLOCK
_EMPTY_CHAR = "\u2591"  # ░ LIGHT SHADE
_ASCII_FILL = "#"
_ASCII_EMPTY = "-"


def supports_unicode() -> bool:
    """Best-effort check whether the terminal can render unicode symbols."""
    for stream in (sys.stderr, sys.stdout):
        enc = getattr(stream, "encoding", None) or ""
        if "utf" in enc.lower():
            return True
    try:
        _FILL_CHAR.encode(getattr(sys.stderr, "encoding", None) or "ascii")
        return True
    except Exception:
        return False


def _bar_chars() -> tuple:
    """Return (fill, empty) characters suited to the current terminal."""
    if supports_unicode():
        return _FILL_CHAR, _EMPTY_CHAR
    return _ASCII_FILL, _ASCII_EMPTY


def _stderr_is_tty() -> bool:
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


def render_bar(fraction, width=BAR_WIDTH, fill_char=None, color=None):
    """Render a long determinate bar, e.g. ``████████████░░░░░░░░  60%``.

    :param fraction: 0.0 to 1.0.
    :param width: bar width in characters.
    :param fill_char: override for the filled character (defaults to the
        terminal-appropriate ``█`` / ``#``).
    :param color: :func:`click.style` foreground color (defaults to the
        elegant sage green; auto-disabled when not a TTY or when
        ``NO_COLOR`` is set).
    """
    fraction = max(0.0, min(1.0, fraction))
    if color is None:
        color = _fg("success")
    fill, empty = _bar_chars()
    if fill_char is not None:
        fill = fill_char
    filled = int(round(fraction * width))
    pct = int(round(fraction * 100))
    bar = fill * filled + empty * (width - filled)
    return click.style("%s %3d%%" % (bar, pct), fg=color)


# ---------------------------------------------------------------------------
# Per-package loading styles
# ---------------------------------------------------------------------------

#: Distinct loading-bar style per package: fill character + elegant color.
#:
#: Each package gets its own look so a user can tell at a glance which
#: component is being installed::
#:
#:     oi          -> █  sage green
#:     oi-browser  -> ▓  steel blue
#:     oi-harness  -> ▒  muted amber
#:     oi-gateway  -> ═  muted teal
#:     oi-memory   -> ─  muted mauve
#:
#: On terminals without unicode support the fill character falls back to
#: ``#`` for every package (colors still differ).
PACKAGE_STYLES = {
    "oi": {"char": "\u2588", "color": _fg("success")},  # █ sage green
    "oi-browser": {"char": "\u2593", "color": _fg("active")},  # ▓ steel blue
    "oi-harness": {"char": "\u2592", "color": _fg("warning")},  # ▒ muted amber
    "oi-gateway": {"char": "\u2550", "color": _fg("teal")},  # ═ muted teal
    "oi-memory": {"char": "\u2500", "color": _fg("mauve")},  # ─ muted mauve
}


def _package_style(package):
    """Return ``(fill_char, color)`` for *package*, with safe fallback.

    Unknown package names fall back to the default style (``█`` green).
    On terminals without unicode support the fill character is always the
    ASCII ``#`` (the color still differs per package).
    """
    style = PACKAGE_STYLES.get(package) or PACKAGE_STYLES["oi"]
    fill_char = style["char"]
    color = style["color"]
    if not supports_unicode():
        fill_char = _ASCII_FILL
    return fill_char, color


class LoadingBar:
    """Long animated loading bar for tasks of unknown duration.

    A smooth 40-character indeterminate bar — a solid block glides back and
    forth while work runs::

        Installing packages ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

    Writes to stderr so stdout stays clean for pipes. When stderr is not a
    TTY (logs, CI, pipes) the animation is skipped and only plain start/done
    lines are printed.

    Example::

        with LoadingBar("Installing packages"):
            do_slow_work()
        # animates on stderr, then prints "✓ Installing packages".
    """

    #: Width of the sliding block, in characters.
    BLOCK_WIDTH = 10

    def __init__(
        self,
        label="",
        interval=0.07,
        width=BAR_WIDTH,
        done_text=None,
        fill_char=None,
        color=None,
    ):
        self.label = label
        self.interval = interval
        self.width = width
        self.done_text = done_text
        if fill_char is None:
            fill_char = _bar_chars()[0]
        if color is None:
            color = _fg("success")
        self.fill_char = fill_char
        self.color = color
        self._stop = threading.Event()
        self._thread = None
        self._animated = _stderr_is_tty()

    def _frames(self):
        _, empty = _bar_chars()
        fill = self.fill_char
        pos = 0
        direction = 1
        while not self._stop.is_set():
            bar = (
                empty * pos
                + fill * self.BLOCK_WIDTH
                + empty * (self.width - pos - self.BLOCK_WIDTH)
            )
            yield click.style(bar, fg=self.color)
            pos += direction
            if pos + self.BLOCK_WIDTH >= self.width:
                direction = -1
            elif pos <= 0:
                direction = 1

    def _run(self):
        stream = sys.stderr
        prefix = "%s " % self.label if self.label else ""
        for frame in self._frames():
            stream.write("\r%s%s" % (prefix, frame))
            stream.flush()
            if self._stop.wait(self.interval):
                break
        # Clear the animated line.
        stream.write("\r" + " " * (len(prefix) + self.width + 2) + "\r")
        stream.flush()

    def start(self):
        """Start the bar animation (no-op if already started)."""
        if self._thread is not None:
            return self
        if not self._animated and self.label:
            click.echo(dim("%s..." % self.label), err=True)
        if self._animated:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def stop(self, final_text=None):
        """Stop the bar and optionally print a final styled line."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        text = final_text if final_text is not None else self.done_text
        if text:
            echo_success(text)

    def update(self, label):
        """Change the bar label while it runs."""
        self.label = label

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None and self.label:
            self.stop(self.label)
        else:
            self.stop()
        return False


def loading_bar(label="", **kwargs):
    """Create a :class:`LoadingBar` (intended as a context manager).

    Example::

        with loading_bar("Downloading models"):
            download()
    """
    return LoadingBar(label, **kwargs)


class ProgressBar:
    """Long determinate progress bar: 40 chars, sage green, with percentage.

    Renders in place on stderr::

        Installing packages ████████████████████░░░░░░░░░░░░░░  50%

    Example::

        with ProgressBar("Installing", total=len(items)) as bar:
            for item in items:
                work(item)
                bar.update(1)
    """

    def __init__(self, label="", total=100, width=BAR_WIDTH, fill_char=None, color=None):
        self.label = label
        self.total = max(1, total)
        self.width = width
        if fill_char is None:
            fill_char = _bar_chars()[0]
        if color is None:
            color = _fg("success")
        self.fill_char = fill_char
        self.color = color
        self.current = 0
        self._animated = _stderr_is_tty()
        self._finished = False

    def _draw(self):
        if not self._animated:
            return
        prefix = "%s " % self.label if self.label else ""
        fraction = self.current / self.total
        sys.stderr.write(
            "\r%s%s" % (prefix, render_bar(fraction, self.width, self.fill_char, self.color))
        )
        sys.stderr.flush()

    def update(self, n=1):
        """Advance the bar by *n* steps and redraw."""
        self.current = min(self.total, self.current + n)
        self._draw()

    def set(self, value):
        """Jump the bar to an absolute value and redraw."""
        self.current = max(0, min(self.total, value))
        self._draw()

    def finish(self, final_text=None):
        """Complete the bar at 100% and print an optional success line."""
        if self._finished:
            return
        self._finished = True
        if self._animated:
            prefix = "%s " % self.label if self.label else ""
            sys.stderr.write(
                "\r%s%s\n"
                % (prefix, render_bar(1.0, self.width, self.fill_char, self.color))
            )
            sys.stderr.flush()
        elif self.label:
            click.echo(dim("%s... done" % self.label), err=True)
        if final_text:
            echo_success(final_text)

    def __enter__(self):
        if not self._animated and self.label:
            click.echo(dim("%s..." % self.label), err=True)
        else:
            self._draw()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.finish(self.label or None)
        else:
            if self._animated:
                sys.stderr.write("\n")
                sys.stderr.flush()
            self._finished = True
        return False


def progress(
    iterable=None,
    length: int | None = None,
    label: str = "",
    **kwargs,
):
    """Return a click progress bar (color-safe, hidden when not a TTY).

    Thin wrapper around :func:`click.progressbar` so callers get a single
    import point. Example::

        with progress(items, label="Downloading") as bar:
            for item in bar:
                ...
    """
    return click.progressbar(iterable, length=length, label=label, **kwargs)


def package_loading_bar(package, label="", **kwargs):
    """Create a :class:`LoadingBar` styled for *package*.

    Each package gets its own fill character and color (see
    :data:`PACKAGE_STYLES`), so a user can tell at a glance which
    component is being installed::

        oi          -> █ sage green
        oi-browser  -> ▓ steel blue
        oi-harness  -> ▒ muted amber
        oi-gateway  -> ═ muted teal
        oi-memory   -> ─ muted mauve

    Unknown package names fall back to the default style.

    Example::

        with package_loading_bar("oi-browser", "Installing browser"):
            install_browser()
    """
    fill_char, color = _package_style(package)
    return LoadingBar(label, fill_char=fill_char, color=color, **kwargs)


def package_progress(package, label="", total=100, **kwargs):
    """Create a :class:`ProgressBar` styled for *package*.

    Same per-package styling as :func:`package_loading_bar`, but for
    determinate progress with a percentage::

        with package_progress("oi-browser", "Installing browser", total=5) as bar:
            for step in steps:
                do(step)
                bar.update(1)
    """
    fill_char, color = _package_style(package)
    return ProgressBar(label, total=total, fill_char=fill_char, color=color, **kwargs)


# ---------------------------------------------------------------------------
# Professional step list — Vercel / Docker / GitHub Actions style
# ---------------------------------------------------------------------------
#
# An elegant multi-step checklist with in-place status transitions. While
# work runs the list redraws each step in place on a TTY::
#
#     ✓ Creating virtual environment (1.2s)
#     ● Installing dependencies…
#     ○ Configuring Oi
#
# The active step gently pulses (● → ◉, once every 0.5 s) while work runs —
# a slow, calm animation in the Vercel style. No spinners, no typewriter
# effects::
#
#     ○  pending   — dimmed
#     ●  active    — steel blue, gently pulsing while the step runs (TTY only)
#     ✓  done      — sage green, with elapsed time
#     ✗  failed    — terracotta, with optional detail
#
# On pipes, logs, and CI (stderr not a TTY) the in-place redraw and the
# pulse animation are both skipped and plain sequential
# ``✓ label (1.2s)`` lines are printed instead.

_PENDING = "○"  # U+25CB WHITE CIRCLE
_ACTIVE = "●"  # U+25CF BLACK CIRCLE
_ASCII_PENDING = "o"
_ASCII_ACTIVE = "*"


def _step_symbols():
    """Return ``(pending, active)`` glyphs suited to the current terminal."""
    if supports_unicode():
        return _PENDING, _ACTIVE
    return _ASCII_PENDING, _ASCII_ACTIVE


#: Animation frames for the active step glyph — a gentle pulse. The dot
#: breathes between a solid disc and a fisheye ring while the step runs.
#: Deliberately slow (one frame every 0.5 s) to stay professional.
_ACTIVE_FRAMES = ("\u25cf", "\u25c9")  # ● BLACK CIRCLE, ◉ FISHEYE
_ASCII_ACTIVE_FRAMES = ("*", "o")

#: Seconds between active-step animation frames.
_ANIM_INTERVAL = 0.5


def _active_frames():
    """Return the active-step animation frames for the current terminal."""
    if supports_unicode():
        return _ACTIVE_FRAMES
    return _ASCII_ACTIVE_FRAMES


class StepList:
    """Professional step checklist with live in-place status updates.

    Steps transition ``○ → ● → ✓`` (or ``✗`` on failure) with per-step
    timing, Vercel-CLI style. While a step runs its dot gently pulses
    (``● → ◉``, once every 0.5 s, TTY only). Writes to stderr so stdout
    stays clean for pipes. Steps may be declared up front or added on
    the fly.

    Example::

        with step_list("Setting up the Oi environment") as steps:
            steps.run("Creating virtual environment", create_venv)
            steps.run("Installing dependencies", install_deps)
            steps.run("Configuring Oi", configure)

    With steps known up front::

        with step_list("Setup", steps=["Venv", "Deps", "Config"]) as steps:
            steps.run("Venv", create_venv)
    """

    def __init__(self, title="", steps=()):
        self.title = title
        self._steps = [
            {"label": label, "state": "pending", "elapsed": 0.0, "detail": ""}
            for label in steps
        ]
        self._animated = _stderr_is_tty()
        self._started = False
        self._total_start = None
        # Active-step pulse animation state (TTY only; daemon thread).
        self._anim_lock = threading.Lock()
        self._anim_stop = threading.Event()
        self._anim_thread = None
        self._anim_index = None
        self._frame = 0

    # -- lifecycle ------------------------------------------------------
    def start(self):
        """Print the title and the pending step list (TTY only)."""
        if self._started:
            return self
        self._started = True
        self._total_start = time.monotonic()
        if self.title:
            click.echo(dim(self.title), err=True)
        if self._animated:
            for step in self._steps:
                sys.stderr.write(self._render_line(step) + "\n")
            sys.stderr.flush()
        return self

    def finish(self, done_text=None):
        """Print a subtle summary line with the total elapsed time."""
        if not self._started:
            return
        self._stop_animation()
        total = (
            time.monotonic() - self._total_start if self._total_start else 0.0
        )
        text = done_text or "Done in %.1fs" % total
        if self._animated:
            click.echo("", err=True)
        click.echo(dim(text), err=True)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.finish()
        else:
            self._stop_animation()
            self._mark_active_failed()
            sys.stderr.write("\n")
            sys.stderr.flush()
        return False

    # -- step management -------------------------------------------------
    def _index_of(self, label):
        for i, step in enumerate(self._steps):
            if step["label"] == label:
                return i
        return None

    def _ensure(self, label):
        """Return the index of *label*, appending a pending step if new."""
        index = self._index_of(label)
        if index is None:
            self._steps.append(
                {"label": label, "state": "pending", "elapsed": 0.0, "detail": ""}
            )
            index = len(self._steps) - 1
            if self._animated and self._started:
                sys.stderr.write(
                    self._render_line(self._steps[index]) + "\n"
                )
                sys.stderr.flush()
        return index

    def _render_line(self, step):
        """Render one step line for the current terminal."""
        label = step["label"]
        pending_glyph, _ = _step_symbols()
        state = step["state"]
        if state == "pending":
            return click.style("  %s %s" % (pending_glyph, label), dim=True)
        if state == "active":
            return self._render_active_line(step)
        if state == "done":
            line = "  " + click.style("%s %s" % (CHECK, label), fg=_fg("success"))
            return line + click.style(" (%.1fs)" % step["elapsed"], dim=True)
        # failed
        line = "  " + click.style("%s %s" % (CROSS, label), fg=_fg("error"))
        if step["detail"]:
            line += click.style(" — %s" % step["detail"], fg=_fg("error"))
        return line

    def _render_active_line(self, step, glyph=None):
        """Render the active step line, optionally with an animation glyph."""
        if glyph is None:
            _, glyph = _step_symbols()
        return "  " + click.style("%s %s" % (glyph, step["label"]), fg=_fg("active"))

    def _draw_line_at(self, index, text):
        """Write *text* over the step line at *index*.

        The caller must hold ``self._anim_lock`` so the pulse thread and
        state transitions never interleave their stderr writes.
        """
        up = len(self._steps) - 1 - index
        stream = sys.stderr
        if up > 0:
            stream.write("\x1b[%dA" % up)
        stream.write("\r\x1b[K" + text)
        if up > 0:
            stream.write("\x1b[%dB" % up)
        stream.flush()

    def _redraw(self, index):
        """Redraw step *index* in place (TTY only)."""
        if not self._animated or not self._started:
            return
        with self._anim_lock:
            self._draw_line_at(index, self._render_line(self._steps[index]))

    # -- active-step pulse animation ------------------------------------
    def _start_animation(self, index):
        """Start pulsing the active glyph on step *index* (TTY only)."""
        self._stop_animation()
        if not self._animated or not self._started:
            return
        self._anim_index = index
        self._frame = 0
        self._anim_stop.clear()
        self._anim_thread = threading.Thread(
            target=self._animate_loop, daemon=True
        )
        self._anim_thread.start()

    def _stop_animation(self):
        """Stop the pulse thread (no-op if it is not running).

        Never called from the animation thread itself, so ``join()``
        cannot deadlock.
        """
        thread = self._anim_thread
        if thread is None:
            return
        self._anim_thread = None
        self._anim_index = None
        self._anim_stop.set()
        thread.join()

    def _animate_loop(self):
        """Pulse the active step glyph until stopped."""
        frames = _active_frames()
        while not self._anim_stop.wait(_ANIM_INTERVAL):
            with self._anim_lock:
                index = self._anim_index
                if index is None or index >= len(self._steps):
                    break
                step = self._steps[index]
                if step["state"] != "active":
                    break
                self._frame = (self._frame + 1) % len(frames)
                self._draw_line_at(
                    index, self._render_active_line(step, frames[self._frame])
                )

    def _plain_done_line(self, step):
        mark = CHECK if step["state"] == "done" else CROSS
        text = "%s %s (%.1fs)" % (mark, step["label"], step["elapsed"])
        if step["state"] == "failed" and step["detail"]:
            text += " — %s" % step["detail"]
        click.echo(text, err=True)

    # -- public transitions ----------------------------------------------
    def begin(self, label):
        """Mark *label* as the active step."""
        if not self._started:
            self.start()
        index = self._ensure(label)
        self._steps[index]["state"] = "active"
        self._steps[index]["_start"] = time.monotonic()
        self._redraw(index)
        self._start_animation(index)
        return self

    def succeed(self, label, detail=""):
        """Mark *label* done and print its elapsed time."""
        self._stop_animation()
        index = self._ensure(label)
        step = self._steps[index]
        started = step.pop("_start", None)
        step["state"] = "done"
        step["elapsed"] = (
            time.monotonic() - started if started else 0.0
        )
        step["detail"] = detail
        if self._animated:
            self._redraw(index)
        else:
            self._plain_done_line(step)
        return self

    def fail(self, label, detail=""):
        """Mark *label* failed with an optional reason."""
        self._stop_animation()
        index = self._ensure(label)
        step = self._steps[index]
        started = step.pop("_start", None)
        step["state"] = "failed"
        step["elapsed"] = (
            time.monotonic() - started if started else 0.0
        )
        step["detail"] = detail
        if self._animated:
            self._redraw(index)
        else:
            self._plain_done_line(step)
        return self

    def _mark_active_failed(self):
        """Mark any still-active step as failed (used on exceptions)."""
        for step in self._steps:
            if step["state"] == "active":
                step["state"] = "failed"
                started = step.pop("_start", None)
                step["elapsed"] = (
                    time.monotonic() - started if started else 0.0
                )
                if self._animated:
                    self._redraw(self._steps.index(step))
                else:
                    self._plain_done_line(step)

    def run(self, label, fn=None):
        """Run ``fn()`` as step *label* with ○ → ● → ✓ transitions.

        :param label: step label (appended if not declared up front).
        :param fn: zero-arg callable performing the step; ``None`` marks
            the step done immediately.
        :returns: whatever ``fn()`` returns.
        :raises: any exception from ``fn()`` — the step is marked ``✗``
            before the exception propagates.
        """
        self.begin(label)
        try:
            result = fn() if fn is not None else None
        except Exception as exc:
            self.fail(label, str(exc) or exc.__class__.__name__)
            raise
        self.succeed(label)
        return result


def step_list(title="", steps=()):
    """Create a :class:`StepList` (intended as a context manager).

    The professional loader for environment setup — a Vercel-style
    checklist with in-place ○/●/✓/✗ transitions and per-step timing::

        with step_list("Setting up the Oi environment") as steps:
            steps.run("Creating virtual environment", create_venv)
            steps.run("Installing dependencies", install_deps)
            steps.run("Configuring Oi", configure)
    """
    return StepList(title, steps)


@contextlib.contextmanager
def captured():
    """Capture noisy stdout/stderr (e.g. pip output) into memory.

    Use around the *noisy work only* — ``begin`` / ``succeed`` / ``fail``
    must stay outside so the checklist still renders on the real stderr::

        with step_list("Installing") as steps:
            steps.begin("oi")
            try:
                with captured():
                    install_oi()
            except Exception as exc:
                steps.fail("oi", "install failed")
                raise
            steps.succeed("oi")

    On success the captured output is discarded. On exception the caller
    should print a short, simple error message instead of the raw log.
    """
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        yield buf_out, buf_err


# ---------------------------------------------------------------------------
# Per-package logos
# ---------------------------------------------------------------------------
#
# A distinct ASCII logo per package — shown when installing or working with
# that component so the user can tell at a glance which package is in play.
# All logos share the same box-drawing aesthetic as the main Oi banner,
# stay within 5 lines, and use the package's elegant accent color
# (matching :data:`PACKAGE_STYLES`).

#: Raw logo art per package (leading newline stripped at definition time).
#: ``oi`` intentionally has no entry here — it reuses the main Oi banner.
_PACKAGE_LOGO_ART = {
    # Browser window: title bar with traffic lights + address bar.
    "oi-browser": r"""
╭─────────────╮
│ ● ● ●       │
├─────────────┤
│   ───────   │
╰─────────────╯
""".lstrip("\n").rstrip("\n"),
    # Layered stack: the harness orchestrates stacked agent layers.
    "oi-harness": r"""
╔═════════════╗
║ ▓▓▓▓▓▓▓▓▓▓▓ ║
╠═════════════╣
║ ▒▒▒▒▒▒▒▒▒▒▒ ║
╚═════════════╝
""".lstrip("\n").rstrip("\n"),
    # Portal arch with a through-arrow: the gateway between worlds.
    "oi-gateway": r"""
 ╭─────────╮
 │         │
 │    →    │
 ╰─────────╯
""".lstrip("\n").rstrip("\n"),
    # Memory module: shaded chip.
    "oi-memory": r"""
 ╭─────────╮
 │ ▓█▓█▓█▓ │
 │ ░▒░▒░▒░ │
 ╰─────────╯
""".lstrip("\n").rstrip("\n"),
}

#: Rocket logo for "other" / unknown packages.
_ROCKET_LOGO = "🚀"
_ROCKET_LOGO_ASCII = r"""
    ^
   / \
  / • \
  |   |
 /|   |\
   \ /
    v
""".lstrip("\n").rstrip("\n")

#: Elegant color role per package logo (matches PACKAGE_STYLES accents).
_PACKAGE_LOGO_COLORS = {
    "oi-browser": "active",  # steel blue — like its ▓ loading bar
    "oi-harness": "warning",  # muted amber — like its ▒ loading bar
    "oi-gateway": "teal",  # muted teal — like its ═ loading bar
    "oi-memory": "mauve",  # muted mauve — like its ─ loading bar
}


def package_logo(package: str) -> str:
    """Return the styled ASCII logo for *package*.

    ``oi`` returns the main Oi banner unchanged; every other known
    package returns its own distinct logo in its elegant accent color.
    Unknown package names fall back to the rocket logo.

    Example::

        click.echo(package_logo("oi-browser"))
    """
    if package == "oi":
        return banner()
    if package not in _PACKAGE_LOGO_ART:
        rocket = _ROCKET_LOGO if supports_unicode() else _ROCKET_LOGO_ASCII
        return click.style(rocket, fg=_fg("active"), bold=True)
    role = _PACKAGE_LOGO_COLORS.get(package, "active")
    return click.style(_PACKAGE_LOGO_ART[package], fg=_fg(role), bold=True)


def echo_package_logo(package: str) -> None:
    """Print the ASCII logo for *package* to stdout."""
    click.echo(package_logo(package))

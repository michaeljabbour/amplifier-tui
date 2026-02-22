"""Reactive status footer for Amplifier TUI.

Adapted from claudechic's StatusFooter — provides a self-contained
composite widget with reactive properties for session name, model,
state, branch, and context usage.
"""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult, RenderResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static
from rich.text import Text


# Default context window estimate (200k tokens for Claude)
DEFAULT_MAX_CONTEXT = 200_000


async def _get_git_branch(cwd: str | None = None) -> str:
    """Get current git branch name (async)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "--show-current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1)
        return stdout.decode().strip() or "detached"
    except Exception:
        return ""


class ContextBar(Static):
    """Display context usage as a compact progress bar.

    Shows token usage as a 10-char bar that changes color as usage
    increases: dim -> warning -> error.
    """

    tokens = reactive(0)
    max_tokens = reactive(DEFAULT_MAX_CONTEXT)

    def render(self) -> RenderResult:
        pct = min(self.tokens / self.max_tokens, 1.0) if self.max_tokens else 0
        if pct == 0:
            return Text("")
        bar_width = 8
        filled = int(pct * bar_width)
        # Color tiers: low -> warning -> error
        if pct < 0.5:
            fill_color, text_color = "#666666", "white"
            empty_color = "#333333"
        elif pct < 0.8:
            fill_color, text_color = "#aaaa00", "black"
            empty_color = "#333333"
        else:
            fill_color, text_color = "#cc3333", "white"
            empty_color = "#333333"
        # Build the bar with centered percentage
        pct_str = f"{pct * 100:.0f}%"
        start = (bar_width - len(pct_str)) // 2
        result = Text()
        for i in range(bar_width):
            bg = fill_color if i < filled else empty_color
            if start <= i < start + len(pct_str):
                fg = text_color if i < filled else "white"
                result.append(pct_str[i - start], style=f"{fg} on {bg}")
            else:
                result.append(" ", style=f"on {bg}")
        return result


class StatusFooter(Static):
    """Reactive footer showing session, model, state, git branch, and context usage.

    Uses Textual reactive properties: setting ``footer.model = "..."``
    auto-triggers ``watch_model()`` to update the corresponding label.
    """

    can_focus = False

    session_name = reactive("")
    tab_info = reactive("")
    model = reactive("")
    state = reactive("Ready")
    branch = reactive("")
    word_count = reactive("")
    scroll_mode = reactive("")
    system_info = reactive("")

    async def on_mount(self) -> None:
        self.branch = await _get_git_branch()

    async def refresh_branch(self, cwd: str | None = None) -> None:
        """Update branch from given directory (async)."""
        self.branch = await _get_git_branch(cwd)

    def compose(self) -> ComposeResult:
        # All widget IDs match the original status bar so existing
        # ``self.query_one("#status-*", Static)`` call sites keep working.
        with Horizontal(id="footer-content"):
            yield Static("No session", id="status-session", classes="footer-label")
            yield Static("", id="status-tabs", classes="footer-label")
            yield Static("Ready", id="status-state", classes="footer-label")
            yield Static("", id="status-stash", classes="footer-label")
            yield Static("", id="status-vim", classes="footer-label")
            yield Static("", id="status-ml", classes="footer-label")
            yield Static("", id="status-system", classes="footer-label")
            yield Static("", id="status-mode", classes="footer-label")
            yield Static("", id="footer-spacer")
            yield Static("\u2195 ON", id="status-scroll", classes="footer-label")
            yield Static("0 words", id="status-wordcount", classes="footer-label")
            yield Static("", id="status-context", classes="footer-label")
            yield ContextBar(id="context-bar")
            yield Static("", id="status-model", classes="footer-label")
            yield Static("", id="branch-label", classes="footer-label")

    # -- Reactive watchers: auto-update labels when properties change --

    def watch_session_name(self, value: str) -> None:
        if label := self.query_one_optional("#status-session", Static):
            label.update(f"Session: {value}" if value else "No session")

    def watch_tab_info(self, value: str) -> None:
        if label := self.query_one_optional("#status-tabs", Static):
            label.update(value)

    def watch_model(self, value: str) -> None:
        if label := self.query_one_optional("#status-model", Static):
            label.update(value if value else "")

    def watch_state(self, value: str) -> None:
        if label := self.query_one_optional("#status-state", Static):
            label.update(value)

    def watch_branch(self, value: str) -> None:
        if label := self.query_one_optional("#branch-label", Static):
            label.update(f"branch: {value}" if value else "")

    def watch_word_count(self, value: str) -> None:
        if label := self.query_one_optional("#status-wordcount", Static):
            label.update(value)

    def watch_scroll_mode(self, value: str) -> None:
        # This can be used for the scroll indicator if needed
        pass

    def watch_system_info(self, value: str) -> None:
        if label := self.query_one_optional("#status-system", Static):
            label.update(value)

    def update_context(
        self, tokens: int, max_tokens: int = DEFAULT_MAX_CONTEXT
    ) -> None:
        """Update the context bar with current token usage."""
        if bar := self.query_one_optional("#context-bar", ContextBar):
            bar.tokens = tokens
            bar.max_tokens = max_tokens

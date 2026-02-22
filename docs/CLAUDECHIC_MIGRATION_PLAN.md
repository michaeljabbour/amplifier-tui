# Amplifier TUI: Claudechic UI Migration Plan

> Make amplifier-tui's visual experience match claudechic's polished, information-dense TUI.

## Status Snapshot (pre-migration)

| Dimension | amplifier-tui (current) | claudechic (target) |
|---|---|---|
| Textual version | `>=7.4.0` | `>=7.4.0` |
| Streaming pipeline | `on_stream` callbacks via `LocalBridge` | `claude-agent-sdk` hooks |
| Text rendering | `Static` + manual `Markdown(text)` per block | `ChatMessage` with `MarkdownStream` + debouncing |
| Thinking indicator | `ProcessingIndicator(Static)` stub, no animation | `Spinner` (shared timer, braille frames, 10 FPS) |
| Scroll container | `ScrollableContainer` (Textual built-in) | `AutoHideScroll` (smart tailing, 1px scrollbar) |
| Tool widgets | Inline `Static` text in collapsible | `ToolUseWidget` (spinner overlay, lazy DiffWidget, formatted headers) |
| Turn collapsing | None (all turns rendered fully) | `CollapsedTurn` (lazy, `RECENT_TURNS_FULL=3`) |
| Layout | LEFT sidebar (sessions, 36ch) + chat + hidden RIGHT panels | Centered chat (max 100ch) + RIGHT sidebar (28ch) + responsive breakpoints |
| Responsive | None | 3 breakpoints: `>=140` centered+sidebar, `110-139` left+sidebar, `<110` hamburger |
| Already ported | `QuietCollapsible`, `BaseToolWidget`, `StatusFooter`, left-border CSS | (origin) |

---

## 1. Architecture Decision

**Option A: Keep `on_stream` callbacks, improve widgets and CSS.**

### Justification

The `on_stream` callback system already delivers the exact same events as Amplifier hooks (`content_block:start/delta/end`, `tool:pre/post`, `execution:start/end`, `llm:response`). The `SharedAppBase._wire_streaming_callbacks()` method in `core/app_base.py` provides clean throttling (50ms), accumulated text tracking, tool counting, agent tracker integration, and recipe tracker integration -- all working today.

Replacing this with Amplifier hooks (Option B) would mean:
- Rewriting `session_manager.py` to inject `HookHandler` instances instead of using `BridgeConfig.on_stream`
- Risking breakage in the `LocalBridge` <-> kernel interface (the bridge currently owns the `on_stream` dispatch)
- Gaining zero new events (the bridge already forwards everything the kernel emits)
- Adding complexity to debug (hooks go through the coordinator; `on_stream` is a direct callback)

Option C (hybrid) is unnecessary because there are no "missing events" -- approvals, cancel, and display concerns are already handled at the app layer via `session_manager` methods.

**Decision: Option A. The streaming pipeline is not the problem. The widgets and layout are.**

### What changes and what doesn't

| Layer | Changes? | Notes |
|---|---|---|
| `core/session_manager.py` | **No** | Streaming callbacks stay as-is |
| `core/app_base.py` | **No** | `_wire_streaming_callbacks()` stays as-is |
| `app.py` streaming methods | **Yes** | `_begin_streaming_block`, `_update_streaming_content`, `_finalize_streaming_block` rewritten to use new widgets |
| `app.py` compose | **Yes** | Layout restructured for centered chat + right sidebar |
| `widgets/` | **Yes** | Major: new primitives, new content widgets, restructured directory |
| `styles.tcss` | **Yes** | Significant CSS additions for new layout and widgets |

---

## 2. Textual Upgrade Assessment

**No upgrade needed.** Both projects pin `textual>=7.4.0`. The amplifier-tui `pyproject.toml` already specifies this version. All Textual APIs used by claudechic (`MarkdownStream`, `Markdown.get_stream()`, `Theme` system, `layers`, `call_later`, `set_timer`, `_layout_cache`, `_set_dirty`) are available.

The only Textual feature to verify is `Markdown.get_stream()` -- confirm it exists in the installed version:

```python
from textual.widgets import Markdown
assert hasattr(Markdown, "get_stream"), "Need Textual with MarkdownStream support"
```

If this fails, bump to `textual>=1.0.0` (MarkdownStream was added in Textual 1.x). This is the only potential blocker.

---

## 3. Phase 0: Foundation (Primitives)

> Build the reusable building blocks that all later phases depend on.

### Dependencies
- None (standalone primitives)

### Complexity: **S** (~250 lines total)

### Files to create

#### `amplifier_tui/widgets/primitives/__init__.py`

```python
from .spinner import Spinner
from .scroll import AutoHideScroll

__all__ = ["Spinner", "AutoHideScroll"]
```

#### `amplifier_tui/widgets/primitives/spinner.py`

Port claudechic's `Spinner` with shared class-level timer.

```python
class Spinner(Static):
    """Animated braille spinner. All instances share one timer."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _instances: set[Spinner] = set()
    _frame: int = 0
    _timer = None

    def __init__(self, text: str = "") -> None: ...
    def render(self) -> str: ...            # Return FRAMES[_frame] + text
    def on_mount(self) -> None: ...         # Register + start shared timer (10 FPS)
    def on_unmount(self) -> None: ...       # Unregister + stop if last
    @staticmethod
    def _tick_all() -> None: ...            # Advance frame, refresh visible only
```

Key detail: Use optimized repaint (`_layout_cache.clear()` + `_set_dirty()`) with `refresh(layout=False)` fallback, exactly as claudechic does. This avoids CSS recalculation per frame.

#### `amplifier_tui/widgets/primitives/scroll.py`

Port claudechic's `AutoHideScroll` with smart tailing.

```python
class AutoHideScroll(VerticalScroll):
    """VerticalScroll with 1px scrollbar and smart tailing."""

    DEFAULT_CSS = "AutoHideScroll { scrollbar-size-vertical: 1; }"

    def __init__(self, *args, **kwargs) -> None: ...
    def _is_near_bottom(self) -> bool: ...          # scroll_y >= max_scroll_y - 50
    def _user_scrolled_up(self) -> None: ...        # Disable tailing
    def _user_scrolled_down(self) -> None: ...      # Re-enable if at bottom
    def action_scroll_up(self) -> None: ...         # Override + track
    def action_scroll_down(self) -> None: ...       # Override + track
    def action_page_up(self) -> None: ...           # Override + track
    def action_page_down(self) -> None: ...         # Override + track
    def _on_mouse_scroll_up(self, event) -> None: ...   # Override + track
    def _on_mouse_scroll_down(self, event) -> None: ... # Override + track
    def _on_scroll_to(self, message: ScrollTo) -> None: ...  # Scrollbar drag
    def scroll_if_tailing(self) -> None: ...        # Scroll to end if tailing
```

### Files to modify

#### `amplifier_tui/widgets/__init__.py`

Add exports for new primitives:

```python
from .primitives import Spinner, AutoHideScroll
```

### Success criteria

- [ ] `Spinner` animates at 10 FPS with braille frames
- [ ] Multiple `Spinner` instances share a single timer
- [ ] `AutoHideScroll` auto-scrolls on new content when user is at bottom
- [ ] `AutoHideScroll` stops tailing when user scrolls up
- [ ] `AutoHideScroll` resumes tailing when user scrolls back to bottom

---

## 4. Phase 1: Content Widgets

> Replace the simple Static-based message widgets with claudechic's streaming-aware content widgets.

### Dependencies
- Phase 0 (Spinner, AutoHideScroll)

### Complexity: **L** (~600 lines new widgets + ~200 lines app.py edits)

### Files to create

#### `amplifier_tui/widgets/content/__init__.py`

```python
from .message import ChatMessage, ThinkingIndicator
from .tools import ToolUseWidget, TaskWidget
from .collapsed_turn import CollapsedTurn

__all__ = [
    "ChatMessage", "ThinkingIndicator",
    "ToolUseWidget", "TaskWidget",
    "CollapsedTurn",
]
```

#### `amplifier_tui/widgets/content/message.py`

The most important new widget. Port claudechic's `ChatMessage` with `MarkdownStream`.

```python
class ThinkingIndicator(Spinner):
    """Animated spinner shown when agent is thinking."""
    can_focus = False
    DEFAULT_CSS = "ThinkingIndicator { width: auto; height: 1; }"

    def __init__(self, id=None, classes=None) -> None:
        super().__init__("Thinking...")


class ChatMessage(Static):
    """A single chat message with streaming support via MarkdownStream.

    Uses debounced MarkdownStream for efficient incremental rendering.
    """
    can_focus = False
    _DEBOUNCE_INTERVAL = 0.05   # 50ms
    _DEBOUNCE_MAX_CHARS = 200   # Flush immediately above this

    def __init__(self, content: str = "") -> None: ...
    def compose(self) -> ComposeResult: ...         # yield Markdown(initial, id="content")
    def _get_stream(self): ...                      # Lazy Markdown.get_stream()
    def append_content(self, text: str) -> None: ... # Debounced streaming append
    def _flush_pending(self) -> None: ...           # Write buffer to stream
    def flush(self) -> None: ...                    # Final flush + stop stream
    def get_raw_content(self) -> str: ...           # Raw accumulated text
```

**Critical integration point**: The existing `_begin_streaming_block()` in `app.py` creates a `Static` widget and manually updates its content. This must be rewritten to create a `ChatMessage` and call `append_content()` on deltas, then `flush()` on block end. The `_update_streaming_content()` method becomes trivial.

#### `amplifier_tui/widgets/content/tools.py`

Port claudechic's `ToolUseWidget` and `TaskWidget`, adapted for Amplifier's tool data format.

```python
class ToolUseWidget(BaseToolWidget):
    """Collapsible tool display with spinner overlay and formatted content."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict,
        collapsed: bool = False,
        completed: bool = False,
    ) -> None: ...

    def compose(self) -> ComposeResult: ...
        # yield Spinner()               # Overlaid on collapse arrow via CSS layer
        # yield QuietCollapsible(...)    # Header + lazy content

    def set_result(self, result: str) -> None: ...  # Remove spinner, add result content
    def _format_header(self) -> str: ...             # Tool-specific one-line summary
    def _format_input(self) -> str: ...              # Formatted tool input
    def _format_result(self, result: str) -> str: ... # Formatted/truncated result


class TaskWidget(BaseToolWidget):
    """Widget for delegate tool calls showing nested agent activity."""

    def __init__(self, agent_name: str, instruction: str) -> None: ...
    def compose(self) -> ComposeResult: ...
    def set_result(self, result: str, status: str = "completed") -> None: ...
```

**Data format difference**: claudechic receives `ToolUseBlock` objects from `claude-agent-sdk`. Amplifier TUI receives `(name: str, tool_input: dict, result: str)` tuples from `on_stream` callbacks. The `ToolUseWidget` constructor takes the Amplifier format directly.

#### `amplifier_tui/widgets/content/collapsed_turn.py`

Port claudechic's `CollapsedTurn` for memory-efficient history display.

```python
class CollapsedTurn(QuietCollapsible):
    """Collapsed user+assistant turn pair with lazy expansion.

    Shows summary like "fix the bug -> 5 tools" when collapsed.
    Creates full widgets only on first expand via content_factory.
    """
    DEFAULT_CSS = """..."""  # border-left: wide $panel, transparent bg

    def __init__(
        self,
        user_text: str,
        tool_count: int,
        text_count: int,
        widget_factory: Callable[[], list[Widget]],
    ) -> None: ...

    @staticmethod
    def _make_summary(user_text: str, tool_count: int, text_count: int) -> str: ...
```

**Data format difference**: claudechic passes `UserContent`/`AssistantContent` objects. Amplifier TUI will pass primitive data (user text, tool count, text count) since it doesn't have an equivalent Agent model. The `widget_factory` closure captures the original message data.

### Files to modify

#### `amplifier_tui/app.py` -- Streaming display methods (lines ~6560-6700)

Rewrite three methods:

**`_begin_streaming_block(block_type)`** (currently line 6562):
```python
# BEFORE: Creates Static("▍") widget
# AFTER:
def _begin_streaming_block(self, block_type: str) -> None:
    self._remove_processing_indicator()
    chat_view = self._active_chat_view()

    if block_type in ("thinking", "reasoning"):
        indicator = ThinkingIndicator()
        chat_view.mount(indicator)
        self._stream_widget = indicator
        self._stream_container = None
    else:
        widget = ChatMessage()
        widget.add_class("chat-message", "assistant-message")
        chat_view.mount(widget)
        self._scroll_if_auto(widget)
        self._stream_widget = widget
        self._stream_container = None
```

**`_update_streaming_content(block_type, text)`** (currently line 6599):
```python
# BEFORE: Manual Markdown rendering with cursor char, error-prone
# AFTER:
def _update_streaming_content(self, block_type: str, text: str) -> None:
    if not self._stream_widget:
        return
    if isinstance(self._stream_widget, ChatMessage):
        # ChatMessage handles its own debouncing internally
        delta = text[len(self._stream_widget.get_raw_content()):]
        if delta:
            self._stream_widget.append_content(delta)
    # ThinkingIndicator just animates, no text update during stream
    self._scroll_if_auto(self._stream_widget)
```

**`_finalize_streaming_block(block_type, final_text)`** (currently line ~6640):
```python
# BEFORE: Replaces Static content with final Markdown widget
# AFTER:
def _finalize_streaming_block(self, block_type: str, final_text: str) -> None:
    if isinstance(self._stream_widget, ChatMessage):
        self._stream_widget.flush()
    elif isinstance(self._stream_widget, ThinkingIndicator):
        # Replace spinner with collapsible thinking block
        self._stream_widget.remove()
        self._add_thinking_block(final_text)
    self._stream_widget = None
    self._stream_container = None
```

#### `amplifier_tui/app.py` -- Tool display methods

Rewrite `_add_tool_use()` to use the new `ToolUseWidget`:

```python
# BEFORE: Builds inline Static elements in a QuietCollapsible
# AFTER:
def _add_tool_use(self, name: str, tool_input: dict, result: str) -> None:
    chat_view = self._active_chat_view()
    widget = ToolUseWidget(
        tool_name=name,
        tool_input=tool_input,
        collapsed=self._should_collapse_tool(name),
        completed=True,
    )
    widget.set_result(result)
    chat_view.mount(widget)
    self._scroll_if_auto(widget)
```

Rewrite `_on_stream_tool_start` display portion to create a pending `ToolUseWidget`:

```python
# Create widget with spinner (no result yet)
widget = ToolUseWidget(tool_name=name, tool_input=tool_input)
chat_view.mount(widget)
self._pending_tool_widgets[tool_use_id] = widget
```

Then in `_on_stream_tool_end`, find the pending widget and call `set_result()`.

### Success criteria

- [ ] Streaming text renders as formatted Markdown (headings, code, lists) as it arrives
- [ ] No visible cursor character or flashing during streaming
- [ ] Thinking indicator shows animated braille spinner while waiting
- [ ] Tool use widgets show spinner while pending, result when complete
- [ ] `ToolUseWidget` click toggles expand/collapse
- [ ] Tool headers show tool-specific summaries (file path for write, command for bash, etc.)
- [ ] Existing streaming callback pipeline (`on_stream`) works unchanged

---

## 5. Phase 2: Layout Transformation

> Restructure the app layout from "left sidebar + full-width chat" to "centered chat + right sidebar + responsive breakpoints".

### Dependencies
- Phase 0 (AutoHideScroll)
- Phase 1 (ChatMessage, ToolUseWidget -- needed for ChatView)

### Complexity: **L** (layout restructure touches compose, sidebar, ChatView, CSS)

### Files to create

#### `amplifier_tui/widgets/layout/__init__.py`

```python
from .chat_view import ChatView
from .sidebar import Sidebar, HamburgerButton

__all__ = ["ChatView", "Sidebar", "HamburgerButton"]
```

#### `amplifier_tui/widgets/layout/chat_view.py`

New `ChatView` class that owns message rendering and streaming lifecycle.

```python
class ChatView(AutoHideScroll):
    """Scrollable chat view with streaming management and turn collapsing.

    Responsibilities:
    - Rendering message history (with CollapsedTurn for old turns)
    - Tracking pending tool widgets (for live spinner -> result transition)
    - Thinking indicator lifecycle
    - Auto-collapse of old tool widgets
    - Deferred updates when hidden (performance for background tabs)
    """

    # Configuration
    RECENT_TURNS_FULL = 3       # Older turns collapsed
    RECENT_TOOLS_EXPANDED = 2   # Only N most recent tools start expanded
    COLLAPSE_BY_DEFAULT = {"read_file", "glob", "grep", "web_search", "web_fetch"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._current_response: ChatMessage | None = None
        self._pending_tool_widgets: dict[str, ToolUseWidget | TaskWidget] = {}
        self._recent_tools: list[ToolUseWidget | TaskWidget] = []
        self._thinking_indicator: ThinkingIndicator | None = None
        self._needs_rerender: bool = False

    # --- History rendering ---
    def render_history(self, messages: list) -> None: ...
        # Group into turns, collapse old ones, mount_all() for single CSS pass

    def _create_collapsed_turn(self, user_text, tools, texts) -> CollapsedTurn: ...
    def _should_collapse_tool(self, tool_name: str, index: int, total: int) -> bool: ...

    # --- Streaming lifecycle (called from app's stream callbacks) ---
    def begin_text_stream(self) -> ChatMessage: ...
    def begin_thinking(self) -> ThinkingIndicator: ...
    def end_thinking(self, final_text: str) -> None: ...
    def add_tool_pending(self, tool_id: str, name: str, input: dict) -> ToolUseWidget: ...
    def complete_tool(self, tool_id: str, result: str) -> None: ...

    # --- Visibility (for tab switching / background agents) ---
    @property
    def is_hidden(self) -> bool: ...
    def flush_deferred_updates(self) -> None: ...
```

This extracts streaming display logic currently scattered across `app.py` (lines 6560-6700+) into a cohesive widget. The app's `_on_stream_*` methods become thin dispatchers to `ChatView` methods.

#### `amplifier_tui/widgets/layout/sidebar.py`

Unified right sidebar combining current `TodoPanel` + `AgentTreePanel` into claudechic-style sections.

```python
SIDEBAR_MIN_WIDTH = 110        # Terminal must be this wide for sidebar
CENTERED_SIDEBAR_WIDTH = 140   # Wide enough for centered chat + sidebar

class SidebarSection(Widget):
    """Base for sidebar sections with title and auto-hide when empty."""
    DEFAULT_CSS = "..."

    def __init__(self, title: str) -> None: ...
    def compose(self) -> ComposeResult: ...


class AgentSection(SidebarSection):
    """Shows active agents with status indicators."""
    ...

class TodoSection(SidebarSection):
    """Shows current todo list from agent."""
    ...

class Sidebar(Widget):
    """Right sidebar with sections for agents, todos, and activity."""
    DEFAULT_CSS = """
    Sidebar {
        dock: right;
        width: 28;
        border-left: solid $surface-lighten-2;
        background: $surface;
        display: none;
    }
    Sidebar.visible { display: block; }
    Sidebar.overlay {
        layer: above;
        /* Float over content instead of pushing it */
    }
    """

    visible: reactive[bool] = reactive(False)
    overlay: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult: ...
    def watch_visible(self, value: bool) -> None: ...


class HamburgerButton(Static):
    """Sidebar toggle button shown when terminal is too narrow."""
    DEFAULT_CSS = """
    HamburgerButton {
        dock: right;
        width: 3;
        height: 1;
        padding: 0 1;
        display: none;
    }
    HamburgerButton.visible { display: block; }
    HamburgerButton.attention { color: $warning; }
    """

    def on_click(self) -> None: ...  # Toggle sidebar visibility
```

### Files to modify

#### `amplifier_tui/app.py` -- `compose()` (line 543)

Restructure the layout:

```python
# BEFORE:
#   Horizontal(main-container)
#     Vertical(session-sidebar)    <- LEFT, 36ch
#     Vertical(chat-area)          <- full width
#     TodoPanel                    <- RIGHT, hidden
#     AgentTreePanel               <- RIGHT, hidden

# AFTER:
def compose(self) -> ComposeResult:
    with Horizontal(id="main-container"):
        with Vertical(id="session-sidebar"):
            yield Static(" Sessions", id="sidebar-title")
            yield Input(placeholder="Filter sessions...", id="session-filter")
            yield Tree("Sessions", id="session-tree")
        with Vertical(id="chat-area"):
            yield Static("", id="breadcrumb-bar")
            yield TabBar(id="tab-bar")
            yield FindBar(id="find-bar")
            # #main centers the chat column
            with Vertical(id="main"):
                with Vertical(id="chat-column"):
                    yield ChatView(id="chat-view", classes="tab-chat-view")
                    yield ChatInput("", id="chat-input", ...)
                    yield SuggestionBar()
                    yield HistorySearchBar()
            yield HamburgerButton(id="hamburger-btn")
            yield Sidebar(id="sidebar")
        yield StatusFooter(id="status-bar")
```

Key changes:
1. `ScrollableContainer(id="chat-view")` -> `ChatView(id="chat-view")` (AutoHideScroll-based)
2. `#main` container with `align: center top` wraps `#chat-column` (max-width: 100)
3. `TodoPanel` + `AgentTreePanel` -> unified `Sidebar` with sections
4. `HamburgerButton` for narrow terminals
5. `StatusFooter` docked bottom (already works this way)

#### `amplifier_tui/app.py` -- Responsive resize handling

Add terminal width tracking:

```python
def on_resize(self, event: Resize) -> None:
    width = event.size.width
    sidebar = self.query_one("#sidebar", Sidebar)
    hamburger = self.query_one("#hamburger-btn", HamburgerButton)
    main = self.query_one("#main", Vertical)

    if width >= CENTERED_SIDEBAR_WIDTH:
        # Wide: centered chat + inline sidebar
        sidebar.visible = True
        sidebar.overlay = False
        hamburger.remove_class("visible")
        main.remove_class("sidebar-shift")
    elif width >= SIDEBAR_MIN_WIDTH:
        # Medium: left-aligned chat + inline sidebar
        sidebar.visible = True
        sidebar.overlay = False
        hamburger.remove_class("visible")
        main.add_class("sidebar-shift")
    else:
        # Narrow: no sidebar, show hamburger
        sidebar.visible = False
        hamburger.add_class("visible")
```

#### `amplifier_tui/app.py` -- `_active_chat_view()` return type

Update to return `ChatView` instead of generic `ScrollableContainer`:

```python
def _active_chat_view(self) -> ChatView:
    return self.query_one("#chat-view", ChatView)
```

#### `amplifier_tui/styles.tcss` -- Layout CSS additions

```css
/* Centered main area */
#main {
    height: 1fr;
    width: 1fr;
    align: center top;
}

#main.sidebar-shift {
    align: left top;
}

/* Chat column - constrained width, centered in #main */
#chat-column {
    width: 1fr;
    max-width: 100;
    height: 1fr;
    overflow: hidden;
}

/* ChatView replaces ScrollableContainer */
.tab-chat-view {
    layout: stream;
    width: 100%;
    height: 1fr;
    padding: 1 1;
}
```

### Migration of TodoPanel / AgentTreePanel

The existing `TodoPanel` and `AgentTreePanel` widgets don't get deleted -- they become sections within the new `Sidebar`. Their data models (`TodoItem`, `AgentNode`) and update methods stay the same. The `Sidebar` composes them as children:

```python
class Sidebar(Widget):
    def compose(self) -> ComposeResult:
        yield AgentSection(id="sidebar-agents")
        yield TodoSection(id="sidebar-todos")
```

The app's existing `_update_todo_panel()` and `_update_agent_tree_*()` methods continue to work, just targeting sidebar children instead of standalone panels.

### Success criteria

- [ ] Chat content centered in terminal with max-width 100
- [ ] Right sidebar (28ch) shows agents and todos when terminal is wide enough
- [ ] Sidebar disappears and hamburger appears on narrow terminals
- [ ] Sidebar appears as overlay (layer: above) when hamburger is clicked
- [ ] Session sidebar (left) still works for session tree browsing
- [ ] Smart tailing: auto-scroll on new content, stop when user scrolls up
- [ ] Tab switching works with ChatView (deferred rendering for hidden tabs)
- [ ] Existing tab, split-panel, and terminal-panel features still function

---

## 6. Phase 3: Visual Polish

> Bring the visual experience to claudechic quality: CSS refinement, turn collapsing, diff rendering, compact mode.

### Dependencies
- Phase 1 (ChatMessage, ToolUseWidget)
- Phase 2 (ChatView, Sidebar layout)

### Complexity: **M** (CSS work + CollapsedTurn integration + DiffWidget)

### Files to create

#### `amplifier_tui/widgets/content/diff.py`

Inline diff rendering for file write/edit tool results.

```python
class DiffWidget(Static):
    """Renders a unified diff with syntax-highlighted additions/deletions."""

    DEFAULT_CSS = """
    DiffWidget {
        padding: 0 1;
    }
    DiffWidget .diff-add { color: $success; }
    DiffWidget .diff-del { color: $error; }
    DiffWidget .diff-hunk { color: $text-muted; text-style: italic; }
    """

    def __init__(self, diff_text: str) -> None: ...
    def render(self) -> RenderResult: ...  # Rich Text with colored +/- lines
```

### Files to modify

#### `amplifier_tui/styles.tcss` -- Visual refinements

Major CSS additions/changes:

```css
/* 1. Shared block styling (claudechic pattern) */
ChatMessage, BaseToolWidget, ThinkingIndicator, .error-message {
    background: transparent;
    margin: 0 2 1 0;
    padding: 0 2 0 2;
}

/* 2. ChatMessage text cursor */
ChatMessage { pointer: text; }

/* 3. User messages - vibrant, extra spacing */
ChatMessage.user-message {
    border-left: thick $primary;
    margin: 2 0 2 0;
}

/* 4. Assistant messages - softer */
ChatMessage.assistant-message {
    border-left: wide $secondary;
    margin: 1 0 1 0;
}

/* 5. Tool use spinner overlay on collapse arrow */
ToolUseWidget > Spinner {
    layer: above;
    dock: top;
    background: transparent;
}

/* 6. TaskWidget - accent colored border */
TaskWidget {
    border-left: wide $accent;
}

/* 7. CollapsedTurn styling */
CollapsedTurn {
    margin: 0;
    padding: 0;
    border-left: wide $panel;
    background: transparent;
}
CollapsedTurn:hover {
    border-left: wide $panel-lighten-2;
}
CollapsedTurn > CollapsibleTitle {
    padding: 0;
    color: $text-muted;
    background: transparent;
}

/* 8. Markdown polish */
Markdown { padding: 0; margin: 0; }
MarkdownFence { background: $surface; scrollbar-size-horizontal: 1; }
ChatMessage Markdown, ToolUseWidget Markdown { margin-bottom: -1; }

/* 9. Scrollbar styling for scroll containers */
AutoHideScroll {
    scrollbar-background: $surface;
    scrollbar-color: $panel;
    scrollbar-color-hover: $panel-lighten-1;
}

/* 10. Compact mode (height < 20) */
.compact-mode ChatMessage { margin: 0; }
.compact-mode .tool-use { margin: 0; }
```

#### `amplifier_tui/app.py` -- CollapsedTurn integration

Add turn collapsing to the transcript replay method that renders history when resuming sessions or switching tabs:

```python
def _render_history_to_chat_view(self, messages: list, chat_view: ChatView) -> None:
    """Render message history with collapsed old turns."""
    turns = self._group_into_turns(messages)
    collapse_before = max(0, len(turns) - ChatView.RECENT_TURNS_FULL)

    widgets = []
    for i, (user_text, blocks) in enumerate(turns):
        if i < collapse_before:
            tool_count = sum(1 for b in blocks if b["type"] == "tool")
            text_count = sum(1 for b in blocks if b["type"] == "text")
            widgets.append(CollapsedTurn(
                user_text=user_text,
                tool_count=tool_count,
                text_count=text_count,
                widget_factory=lambda u=user_text, b=blocks: self._make_turn_widgets(u, b),
            ))
        else:
            widgets.extend(self._make_turn_widgets(user_text, blocks))

    chat_view.mount_all(widgets)
    chat_view.scroll_end(animate=False)
```

#### `amplifier_tui/widgets/content/tools.py` -- DiffWidget integration

In `ToolUseWidget.set_result()`, detect file edit results and render as `DiffWidget`:

```python
def set_result(self, result: str) -> None:
    # Remove spinner
    if spinner := self.query_one_optional(Spinner):
        spinner.remove()

    # If result looks like a diff, use DiffWidget
    if result.startswith("---") or result.startswith("@@"):
        content_factory = lambda: [DiffWidget(result)]
    else:
        content_factory = lambda: [Markdown(self._format_result(result))]
    # Add to collapsible (lazy if collapsed)
    ...
```

### Success criteria

- [ ] Older turns collapse into single-line summaries with tool/message counts
- [ ] Clicking collapsed turn expands to full widgets (lazy-loaded)
- [ ] File edit results render as colored diffs (green adds, red deletes)
- [ ] Spinner overlays the collapse arrow on pending tool widgets
- [ ] Markdown code blocks render with surface background and thin scrollbar
- [ ] No trailing whitespace/margin after last message in chat
- [ ] Compact mode reduces spacing when terminal height < 20

---

## 7. Phase 4: Advanced Features

> Approval modals, improved agent management, and sidebar attention indicators.

### Dependencies
- Phase 2 (Sidebar, HamburgerButton)
- Phase 3 (Visual polish)

### Complexity: **M** (modal widgets + attention indicators)

### Files to create

#### `amplifier_tui/widgets/modals/__init__.py`

```python
from .approval import ApprovalModal

__all__ = ["ApprovalModal"]
```

#### `amplifier_tui/widgets/modals/approval.py`

Modal overlay for tool approval requests.

```python
class ApprovalModal(Widget):
    """Modal overlay for requesting user approval of tool calls.

    Replaces the current inline approval prompts with a centered modal
    that shows tool details and allow/deny buttons.
    """
    DEFAULT_CSS = """
    ApprovalModal {
        layer: modal;
        width: 100%;
        height: 100%;
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    """

    class Approved(Message):
        def __init__(self, tool_name: str) -> None: ...

    class Denied(Message):
        def __init__(self, tool_name: str, reason: str = "") -> None: ...

    def __init__(self, tool_name: str, tool_input: dict, prompt: str) -> None: ...
    def compose(self) -> ComposeResult: ...
        # Centered panel with tool details + Allow/Deny buttons
    def key_y(self) -> None: ...   # Quick approve
    def key_n(self) -> None: ...   # Quick deny
```

### Files to modify

#### `amplifier_tui/widgets/layout/sidebar.py` -- Attention indicators

Add attention indicator support to `HamburgerButton`:

```python
class HamburgerButton(Static):
    attention: reactive[bool] = reactive(False)

    def watch_attention(self, value: bool) -> None:
        self.set_class(value, "attention")

    def render(self) -> str:
        return "☰" if not self.attention else "☰!"
```

The sidebar sets `attention=True` when an agent needs input (approval pending) while the sidebar is hidden.

#### `amplifier_tui/app.py` -- Approval integration

Wire `ApprovalModal` into the existing approval flow:

```python
async def _handle_approval_request(self, tool_name: str, tool_input: dict, prompt: str):
    modal = ApprovalModal(tool_name, tool_input, prompt)
    self.mount(modal)
    result = await self._wait_for_approval(modal)
    modal.remove()
    return result
```

#### `amplifier_tui/styles.tcss` -- Modal and Screen layers

```css
Screen {
    layers: below above modal;
}
```

### Success criteria

- [ ] Approval requests appear as centered modal overlays
- [ ] `y`/`n` keys work as quick approve/deny in modal
- [ ] Modal shows tool name, formatted input, and context
- [ ] Hamburger button shows attention indicator when sidebar has pending items
- [ ] Agent section in sidebar shows status (running/completed/failed) per agent
- [ ] Todo section updates live as agent creates/completes tasks

---

## 8. Implementation Order and Risk Assessment

### Recommended order

```
Phase 0 (Foundation)  -->  Phase 1 (Content Widgets)  -->  Phase 3 (Visual Polish)
         \                          |
          -------->  Phase 2 (Layout)  -------->  Phase 4 (Advanced)
```

Phases 0 and 1 are safe to land independently -- they add new widgets without changing the layout. Phase 2 is the riskiest because it touches `compose()` and layout CSS.

### Risk matrix

| Phase | Risk | Mitigation |
|---|---|---|
| Phase 0 | **Low** | New files only, no existing code changes |
| Phase 1 | **Medium** | Rewrites streaming display methods; test with `content_block:start/delta/end` events carefully |
| Phase 2 | **High** | Layout restructure can break existing features (tabs, split panel, terminal panel, session sidebar) |
| Phase 3 | **Low** | CSS additions, CollapsedTurn only affects history replay |
| Phase 4 | **Low** | New modal widgets, additive changes |

### Phase 2 risk mitigation

1. **Feature-flag the layout**: Use a CSS class (`claudechic-layout`) to toggle between old and new layout
2. **Preserve all existing IDs**: Keep `#chat-view`, `#chat-input`, `#session-sidebar` etc. so query_one() call sites work
3. **Test tab switching**: The tab system creates/swaps `ScrollableContainer` elements; verify `ChatView` works as a drop-in replacement
4. **Test split panel**: The split panel feature depends on `#chat-split-container` layout; may need to keep this container
5. **Test terminal panel**: The embedded terminal depends on position relative to `#chat-area`

### Estimated effort

| Phase | Estimated lines | Days (solo) |
|---|---|---|
| Phase 0 | ~250 | 0.5 |
| Phase 1 | ~600 + ~200 app.py edits | 2 |
| Phase 2 | ~400 + ~300 app.py/CSS edits | 2 |
| Phase 3 | ~200 + ~300 CSS | 1 |
| Phase 4 | ~300 | 1 |
| **Total** | **~2,550** | **~6.5** |

---

## 9. File Tree After Migration

```
amplifier_tui/
├── widgets/
│   ├── __init__.py              (modified: re-exports)
│   ├── primitives/
│   │   ├── __init__.py          (new)
│   │   ├── spinner.py           (new: Spinner)
│   │   └── scroll.py            (new: AutoHideScroll)
│   ├── content/
│   │   ├── __init__.py          (new)
│   │   ├── message.py           (new: ChatMessage, ThinkingIndicator)
│   │   ├── tools.py             (new: ToolUseWidget, TaskWidget)
│   │   ├── collapsed_turn.py    (new: CollapsedTurn)
│   │   └── diff.py              (new: DiffWidget)
│   ├── layout/
│   │   ├── __init__.py          (new)
│   │   ├── chat_view.py         (new: ChatView)
│   │   └── sidebar.py           (new: Sidebar, HamburgerButton, sections)
│   ├── modals/
│   │   ├── __init__.py          (new)
│   │   └── approval.py          (new: ApprovalModal)
│   │
│   │   # Existing files (kept, some modified)
│   ├── bars.py
│   ├── chat_input.py
│   ├── commands.py
│   ├── datamodels.py
│   ├── indicators.py            (modified: ProcessingIndicator may be removed)
│   ├── messages.py              (deprecated: replaced by content/message.py)
│   ├── panels.py
│   ├── quiet_collapsible.py     (kept as-is)
│   ├── screens.py
│   ├── status_footer.py         (kept as-is)
│   ├── tabs.py
│   ├── terminal.py
│   ├── todo_panel.py            (kept: becomes sidebar section data source)
│   ├── tool_base.py             (kept as-is)
│   └── agent_tree_panel.py      (kept: becomes sidebar section data source)
├── styles.tcss                  (modified: ~200 lines added/changed)
├── app.py                       (modified: compose, streaming methods, resize handler)
├── core/
│   ├── app_base.py              (unchanged)
│   └── session_manager.py       (unchanged)
└── ...
```

---

## 10. Reference: claudechic Source Files -> amplifier-tui Targets

| claudechic file | amplifier-tui target | Status |
|---|---|---|
| `widgets/primitives/spinner.py` | `widgets/primitives/spinner.py` | Phase 0 |
| `widgets/primitives/scroll.py` | `widgets/primitives/scroll.py` | Phase 0 |
| `widgets/primitives/collapsible.py` | `widgets/quiet_collapsible.py` | **Already ported** |
| `widgets/base/tool_base.py` | `widgets/tool_base.py` | **Already ported** |
| `widgets/content/message.py` (ChatMessage) | `widgets/content/message.py` | Phase 1 |
| `widgets/content/message.py` (ThinkingIndicator) | `widgets/content/message.py` | Phase 1 |
| `widgets/content/tools.py` | `widgets/content/tools.py` | Phase 1 |
| `widgets/content/collapsed_turn.py` | `widgets/content/collapsed_turn.py` | Phase 3 |
| `widgets/content/diff.py` | `widgets/content/diff.py` | Phase 3 |
| `widgets/layout/chat_view.py` | `widgets/layout/chat_view.py` | Phase 2 |
| `widgets/layout/sidebar.py` | `widgets/layout/sidebar.py` | Phase 2 |
| `widgets/layout/footer.py` | `widgets/status_footer.py` | **Already adapted** |
| `widgets/layout/indicators.py` (ContextBar) | `widgets/status_footer.py` (ContextBar) | **Already adapted** |
| `widgets/modals/` | `widgets/modals/approval.py` | Phase 4 |
| `theme.py` (CHIC_THEME) | `theme.py` / `preferences.py` | N/A (keep existing 11 themes) |

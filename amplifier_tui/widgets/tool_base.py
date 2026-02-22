"""Base class for tool display widgets.

Ported from claudechic's BaseToolWidget — adapted for amplifier-tui.
"""

from textual.events import Click
from textual.widgets import Static

from .quiet_collapsible import QuietCollapsible


class BaseToolWidget(Static):
    """Base class for tool display widgets with shared styling.

    Provides consistent visual treatment (border, spacing, hover) for
    tool-use blocks, thinking blocks, and similar collapsible containers.

    Visual styles are defined in styles.tcss using the BaseToolWidget
    selector.  Clicking anywhere on the widget toggles the collapsible.
    """

    can_focus = False

    def on_click(self, event: Click) -> None:
        """Toggle collapsible when clicking anywhere on the widget."""
        if event.button != 1:  # Left click only
            return
        if collapsible := self.query_one_optional(QuietCollapsible):
            collapsible.collapsed = not collapsible.collapsed

    def collapse(self) -> None:
        """Collapse this widget's collapsible."""
        if collapsible := self.query_one_optional(QuietCollapsible):
            collapsible.collapsed = True

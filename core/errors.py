"""Errors whose text is already written for the person using the app.

Anything that is NOT a UserFacingError is treated as an internal fault: the user
sees one plain sentence and the real detail goes to the log. That keeps raw API
strings and Python exception names off the screen.
"""

from __future__ import annotations


class UserFacingError(RuntimeError):
    """Raise this when the message is safe and useful to show as-is."""

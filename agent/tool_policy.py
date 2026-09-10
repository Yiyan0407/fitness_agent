"""Coach-facing tool registry (always mounted; no keyword gating)."""

from __future__ import annotations

from agent.tools import ALL_TOOLS

# Near-duplicates kept as functions for pages/repo, but not exposed to the agent.
_EXCLUDED_FROM_COACH = frozenset({"log_meal", "get_day_detail"})

COACH_TOOLS = [
    t for t in ALL_TOOLS if getattr(t, "name", None) not in _EXCLUDED_FROM_COACH
]

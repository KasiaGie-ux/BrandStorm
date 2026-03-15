"""Context injection — replaces the entire nudge/dispatch system.

Instead of telling the agent what to do, we give it information:
the current canvas state, what just happened, and progress.
The agent decides autonomously what to do next.
"""

from __future__ import annotations

from models.session import Session


def build_context_message(session: Session, trigger: str, details: str = "") -> str:
    """Build the context message injected to the agent after each event.

    This is NOT a nudge. It gives the agent information, not instructions.
    The agent's system prompt tells it how to use this information.
    """
    canvas = session.canvas.snapshot()
    progress = canvas.pop("progress", 0.0)
    style_anchor = canvas.pop("style_anchor", "")

    lines = ["[CANVAS STATE]"]
    if style_anchor:
        lines.append(f"  style_anchor: {style_anchor}")

    for element_name, state in canvas.items():
        if not isinstance(state, dict):
            continue
        status = state.get("status", "empty")
        if status == "ready":
            if "url" in state:
                lines.append(f"  {element_name}: READY (url: {state['url'][:80]})")
            else:
                val = state.get("value", "")
                preview = str(val)[:80] if val else ""
                lines.append(f"  {element_name}: READY = {preview}")
        elif status == "stale":
            ctx = state.get("generated_with", {})
            lines.append(f"  {element_name}: STALE (generated_with: {ctx})")
        elif status == "generating":
            lines.append(f"  {element_name}: GENERATING...")
        else:
            lines.append(f"  {element_name}: EMPTY")

    lines.append(f"\n[TRIGGER] {trigger}")
    if details:
        lines.append(f"[DETAILS] {details}")

    ready = session.canvas.ready_count
    total = session.canvas.total_elements
    lines.append(f"\n[PROGRESS] {ready}/{total} elements ready ({progress:.0%})")

    return "\n".join(lines)

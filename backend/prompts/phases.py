"""Phase-specific prompts: analysis, naming, visual direction, copy, voice guide."""


def get_phase_prompt(phase: str) -> str:
    """Return the phase-specific prompt layer. See PRD section 9."""
    raise NotImplementedError(
        f"Phase-specific prompt for '{phase}' not yet implemented. "
        "See docs/PRD.md section 9 for prompt layer specifications."
    )

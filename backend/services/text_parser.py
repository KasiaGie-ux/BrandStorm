"""Parse structured tags from agent text output into typed frontend events.

The agent wraps key data in tags like [BRAND_NAME]...[/BRAND_NAME].
If tags are missing, regex fallback extracts data heuristically.
Returns (events, cleaned_text) — never crashes, always degrades gracefully.
"""

import logging
import re

logger = logging.getLogger("brand-agent")

# Tag patterns: [TAG_NAME]content[/TAG_NAME]
_TAG_RE = re.compile(
    r"\[([A-Z_]+)\](.*?)\[/\1\]",
    re.DOTALL,
)

# ---------- Regex fallback patterns ----------
_BRAND_NAME_RE = re.compile(
    r'(?:brand\s*name\s*(?:is|will\s*be|:)\s*["\u201c\u201d\']?'
    r'([A-Z\u00c0-\u017e][A-Za-z\u00c0-\u017e\s\'\u2019\u0101-\u016b]{1,30}?)'
    r'["\u201c\u201d\']?(?:\s*[-\u2014.]|\s*$))',
    re.IGNORECASE | re.MULTILINE,
)
_QUOTED_NAME_RE = re.compile(
    r'[\u201c\u201d"]'
    r'([A-Z\u00c0-\u017e][A-Za-z\u00c0-\u017e\s\'\u2019]{2,20})'
    r'[\u201c\u201d"]'
)
_TAGLINE_RE = re.compile(
    r'(?:tagline\s*(?:is|:)\s*["\']?(.+?)["\']?\s*$)',
    re.IGNORECASE | re.MULTILINE,
)
_VALUES_RE = re.compile(
    r'(?:values?\s*(?:are|:)\s*)(.+?)(?:\n|$)',
    re.IGNORECASE,
)
_HEX_RE = re.compile(r'(#[0-9a-fA-F]{3,6})\b')

# Track already-emitted event types to deduplicate
_DEDUP_TYPES = {"brand_name_reveal", "tagline_reveal", "brand_story", "brand_values"}


def parse_agent_text(
    text: str,
    seen_types: set[str] | None = None,
) -> tuple[list[dict], str]:
    """Extract structured events from agent text.

    Args:
        text: Raw agent text output (may contain tags or plain prose).
        seen_types: Set of event types already emitted this session,
                    used for deduplication. Mutated in place.

    Returns:
        (events, narration_text) — events is a list of dicts ready to send
        via WebSocket; narration_text is the remaining prose with tags stripped.
    """
    if not text or not text.strip():
        return [], ""

    if seen_types is None:
        seen_types = set()

    events: list[dict] = []
    found_tags = False

    try:
        for match in _TAG_RE.finditer(text):
            found_tags = True
            tag_name = match.group(1)
            content = match.group(2).strip()
            if not content:
                continue
            event = _parse_tag(tag_name, content)
            if event:
                logger.info(f"TextParser | Parsed tag: {tag_name} → type={event.get('type')} | keys={list(event.keys())}")
                events.append(event)
            else:
                logger.warning(f"TextParser | Tag {tag_name} returned None | content: {content[:100]}")

        # If no structured tags found, try regex fallback
        if not found_tags:
            fallback_events = _regex_fallback(text)
            events.extend(fallback_events)

        # Deduplicate: skip events whose type we've already emitted
        deduped: list[dict] = []
        for event in events:
            etype = event.get("type", "")
            if etype in _DEDUP_TYPES and etype in seen_types:
                logger.info(f"TextParser | Dedup skip: {etype}")
                continue
            if etype in _DEDUP_TYPES:
                seen_types.add(etype)
            deduped.append(event)
        events = deduped

    except Exception as e:
        logger.error(f"TextParser | Parse error (non-fatal): {e}")
        events = []

    # Strip all tags from narration text
    try:
        cleaned = _TAG_RE.sub("", text).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        # Remove tool-call narration lines (agent explaining what it's about to do)
        cleaned = _strip_tool_narration(cleaned)
    except Exception:
        cleaned = text.strip()

    if events:
        logger.info(
            f"TextParser | Extracted {len(events)} events: "
            f"{[e['type'] for e in events]}"
        )

    return events, cleaned


_TOOL_NARRATION_RE = re.compile(
    r"^.*?(?:"
    r"I will call|I'll call|I'm going to call|I am going to call|"
    r"I will now call|Let me call|I'll use|I will use|I'm calling|"
    r"The prompt will (?:include|be)|"
    r"I'll invoke|I will invoke|"
    r"calling generate_|calling analyze_|calling finalize_|"
    r"I'll generate|I will generate the"
    r").*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_tool_narration(text: str) -> str:
    """Remove lines where the agent narrates its tool-call intent."""
    cleaned = _TOOL_NARRATION_RE.sub("", text)
    cleaned = re.sub(r"\n{2,}", "\n\n", cleaned).strip()
    return cleaned


def _parse_tag(tag_name: str, content: str) -> dict | None:
    """Convert a single tag into a typed event dict."""
    try:
        if tag_name == "BRAND_NAME":
            return {"type": "brand_name_reveal", "name": content}

        if tag_name == "BRAND_NAME_RATIONALE":
            return {"type": "brand_name_reveal_rationale", "rationale": content}

        if tag_name == "TAGLINE":
            return {"type": "tagline_reveal", "tagline": content}

        if tag_name == "BRAND_STORY":
            return {"type": "brand_story", "story": content}

        if tag_name == "BRAND_VALUES":
            values = [v.strip() for v in content.split(",") if v.strip()]
            return {"type": "brand_values", "values": values}

        if tag_name == "DIRECTION_PROPOSALS":
            # Direction proposals removed — agent decides direction autonomously.
            # Silently consume the tag so it doesn't leak to frontend.
            return None

        if tag_name == "NAME_PROPOSALS":
            return _parse_name_proposals(content)

        if tag_name == "PALETTE":
            return _parse_palette(content)

        if tag_name == "FONT_SUGGESTION":
            return _parse_fonts(content)

        if tag_name == "AGENT_THINKING":
            # Silently consume — internal narration, not for display
            return None

        logger.warning(f"TextParser | Unknown tag: {tag_name}")
        return None

    except Exception as e:
        logger.error(f"TextParser | Tag parse error for {tag_name}: {e}")
        return None


# ---------- Regex fallback ----------

def _regex_fallback(text: str) -> list[dict]:
    """Try to extract structured data from untagged prose."""
    events: list[dict] = []

    # Brand name: "brand name is X" or quoted name
    m = _BRAND_NAME_RE.search(text)
    if m:
        events.append({"type": "brand_name_reveal", "name": m.group(1).strip()})
    elif not m:
        # Look for a quoted proper noun as brand name
        qm = _QUOTED_NAME_RE.search(text)
        if qm:
            events.append({"type": "brand_name_reveal", "name": qm.group(1).strip()})

    # Tagline
    m = _TAGLINE_RE.search(text)
    if m:
        events.append({"type": "tagline_reveal", "tagline": m.group(1).strip()})

    # Values (comma-separated after "values:")
    m = _VALUES_RE.search(text)
    if m:
        raw = m.group(1)
        values = [v.strip().strip("•-*") for v in re.split(r"[,\n]", raw) if v.strip()]
        if values:
            events.append({"type": "brand_values", "values": values})

    # Hex colors anywhere in text
    hexes = _HEX_RE.findall(text)
    if len(hexes) >= 3:
        colors = [{"hex": h, "role": "unknown", "name": ""} for h in hexes[:5]]
        events.append({"type": "palette_reveal", "colors": colors})

    if events:
        logger.info(
            f"TextParser | Regex fallback extracted: {[e['type'] for e in events]}"
        )

    return events


# ---------- Structured tag parsers ----------


def _parse_name_proposals(content: str) -> dict:
    """Parse name proposals from pipe-delimited lines.

    Format: id|name|rationale|recommended (optional)
    """
    names = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        entry = {
            "id": int(parts[0]) if parts[0].isdigit() else len(names) + 1,
            "name": parts[1],
            "rationale": parts[2],
        }
        if len(parts) > 3 and "recommended" in parts[3].lower():
            entry["recommended"] = True
        names.append(entry)

    return {
        "type": "name_proposals",
        "names": names,
        "auto_select_seconds": 10,
    }


def _parse_palette(content: str) -> dict:
    """Parse palette from pipe-delimited lines.

    Format: #hex|role|name
    """
    colors = []
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        colors.append({
            "hex": parts[0],
            "role": parts[1],
            "name": parts[2],
        })

    return {"type": "palette_reveal", "colors": colors}


def _parse_fonts(content: str) -> dict:
    """Parse font suggestion from pipe-delimited lines.

    Format (primary — pipe-delimited):
    heading|Family Name|style description
    body|Family Name|style description
    rationale|The rationale text

    Also handles colon-delimited and common agent variations.
    """
    logger.info(f"TextParser | _parse_fonts raw content: {content[:200]}")
    result: dict = {"type": "font_suggestion"}

    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Try pipe-delimited first
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) >= 2:
            key = parts[0].lower().strip("*- ")
            if key in ("heading", "body", "display"):
                mapped_key = "heading" if key in ("heading", "display") else "body"
                result[mapped_key] = {
                    "family": parts[1].strip("*` "),
                    "google_fonts": True,
                    "style": parts[2].strip("*` ") if len(parts) > 2 else "",
                }
                continue
            elif key == "rationale":
                result["rationale"] = parts[1] if len(parts) == 2 else "|".join(parts[1:])
                continue

        # Try colon-delimited fallback (e.g. "Heading: Playfair Display")
        if ":" in line:
            key_part, _, val_part = line.partition(":")
            key = key_part.lower().strip("*- ")
            val = val_part.strip("*` ")
            if key in ("heading", "heading font", "display", "display font"):
                result["heading"] = {"family": val, "google_fonts": True, "style": ""}
            elif key in ("body", "body font", "text", "text font"):
                result["body"] = {"family": val, "google_fonts": True, "style": ""}
            elif key == "rationale":
                result["rationale"] = val

    # Only emit if we have at least one font
    if "heading" not in result and "body" not in result:
        logger.warning(f"TextParser | FONT_SUGGESTION parsed no fonts from: {content[:200]}")
        return None

    logger.info(f"TextParser | FONT_SUGGESTION result: heading={result.get('heading', {}).get('family')} body={result.get('body', {}).get('family')}")
    return result

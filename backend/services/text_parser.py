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
_DEDUP_TYPES = {"brand_name_reveal", "tagline_reveal", "brand_story", "brand_values", "tone_of_voice"}


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
        # Remove leaked palette-format lines (e.g. "#cfae68|primary|Liquid Gold")
        cleaned = _strip_leaked_palette(cleaned)
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
    r"I'll generate|I will generate the|"
    r"Let me create your logo|Let me generate|Let me design|"
    r"Now let's (?:create|generate|design)|Now I'll (?:create|generate|design)|"
    r"Time to create|Time to generate"
    r").*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_tool_narration(text: str) -> str:
    """Remove lines where the agent narrates its tool-call intent."""
    cleaned = _TOOL_NARRATION_RE.sub("", text)
    cleaned = re.sub(r"\n{2,}", "\n\n", cleaned).strip()
    return cleaned


# Matches lines that look like raw palette data leaked into narration:
# "#cfae68|primary|Liquid Gold" or "#1a1a2e | accent | Deep Ink"
_LEAKED_PALETTE_RE = re.compile(
    r"^.*#[0-9a-fA-F]{3,8}\s*\|.*\|.*$",
    re.MULTILINE,
)


def _strip_leaked_palette(text: str) -> str:
    """Remove raw palette-format lines that leaked into agent narration."""
    cleaned = _LEAKED_PALETTE_RE.sub("", text)
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

        if tag_name == "TONE_OF_VOICE":
            return _parse_tone_of_voice(content)

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

    Audio transcription fallback: when the Live API transcribes speech,
    newlines and pipes may be lost. We handle:
      - Proper pipe-delimited lines (primary)
      - Numbered entries like "1. Name — rationale" or "1) Name: rationale"
      - Run-on text with numbers as separators
    """
    logger.info(f"TextParser | _parse_name_proposals raw content: {content[:300]}")
    names = []

    # Primary: try pipe-delimited lines
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            entry = {
                "id": int(parts[0]) if parts[0].isdigit() else len(names) + 1,
                "name": parts[1],
                "rationale": parts[2],
            }
            if len(parts) > 3 and "recommended" in parts[3].lower():
                entry["recommended"] = True
            names.append(entry)

    if len(names) >= 2:
        return {
            "type": "name_proposals",
            "names": names,
            "auto_select_seconds": 8,
        }

    # Fallback: numbered entries from audio transcription
    # Matches patterns like: "1. Aurum — Latin for gold" or "1) Aurum: Latin for gold"
    # or "1 Aurum Latin for gold, 2 Lumina ..."
    names = []
    numbered_re = re.compile(
        r'(\d)\s*[.):\-]?\s*'            # number prefix
        r'([A-Z\u00c0-\u017e][A-Za-z\u00c0-\u017e\'\u2019\u0101-\u016b]+)'  # name (capitalized word)
        r'\s*[:\u2014\u2013\-,.]?\s*'     # separator
        r'(.*?)(?=\d\s*[.):\-]?\s*[A-Z]|recommended|$)',  # rationale until next number or end
        re.DOTALL,
    )
    for m in numbered_re.finditer(content):
        num, name, rationale = m.group(1), m.group(2).strip(), m.group(3).strip()
        if not name:
            continue
        rationale = rationale.rstrip(" ,.|")
        entry = {"id": int(num), "name": name, "rationale": rationale}
        # Check if "recommended" appears near this entry
        span_end = m.end()
        lookahead = content[span_end:span_end + 30].lower()
        if "recommended" in lookahead or "recommended" in rationale.lower():
            entry["recommended"] = True
            entry["rationale"] = re.sub(r'\s*recommended\s*', '', entry["rationale"], flags=re.IGNORECASE).strip()
        names.append(entry)

    # Deduplicate by name
    seen = set()
    unique = []
    for n in names:
        if n["name"] not in seen:
            seen.add(n["name"])
            unique.append(n)
    names = unique

    if names:
        logger.info(f"TextParser | Name proposals fallback extracted {len(names)} names: {[n['name'] for n in names]}")

    return {
        "type": "name_proposals",
        "names": names,
        "auto_select_seconds": 8,
    }


def _parse_tone_of_voice(content: str) -> dict:
    """Parse tone of voice from pipe-delimited lines.
    
    Format:
    do|The rule to do
    dont|The rule to avoid
    """
    dos = []
    donts = []
    
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        
        # Support both | and : as delimiters
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 1)]
        elif ":" in line:
            parts = [p.strip() for p in line.split(":", 1)]
        else:
            continue

        if len(parts) == 2:
            kind, rule = parts[0].lower(), parts[1]
            if kind in ("do", "dos"):
                dos.append(rule)
            elif kind in ("dont", "don't", "do not", "donts"):
                donts.append(rule)
                
    return {
        "type": "tone_of_voice",
        "tone_of_voice": {
            "do": dos,
            "dont": donts
        }
    }


def _parse_palette(content: str) -> dict:
    """Parse palette from pipe-delimited lines.

    Format: #hex|role|name

    Audio transcription fallback: pipes/newlines may be lost.
    Handles: "#hex role name, #hex role name" or run-on text with hex codes.
    """
    logger.info(f"TextParser | _parse_palette raw content: {content[:300]}")
    colors = []

    # Primary: pipe-delimited lines
    for line in content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            colors.append({
                "hex": parts[0],
                "role": parts[1],
                "name": parts[2],
            })

    if len(colors) >= 3:
        return {"type": "palette_reveal", "colors": colors}

    # Fallback: extract hex codes and surrounding context from transcription
    colors = []
    # Match: #hex followed by optional role and name text
    palette_entry_re = re.compile(
        r'(#[0-9a-fA-F]{3,8})\s*'                    # hex code
        r'[\|,\s]*\s*'                                 # separator
        r'(primary|secondary|accent|neutral|background)?'  # optional role
        r'\s*[\|,:\-\s]*\s*'                           # separator
        r'([A-Za-z\u00c0-\u017e][A-Za-z\u00c0-\u017e\s]{0,25})?',  # optional name
        re.IGNORECASE,
    )
    roles_seen = set()
    role_order = ["primary", "secondary", "accent", "neutral", "background"]
    for m in palette_entry_re.finditer(content):
        hex_val = m.group(1)
        role = (m.group(2) or "").lower().strip() or None
        name = (m.group(3) or "").strip()
        # Clean name — remove trailing role-like words
        name = re.sub(r'\b(primary|secondary|accent|neutral|background)\b.*', '', name, flags=re.IGNORECASE).strip()
        if not role:
            # Assign role in order
            for r in role_order:
                if r not in roles_seen:
                    role = r
                    break
            if not role:
                role = "unknown"
        roles_seen.add(role)
        colors.append({"hex": hex_val, "role": role, "name": name})

    if colors:
        logger.info(f"TextParser | Palette fallback extracted {len(colors)} colors")

    return {"type": "palette_reveal", "colors": colors}


def _parse_fonts(content: str) -> dict:
    """Parse font suggestion from pipe-delimited lines.

    Format (primary — pipe-delimited):
    heading|Family Name|style description
    body|Family Name|style description
    rationale|The rationale text

    Also handles colon-delimited, comma-delimited, and audio transcription
    run-on text where pipes/newlines are lost.
    """
    logger.info(f"TextParser | _parse_fonts raw content: {content[:300]}")
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

    # Fallback: audio transcription run-on text
    # e.g. "CORMORANT GARAMOND · SERIF, REFINED BODY OPEN SANS SANS-SERIF"
    # or "heading Playfair Display serif elegant body Inter clean modern rationale ..."
    if "heading" not in result and "body" not in result:
        text = content.strip()

        # Try to find font names — common Google Fonts patterns
        _KNOWN_FONTS = [
            "Playfair Display", "Cormorant Garamond", "Cormorant", "Bebas Neue",
            "Libre Baskerville", "DM Serif Display", "Lora", "Merriweather",
            "Crimson Text", "Spectral", "Noto Serif", "Source Serif",
            "Inter", "Open Sans", "Syne", "Montserrat", "Raleway", "Poppins",
            "Work Sans", "DM Sans", "Outfit", "Manrope", "Nunito", "Lato",
            "Roboto", "Jost", "Space Grotesk", "Plus Jakarta Sans",
        ]

        found_fonts = []
        for font in _KNOWN_FONTS:
            if font.lower() in text.lower():
                found_fonts.append(font)

        if len(found_fonts) >= 2:
            result["heading"] = {"family": found_fonts[0], "google_fonts": True, "style": ""}
            result["body"] = {"family": found_fonts[1], "google_fonts": True, "style": ""}
            logger.info(f"TextParser | FONT_SUGGESTION font-name fallback: heading={found_fonts[0]}, body={found_fonts[1]}")
        elif len(found_fonts) == 1:
            result["heading"] = {"family": found_fonts[0], "google_fonts": True, "style": ""}
            logger.info(f"TextParser | FONT_SUGGESTION font-name fallback (single): heading={found_fonts[0]}")

        # Try keyword-based extraction: "heading ... body ... rationale ..."
        if "heading" not in result:
            heading_re = re.compile(
                r'(?:heading|display)\s*[:\-\|]?\s*'
                r'([A-Z][A-Za-z\s]+?)(?:\s*[\|·,\-]\s*|\s+(?:body|rationale|serif|sans))',
                re.IGNORECASE,
            )
            m = heading_re.search(text)
            if m:
                result["heading"] = {"family": m.group(1).strip(), "google_fonts": True, "style": ""}

        if "body" not in result:
            body_re = re.compile(
                r'(?:body|text)\s*[:\-\|]?\s*'
                r'([A-Z][A-Za-z\s]+?)(?:\s*[\|·,\-]\s*|\s+(?:rationale|serif|sans)|$)',
                re.IGNORECASE,
            )
            m = body_re.search(text)
            if m:
                result["body"] = {"family": m.group(1).strip(), "google_fonts": True, "style": ""}

    # Only emit if we have at least one font
    if "heading" not in result and "body" not in result:
        logger.warning(f"TextParser | FONT_SUGGESTION parsed no fonts from: {content[:200]}")
        return None

    logger.info(f"TextParser | FONT_SUGGESTION result: heading={result.get('heading', {}).get('family')} body={result.get('body', {}).get('family')}")
    return result

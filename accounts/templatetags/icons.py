"""Small inline stroke-based SVG icons, replacing the emoji glyphs the UI
previously used throughout the site. Emoji render inconsistently across
platforms/fonts (different weight, color, and style per OS) and read as an
unpolished, "AI-generated" look - a single consistent icon set fixes both
problems at once. Every icon shares one outer <svg> shape (see `icon()`
below) so they're all the same visual weight; only the inner shape data
differs per name.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Each entry is just the inner SVG shapes - the outer <svg> wrapper (size,
# viewBox, stroke) is added once in icon() below, so adding a new icon only
# means adding one line here.
_ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "academic-cap": '<path d="M2 8l10-5 10 5-10 5-10-5z"/><path d="M6 10.5v4c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-4"/>',
    "building": '<rect x="5" y="4" width="14" height="17"/><rect x="8" y="7" width="2" height="2"/><rect x="14" y="7" width="2" height="2"/><rect x="8" y="12" width="2" height="2"/><rect x="14" y="12" width="2" height="2"/><rect x="10" y="17" width="4" height="4"/>',
    "bell": '<path d="M12 3a5 5 0 0 0-5 5v3.5c0 1-.4 2-1.2 2.7L4 16h16l-1.8-1.8c-.8-.7-1.2-1.7-1.2-2.7V8a5 5 0 0 0-5-5z"/><path d="M9 18a3 3 0 0 0 6 0"/>',
    "sparkles": '<path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M19 14l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z"/>',
    "document": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/>',
    "check": '<polyline points="4 12 9 17 20 6"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/>',
    "x": '<line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/>',
    "warning": '<path d="M12 3l10 18H2z"/><line x1="12" y1="9" x2="12" y2="14"/><line x1="12" y1="17" x2="12" y2="17.01"/>',
    "clipboard": '<rect x="6" y="4" width="12" height="17" rx="1"/><rect x="9" y="2.5" width="6" height="3" rx="1"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="15" y2="14"/>',
    "bar-chart": '<line x1="5" y1="20" x2="5" y2="12"/><line x1="12" y1="20" x2="12" y2="7"/><line x1="19" y1="20" x2="19" y2="15"/>',
    "book": '<path d="M4 5c3-1.5 6-1.5 8 0v14c-2-1.5-5-1.5-8 0z"/><path d="M20 5c-3-1.5-6-1.5-8 0v14c2-1.5 5-1.5 8 0z"/>',
    "calendar": '<rect x="4" y="5" width="16" height="15" rx="1"/><line x1="4" y1="9" x2="20" y2="9"/><line x1="8" y1="3" x2="8" y2="6"/><line x1="16" y1="3" x2="16" y2="6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
    "chat": '<path d="M4 5h16v11H8l-4 4z"/>',
    "trophy": '<path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 5H4v2a3 3 0 0 0 3 3"/><path d="M17 5h3v2a3 3 0 0 1-3 3"/><line x1="12" y1="14" x2="12" y2="18"/><line x1="8" y1="20" x2="16" y2="20"/><line x1="9" y1="18" x2="15" y2="18"/>',
    "user-plus": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><line x1="18" y1="7" x2="18" y2="13"/><line x1="15" y1="10" x2="21" y2="10"/>',
    "repeat": '<path d="M4 10a8 8 0 0 1 14-5"/><polyline points="18 2 18 6 14 6"/><path d="M20 14a8 8 0 0 1-14 5"/><polyline points="6 22 6 18 10 18"/>',
    "trending-up": '<polyline points="3 17 9 11 13 15 21 6"/><polyline points="15 6 21 6 21 12"/>',
    "trending-down": '<polyline points="3 7 9 13 13 9 21 18"/><polyline points="15 18 21 18 21 12"/>',
    "lightbulb": '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.5.4.8 1 .8 1.6h5.4c0-.6.3-1.2.8-1.6A6 6 0 0 0 12 3z"/>',
    "tag": '<path d="M3 11l8-8h7v7l-8 8z"/><circle cx="14" cy="9" r="1.2"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "dot": '<circle cx="12" cy="12" r="6"/>',
    "archive": '<rect x="4" y="4" width="16" height="5" rx="1"/><rect x="5" y="9" width="14" height="11"/><line x1="10" y1="13" x2="14" y2="13"/>',
    "folder": '<path d="M4 6h6l2 2h8v11H4z"/>',
    "key": '<circle cx="8" cy="14" r="4"/><line x1="11" y1="11" x2="20" y2="2"/><line x1="16" y1="6" x2="19" y2="9"/><line x1="13" y1="9" x2="16" y2="12"/>',
    "camera": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7l1.5-3h5L16 7"/><circle cx="12" cy="13.5" r="3.5"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="1"/><polyline points="3 6 12 13 21 6"/>',
    "scroll": '<path d="M7 3h7l4 4v14H7z"/><line x1="10" y1="12" x2="15" y2="12"/><line x1="10" y1="16" x2="15" y2="16"/>',
    "paperclip": '<path d="M8 12V6a4 4 0 0 1 8 0v10a2 2 0 0 1-4 0V8"/>',
    "pin": '<circle cx="12" cy="9" r="4"/><path d="M12 13v8"/>',
    "users": '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><path d="M2 20c0-3 2.7-5.5 6-5.5s6 2.5 6 5.5"/><path d="M10 20c0-3 2.7-5.5 6-5.5s6 2.5 6 5.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"/>',
    "settings": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/>',
    "pencil": '<path d="M4 20l4-1 10-10-3-3L5 16z"/><line x1="14.5" y1="6.5" x2="17.5" y2="9.5"/>',
}


@register.simple_tag
def icon(name, size="1em"):
    """Usage: {% icon "home" %} or {% icon "home" size="20px" %}.
    stroke="currentColor" so each icon inherits whatever color/hover-state
    styling its wrapping element (e.g. .sidebar-icon) already applies -
    no per-icon CSS needed, same as the emoji glyphs it replaces."""
    inner = _ICONS.get(name, "")
    return mark_safe(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        'focusable="false">{inner}</svg>'.format(size=size, inner=inner)
    )

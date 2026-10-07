from pathlib import Path
root = Path(__file__).resolve().parents[1]
path = root / 'app/services/gmaps_service.py'
s = path.read_text()
start = s.index('def search_google_maps_leads(')
end = s.index('\ndef import_gmaps_leads_to_customers', start)
s = s[:start] + '''def search_google_maps_leads(query: str, location: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return only real OpenStreetMap records; never fabricate contact data."""
    from fastapi import HTTPException
    if not 1 <= limit <= 50:
        raise HTTPException(400, "Search limit must be between 1 and 50")
    search_term = urllib.parse.quote(f"{query.strip()} in {location.strip()}")
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?q={search_term}&format=json&addressdetails=1&extratags=1&limit={limit}",
        headers={"User-Agent": "HanuRamTech/1.0 (hanuramtech@gmail.com)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            items = json.loads(response.read(2_000_000))
    except (OSError, ValueError):
        raise HTTPException(502, "Live directory search is unavailable; no generated leads were substituted") from None
    if not isinstance(items, list):
        raise HTTPException(502, "Unexpected directory response")
    leads = []
    for item in items:
        tags = item.get("extratags") or {}
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile")
        leads.append({
            "id": f"osm_{item.get('osm_type')}_{item.get('osm_id')}",
            "business_name": item.get("name") or item.get("display_name", "").split(",")[0],
            "phone": re.sub(r"[^\\d+]", "", phone) if phone else None,
            "category": item.get("type") or query,
            "rating": None, "reviews_count": None,
            "address": item.get("display_name"),
            "website": tags.get("website") or tags.get("contact:website"),
            "latitude": item.get("lat"), "longitude": item.get("lon"),
            "verified": False, "source": "OpenStreetMap",
        })
    return leads

''' + s[end:]
s = s.replace('import random\n', '')
path.write_text(s)

# Client labels must not imply integration features that do not exist.
frontend = Path(r'D:\web apps\React\CBD project')
replacements = {
    'src/Pages/CLC/whatsapp/BulkSenderTab.jsx': {
        'Bulk & Unlimited WhatsApp Sender': 'WhatsApp Broadcast Sender',
        'Anti-ban': 'Sending', 'anti-ban': 'sending',
    },
    'src/Pages/CLC/whatsapp/NumberFilterTab.jsx': {
        'valid WhatsApp numbers detected!': 'numbers with valid formatting. WhatsApp availability was not checked.',
    },
    'src/Pages/CLC/whatsapp/GMapsExtractorTab.jsx': {
        'Google Maps': 'OpenStreetMap', 'G-Maps': 'Directory',
    },
    'src/Pages/CLC/whatsapp/GroupToolsTab.jsx': {
        'Grab all contact numbers from active WhatsApp groups, or batch-join promotional groups with safe anti-ban pacing.': 'Parse numbers from text you provide and validate invite-link formats. This tool does not read group membership or join groups through Meta.',
    },
    'src/Pages/CLC/whatsapp/AutoResponderTab.jsx': {
        '<form': '<p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">Rules can be saved and tested here. Automatic replies to incoming WhatsApp messages are not connected.</p>\n    <form',
    },
}
for name, pairs in replacements.items():
    path = frontend / name
    s = path.read_text(encoding='utf-8')
    for before, after in pairs.items():
        # AutoResponder return shape needs a wrapper; leave unchanged until inspected.
        if name.endswith('AutoResponderTab.jsx'):
            continue
        s = s.replace(before, after)
    path.write_text(s, encoding='utf-8')

"""
label_fill.py — fill the DYMO template with one fixture's data.

This is the token-replacement logic proven in print_test.py, packaged for reuse.
The template contains these tokens in its text objects:
    #fid #u #add #profile #description #fixturetype #link

Rules:
  - #add (DMX offset) is always zero-padded to 3 digits: 1 -> "001", 463 -> "463"
  - all values are XML-escaped so ampersands etc. don't corrupt the label
  - tokens are replaced longest-first as a safety discipline against prefixes
"""


# A fixture dict is expected to have these keys. 'link' is added by the laptop
# from the link store before filling, not sent by MA.
REQUIRED_FIELDS = ("fid", "universe", "address", "profile",
                   "description", "fixturetype", "link")


def xml_escape(value) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fill_template(template_xml: str, fx: dict) -> str:
    """
    Return a filled copy of template_xml for fixture dict fx.

    fx must contain: fid, universe, address, profile, description,
    fixturetype, link.  (address is the per-universe offset, 1-512.)
    """
    missing = [k for k in REQUIRED_FIELDS if k not in fx]
    if missing:
        raise ValueError(f"Fixture missing fields: {missing}")

    addr_padded = str(fx["address"]).zfill(3)

    # Longest tokens first (defensive; current tokens don't actually collide).
    replacements = [
        ("#fixturetype", fx["fixturetype"]),
        ("#description", fx["description"]),
        ("#profile",     fx["profile"]),
        ("#link",        fx["link"]),
        ("#fid",         fx["fid"]),
        ("#add",         addr_padded),
        ("#u",           str(fx["universe"])),
    ]

    out = template_xml
    for token, value in replacements:
        out = out.replace(token, xml_escape(value))
    return out


def find_unreplaced_tokens(filled_xml: str) -> list[str]:
    """Return any known tokens still present (sanity check after fill)."""
    tokens = ["#fid", "#u", "#add", "#profile",
              "#description", "#fixturetype", "#link"]
    return [t for t in tokens if t in filled_xml]


# Quick self-test
if __name__ == "__main__":
    import re

    with open("LabelTemplate_2026_Python.dymo", "r", encoding="utf-8-sig") as f:
        tpl = f.read()

    fx = {
        "fid": "703", "universe": 1, "address": 1,
        "profile": "37 ch",
        "description": "Limited CCT & RGB + Control - 16 Bit",
        "fixturetype": "Proteus Maximus",
        "link": "11111111A",
    }
    filled = fill_template(tpl, fx)

    leftover = find_unreplaced_tokens(filled)
    print("  unreplaced tokens:", leftover or "none")

    # show resulting text objects
    blocks = re.split(r"(?=<Name>TextObject)", filled)
    for b in blocks:
        m = re.search(r"<Name>(TextObject\d+)</Name>", b)
        if not m:
            continue
        texts = re.findall(r"<Text>(.*?)</Text>", b, re.S)
        print(f"  {m.group(1)}: {' | '.join(t.strip() for t in texts)}")

    # confirm address zero-padding: address 1 -> 001
    assert "1/001" in filled, "address padding failed"
    print("  address padding OK (1 -> 001)")

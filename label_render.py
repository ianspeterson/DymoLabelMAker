"""
label_render.py — render a filled DYMO label XML to a PNG image.

Used by the review screen so you can see labels before printing. Parses the
DYMO Connect 'DesktopLabel' format: each text object has an ObjectLayout
(position + size in inches), background brush, font, and font color. We draw
them onto a white canvas at print proportions.

This is a *preview* renderer — it approximates fonts (Helvetica -> a bundled
sans) and shrink-to-fit. The real DYMO service renders the true output; this
is just to catch mistakes before committing to the printer.
"""

import re
import io
import os
from PIL import Image, ImageDraw, ImageFont


DPI = 200  # preview resolution; 200 is crisp enough for screen, fast to make


def _font_path(bold: bool, italic: bool) -> str | None:
    """Return a usable TrueType font path on Windows/macOS/Linux."""
    candidates = []

    # Linux / sandbox
    linux_base = "/usr/share/fonts/truetype/dejavu/"
    if bold and italic:
        candidates.append(linux_base + "DejaVuSans-BoldOblique.ttf")
    if bold:
        candidates.append(linux_base + "DejaVuSans-Bold.ttf")
    if italic:
        candidates.append(linux_base + "DejaVuSans-Oblique.ttf")
    candidates.append(linux_base + "DejaVuSans.ttf")

    # Windows
    win = os.environ.get("WINDIR", r"C:\Windows")
    if bold and italic:
        candidates.append(os.path.join(win, "Fonts", "arialbi.ttf"))
    if bold:
        candidates.append(os.path.join(win, "Fonts", "arialbd.ttf"))
    if italic:
        candidates.append(os.path.join(win, "Fonts", "ariali.ttf"))
    candidates.append(os.path.join(win, "Fonts", "arial.ttf"))

    # macOS
    candidates.extend([
        "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf" if bold and italic else "",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "",
        "/System/Library/Fonts/Supplemental/Arial Italic.ttf" if italic else "",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ])

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _load_font(bold: bool, italic: bool, px: int):
    path = _font_path(bold, italic)
    if path:
        try:
            return ImageFont.truetype(path, px)
        except Exception:
            pass
    return ImageFont.load_default()


def _color_tuple(color_tuple, fallback=(0, 0, 0)):
    """
    DYMO Connect often stores colors as normalized floats/ints in the 0..1 range
    (white = 1,1,1), while PIL expects 0..255. Some files may use 0..255.
    Normalize both formats.
    """
    if not color_tuple:
        return fallback
    try:
        _a, r, g, b = [float(x) for x in color_tuple]
    except Exception:
        return fallback
    vals = [r, g, b]
    if max(vals) <= 1.0:
        vals = [v * 255 for v in vals]
    return tuple(max(0, min(255, int(round(v)))) for v in vals)


def _fit_font(text, bold, italic, max_w, max_h, start_px):
    px = max(start_px, 6)
    while px > 6:
        f = _load_font(bold, italic, px)
        bbox = f.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_w and (bbox[3] - bbox[1]) <= max_h:
            return f
        px -= 2
    return _load_font(bold, italic, 6)


def _parse_objects(xml: str):
    objs = []
    for b in re.split(r"(?=<Name>TextObject)", xml):
        m = re.search(r"<Name>(TextObject\d+)</Name>", b)
        if not m:
            continue
        lay = re.search(
            r"<ObjectLayout>\s*<DYMOPoint>\s*<X>([\d.]+)</X>\s*<Y>([\d.]+)</Y>"
            r".*?<Width>([\d.]+)</Width>\s*<Height>([\d.]+)</Height>", b, re.S)
        if not lay:
            continue
        bg = re.search(
            r"<BackgroundBrush>\s*<SolidColorBrush>\s*"
            r'<Color A="([\d.]+)" R="([\d.]+)" G="([\d.]+)" B="([\d.]+)"', b)
        font = re.search(
            r"<FontName>(.*?)</FontName>\s*<FontSize>([\d.]+)</FontSize>\s*"
            r"<IsBold>(\w+)</IsBold>\s*<IsItalic>(\w+)</IsItalic>", b, re.S)
        fb = re.search(
            r"<FontBrush>\s*<SolidColorBrush>\s*"
            r'<Color A="([\d.]+)" R="([\d.]+)" G="([\d.]+)" B="([\d.]+)"', b)
        rot = re.search(r"<Rotation>Rotation(\d+)</Rotation>", b)
        halign = re.search(r"<HorizontalAlignment>(\w+)</HorizontalAlignment>", b)
        texts = [t.strip() for t in re.findall(r"<Text>(.*?)</Text>", b, re.S)]
        text = "\n".join(texts).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        x, y, w, h = map(float, lay.groups())
        objs.append(dict(
            x=x, y=y, w=w, h=h,
            bg=tuple(map(float, bg.groups())) if bg else None,
            font=font.groups() if font else ("Helvetica", "10", "False", "False"),
            fb=tuple(map(float, fb.groups())) if fb else (1, 0, 0, 0),
            rot=int(rot.group(1)) if rot else 0,
            halign=halign.group(1) if halign else "Left",
            text=text,
        ))
    return objs


def render_to_png_bytes(filled_xml: str) -> bytes:
    """Render filled label XML and return PNG bytes."""
    objs = _parse_objects(filled_xml)
    if not objs:
        raise ValueError("No text objects found to render.")

    label_w_in = max(o["x"] + o["w"] for o in objs) + 0.25
    label_h_in = max(o["y"] + o["h"] for o in objs) + 0.15
    W, H = int(label_w_in * DPI), int(label_h_in * DPI)

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, W - 3, H - 3], radius=int(0.13 * DPI),
                           outline=(200, 200, 200), width=3)

    for o in objs:
        px0, py0 = int(o["x"] * DPI), int(o["y"] * DPI)
        pw, ph = int(o["w"] * DPI), int(o["h"] * DPI)

        if o["bg"] and o["bg"][0] > 0:
            draw.rectangle([px0, py0, px0 + pw, py0 + ph],
                           fill=_color_tuple(o["bg"], fallback=(255, 255, 255)))

        fname, fsize, fbold, fit = o["font"]
        bold = fbold == "True"
        italic = fit == "True"
        fcol = _color_tuple(o["fb"], fallback=(0, 0, 0))
        start_px = int(float(fsize) / 72 * DPI)

        if o["rot"] in (90, 270):
            tmp = Image.new("RGBA", (max(ph, 10), max(pw, 10)), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            f = _fit_font(o["text"], bold, italic, ph - 4, pw - 4, start_px)
            td.text((ph // 2, pw // 2), o["text"], font=f, fill=fcol, anchor="mm")
            tmp = tmp.rotate(-90, expand=True) if o["rot"] == 90 else tmp.rotate(90, expand=True)
            img.paste(tmp, (px0, py0), tmp)
        else:
            lines = o["text"].split("\n")
            fonts = [_fit_font(l, bold, italic, pw - 6,
                               max(ph // len(lines) - 2, 8), start_px) for l in lines]
            heights = [f.getbbox(l)[3] - f.getbbox(l)[1] for f, l in zip(fonts, lines)]
            total = sum(heights) + 6 * (len(lines) - 1)
            cy = py0 + (ph - total) // 2
            for l, f in zip(lines, fonts):
                bbox = f.getbbox(l)
                lw = bbox[2] - bbox[0]
                if o["halign"] == "Center":
                    lx = px0 + (pw - lw) // 2
                elif o["halign"] == "Right":
                    lx = px0 + pw - lw
                else:
                    lx = px0
                draw.text((lx, cy - bbox[1]), l, font=f, fill=fcol)
                cy += (bbox[3] - bbox[1]) + 6

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    from label_fill import fill_template
    with open("LabelTemplate_2026_Python.dymo", "r", encoding="utf-8-sig") as f:
        tpl = f.read()
    fx = {"fid": "703", "universe": 1, "address": 463, "profile": "37 ch",
          "description": "Limited CCT & RGB + Control - 16 Bit",
          "fixturetype": "Proteus Maximus", "link": "11111111A"}
    png = render_to_png_bytes(fill_template(tpl, fx))
    with open("render_test.png", "wb") as f:
        f.write(png)
    print(f"  wrote render_test.png ({len(png)} bytes)")

"""
range_parse.py — parse MA/BO-style range strings into fixture numbers.

Supports:
    703
    202 thru 208
    202 t 208
    202 + 205 + 207
    202, 205, 207
    1 thru          -> 1..99999
    1 t             -> 1..99999
"""

import re

OPEN_THRU_MAX = 99999

class RangeParseError(ValueError):
    pass


def parse_range(text: str) -> list[int]:
    if text is None:
        raise RangeParseError("No range provided.")
    s = str(text).strip().lower()
    if not s:
        raise RangeParseError("Range is empty.")
    s = re.sub(r"^fixture\s+", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.replace(",", "+")
    result: set[int] = set()
    chunks = [c.strip() for c in s.split("+")]
    for chunk in chunks:
        if not chunk:
            raise RangeParseError(f"Empty segment in '{text}' (stray '+' or comma?).")

        # Normalize shorthand t to thru only when it is a standalone word.
        chunk = re.sub(r"\bt\b", "thru", chunk)

        m = re.fullmatch(r"(\d+)\s+thru\s+(\d+)", chunk)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            result.update(range(lo, hi + 1))
            continue

        m = re.fullmatch(r"(\d+)\s+thru", chunk)
        if m:
            lo = int(m.group(1))
            result.update(range(lo, OPEN_THRU_MAX + 1))
            continue

        m = re.fullmatch(r"\d+", chunk)
        if m:
            result.add(int(chunk))
            continue

        raise RangeParseError(f"Could not parse range segment: '{chunk}'.")

    return sorted(result)


if __name__ == "__main__":
    for s in ["703", "202 thru 208", "202 t 208", "202+205,207", "1 thru"]:
        got = parse_range(s)
        print(s, got[:10], len(got))

"""
range_parse.py — parse MA-style range strings into a list of fixture numbers.

Supports the syntax you'd type on the MA keypad:
    "703"                -> [703]
    "202 thru 208"       -> [202, 203, 204, 205, 206, 207, 208]
    "202 + 205 + 207"    -> [202, 205, 207]
    "202 thru 208 + 300" -> [202..208, 300]
    "1 thru 5 + 10 thru 12"

Also tolerates lowercase/uppercase "thru", extra spaces, and "+" with or
without surrounding spaces. This module is used on the laptop side, but the
same logic mirrors what the MA plugin resolves, so it's handy for testing.

Note: in practice the MA plugin resolves the range against the patch itself
(only existing fixtures get sent). This parser is a convenience/fallback and
for validating input shape.
"""

import re


class RangeParseError(ValueError):
    """Raised when a range string can't be understood."""
    pass


def parse_range(text: str) -> list[int]:
    """
    Parse a range string into a sorted, de-duplicated list of integers.

    Raises RangeParseError on malformed input.
    """
    if text is None:
        raise RangeParseError("No range provided.")

    s = text.strip().lower()
    if not s:
        raise RangeParseError("Range is empty.")

    # Normalize: collapse whitespace, standardize separators
    s = re.sub(r"\s+", " ", s)

    result: set[int] = set()

    # Split on "+" first — each chunk is either a single number or a "thru" range
    chunks = [c.strip() for c in s.split("+")]

    for chunk in chunks:
        if not chunk:
            raise RangeParseError(f"Empty segment in '{text}' (stray '+'?).")

        if "thru" in chunk:
            parts = [p.strip() for p in chunk.split("thru")]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise RangeParseError(f"Malformed range segment: '{chunk}'.")
            lo = _to_int(parts[0], text)
            hi = _to_int(parts[1], text)
            if lo > hi:
                lo, hi = hi, lo  # tolerate reversed ranges
            result.update(range(lo, hi + 1))
        else:
            result.add(_to_int(chunk, text))

    return sorted(result)


def _to_int(token: str, original: str) -> int:
    token = token.strip()
    if not re.fullmatch(r"\d+", token):
        raise RangeParseError(
            f"'{token}' is not a whole number (in '{original}')."
        )
    return int(token)


# Quick self-test
if __name__ == "__main__":
    tests = [
        ("703", [703]),
        ("202 thru 208", [202, 203, 204, 205, 206, 207, 208]),
        ("202 + 205 + 207", [202, 205, 207]),
        ("202 thru 204 + 300", [202, 203, 204, 300]),
        ("5 THRU 1", [1, 2, 3, 4, 5]),            # reversed
        ("10+10+10", [10]),                        # dedupe
        ("1 thru 3 + 2 thru 4", [1, 2, 3, 4]),    # overlap merge
    ]
    for inp, expected in tests:
        got = parse_range(inp)
        status = "OK " if got == expected else "FAIL"
        print(f"  [{status}] '{inp}' -> {got}")

    for bad in ["", "  ", "abc", "1 thru", "thru 5", "1 + + 2", "1 thru 2 thru 3"]:
        try:
            parse_range(bad)
            print(f"  [FAIL] '{bad}' should have raised")
        except RangeParseError as e:
            print(f"  [OK ] '{bad}' rejected: {e}")

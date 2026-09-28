"""Repair text that was encoded as UTF-8 and read back as Windows-1252.

BIS's own records carry it: an en dash stored as "â€“", a lost character as
"ï¿½" (the replacement character, itself double-encoded). The first kind
decodes back exactly; the second was lost before BIS published it, so it
becomes a plain dash, which is what it almost always stood for between the
parts of a title.
"""

import re

_GARBLED = re.compile("â€|Ã.|Â")
# Longest first: a dash garbled through several layers ("Ã¢â‚¬”") cannot be
# decoded mechanically, because one layer turned a byte into a curly quote.
_KNOWN = {"Ã¢â‚¬”": "\u2014", "Ã¢â‚¬â€œ": "\u2013", "â€“": "\u2013", "â€”": "\u2014", "â€˜": "\u2018",
          "â€™": "\u2019", "â€œ": "\u201c", "â€\x9d": "\u201d", "â€¦": "\u2026", "Â ": " ", "Â": ""}


def fix_text(text):
    """The text with double-encoding undone, or unchanged when there is none.

    Some titles were encoded twice over ("Ã¢â‚¬”" for an em dash), so the
    decoding repeats until nothing changes.
    """
    if not text or not (_GARBLED.search(text) or "ï¿½" in text or "�" in text):
        return text
    for _ in range(3):
        if not _GARBLED.search(text):
            break
        try:
            text = text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            for bad, good in _KNOWN.items():
                text = text.replace(bad, good)
            break
    text = text.replace("ï¿½", " - ").replace("�", " - ")
    text = re.sub(r"\s+-\s+(?:-\s+)+", " - ", text)
    return " ".join(text.split())

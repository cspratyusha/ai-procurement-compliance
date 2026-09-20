"""Extract searchable text from an uploaded tender document.

A procurement official has the tender as a PDF or Word file, not as a typed
sentence. This turns that file into a query the retrieval pipeline can use.

Two things make a tender document different from ordinary text:

* It is long. Embedding models truncate at a few hundred tokens, so feeding a
  40-page tender in whole means silently searching its cover page. We extract
  the part that actually describes the goods.
* It is mostly boilerplate. Terms, eligibility, EMD and signature blocks
  dominate by volume, so a naive summary is dominated by legal language rather
  than by the product.
"""

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Guard rails. Enforced here, server-side, not only in the browser.
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_QUERY_CHARS = 2000

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class ExtractionError(Exception):
    """Raised with a message intended to be shown to the user."""


@dataclass
class ExtractedDocument:
    text: str
    """Full extracted text."""

    query: str
    """The portion most likely to describe the goods, for searching."""

    page_count: int = 0
    char_count: int = 0
    method: str = ""
    warnings: List[str] = field(default_factory=list)
    matched_section: Optional[str] = None
    """Heading of the section the query came from, when one was identified."""


# Headings that introduce the part of a tender describing what is being bought.
# Ordered: earlier patterns are preferred when several match.
_SPEC_HEADINGS = [
    r"technical\s+specification",
    r"scope\s+of\s+(?:work|supply)",
    r"specification\s+of\s+(?:goods|items|material)",
    r"description\s+of\s+(?:goods|items|stores)",
    r"material\s+specification",
    r"item\s+description",
    r"bill\s+of\s+quantit",
    r"schedule\s+of\s+requirement",
    r"technical\s+details",
]

# Boilerplate whose presence means a line is not describing a product.
_BOILERPLATE = re.compile(
    r"earnest\s+money|bid\s+security|tender\s+fee|eligibility\s+criteria"
    r"|terms\s+and\s+conditions|arbitration|jurisdiction|affidavit"
    r"|signature\s+of|seal\s+of|annexure\s+[ivx\d]|page\s+\d+\s+of\s+\d+"
    r"|gst\s+registration|pan\s+(?:no|number)|e-?mail|www\.|@",
    re.IGNORECASE,
)

# A line mentioning any of these is probably about the goods.
_TECHNICAL_HINT = re.compile(
    r"\bIS\s?\d{3,5}\b|\bIS[:\s]\d+|conforming\s+to|as\s+per\s+IS"
    r"|sq\.?\s?mm|mm\b|\bkg\b|\bmpa\b|\bvolt|\bkv\b|\bamp|grade\s+\d+"
    r"|\bmm2\b|diameter|thickness|tensile|insulat|galvanis|galvaniz",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    """Normalise whitespace without destroying line structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError(
            "PDF support is not installed on the server (PyMuPDF missing)."
        ) from exc

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(
            "This file could not be opened as a PDF. It may be corrupted or "
            "password-protected."
        ) from exc

    warnings: List[str] = []
    try:
        if document.needs_pass:
            raise ExtractionError(
                "This PDF is password-protected. Remove the password and upload again."
            )
        pages = [page.get_text() for page in document]
        page_count = document.page_count
    finally:
        document.close()

    text = _clean("\n".join(pages))

    if len(text) < 50:
        # A scanned tender has no text layer. OCR would be the answer; we do
        # not have it, and saying so beats returning an empty search.
        raise ExtractionError(
            "No readable text found in this PDF. It is most likely a scan or photo "
            "of a document, which needs optical character recognition (OCR) — not "
            "yet supported. Please paste the specification text instead."
        )

    return ExtractedDocument(
        text=text,
        query="",
        page_count=page_count,
        char_count=len(text),
        method="pdf-text-layer",
        warnings=warnings,
    )


def extract_docx(data: bytes) -> ExtractedDocument:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError(
            "Word support is not installed on the server (python-docx missing)."
        ) from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(
            "This file could not be opened as a Word document. Note that the older "
            ".doc format is not supported — save it as .docx and try again."
        ) from exc

    parts = [p.text for p in document.paragraphs]

    # Tenders keep their specifications in tables far more often than in prose.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    text = _clean("\n".join(parts))
    if len(text) < 20:
        raise ExtractionError("This Word document appears to contain no text.")

    return ExtractedDocument(
        text=text, query="", char_count=len(text), method="docx"
    )


def extract_txt(data: bytes) -> ExtractedDocument:
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = _clean(data.decode(encoding))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExtractionError("This text file could not be decoded.")

    if not text:
        raise ExtractionError("This file is empty.")

    return ExtractedDocument(text=text, query="", char_count=len(text), method="text")


def find_specification_section(text: str) -> tuple[Optional[str], Optional[str]]:
    """Locate the part of a tender that describes the goods.

    Returns (heading, section_text), or (None, None) if no recognised heading
    is present.
    """
    lowered = text.lower()
    for pattern in _SPEC_HEADINGS:
        match = re.search(pattern, lowered)
        if not match:
            continue

        start = match.start()
        # Run to the next all-caps or numbered heading, or 4000 chars.
        remainder = text[start : start + 4000]
        end_match = re.search(
            r"\n\s*(?:\d+\.\s+[A-Z]|[A-Z][A-Z\s]{12,}\n)", remainder[200:]
        )
        section = remainder[: 200 + end_match.start()] if end_match else remainder

        heading_line = text[start : start + 80].split("\n")[0].strip()
        return heading_line, section
    return None, None


def build_query(text: str) -> tuple[str, Optional[str]]:
    """Reduce a document to a search query describing the goods.

    Strategy, in order of preference:
      1. The text under a recognised specification heading.
      2. Otherwise, the lines that look technical and are not boilerplate.
      3. Otherwise, the opening of the document.

    Returns (query, matched_heading).
    """
    heading, section = find_specification_section(text)
    source = section if section else text

    # Filter by paragraph, not by physical line. PDF and DOCX extraction wraps
    # sentences mid-clause, so "Item 3: Ordinary Portland Cement, 43 grade, for
    # the civil works associated with" carries no technical marker on its own
    # line and would be discarded, taking the product with it.
    lines = [ln.strip() for ln in source.split("\n")]
    units: List[str] = []
    current: List[str] = []
    for line in lines:
        if not line:
            if current:
                units.append(" ".join(current))
                current = []
        else:
            current.append(line)
    if current:
        units.append(" ".join(current))

    kept = [
        u
        for u in units
        if len(u) > 12 and not _BOILERPLATE.search(u) and _TECHNICAL_HINT.search(u)
    ]

    if not kept:
        # No technical markers: fall back to non-boilerplate prose.
        kept = [u for u in units if len(u) > 25 and not _BOILERPLATE.search(u)]

    query = " ".join(kept) if kept else source
    query = re.sub(r"\s+", " ", query).strip()

    if len(query) > MAX_QUERY_CHARS:
        query = query[:MAX_QUERY_CHARS].rsplit(" ", 1)[0]

    return query, heading


def extract(filename: str, data: bytes) -> ExtractedDocument:
    """Extract text and build a search query from an uploaded file."""
    if not data:
        raise ExtractionError("The uploaded file is empty.")

    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError(
            f"This file is {len(data) / 1_048_576:.1f} MB. The limit is "
            f"{MAX_FILE_BYTES // 1_048_576} MB."
        )

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ExtractionError(
            f"'{suffix or filename}' is not a supported file type. Supported: {supported}."
        )

    if suffix == ".pdf":
        result = extract_pdf(data)
    elif suffix == ".docx":
        result = extract_docx(data)
    else:
        result = extract_txt(data)

    result.query, result.matched_section = build_query(result.text)

    if not result.query.strip():
        raise ExtractionError(
            "Text was extracted, but no product description could be identified in it. "
            "Please paste the relevant specification text instead."
        )

    if result.matched_section is None:
        result.warnings.append(
            "No 'technical specification' or 'scope of supply' heading was found, so "
            "the whole document was scanned for product details. Check the extracted "
            "text below before relying on the results."
        )

    return result

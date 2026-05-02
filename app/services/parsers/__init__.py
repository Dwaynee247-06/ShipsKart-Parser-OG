"""
parsers/__init__.py
-------------------
Central dispatcher. Given raw file bytes and a file extension,
routes to the correct parser and returns a normalised result dict.

Usage::

    from app.services.parsers import dispatch_parser
    result = dispatch_parser(file_bytes, ".xlsx")
    result = dispatch_parser(file_bytes, ".pdf")
    result = dispatch_parser(file_bytes, ".docx")
"""
from __future__ import annotations

from app.services.parsers.excel import parse_excel
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.word import parse_word

# Maps every supported extension to its parser function
_PARSER_MAP = {
    ".xlsx":  parse_excel,
    ".xlsm":  parse_excel,
    ".xltx":  parse_excel,
    ".xltm":  parse_excel,
    ".docx":  parse_word,
    ".doc":   parse_word,   # best-effort; python-docx handles most .doc via compatibility
    ".pdf":   parse_pdf,
}


def dispatch_parser(file_bytes: bytes, extension: str) -> dict:
    """
    Route file bytes to the correct parser based on file extension.

    :param file_bytes: Raw bytes of the uploaded file.
    :param extension:  Lowercase file extension including dot, e.g. ".xlsx".
    :raises ValueError: If the extension has no registered parser.
    :returns: Parsed result dict (structure identical across all parsers).
    """
    ext = extension.lower()
    parser = _PARSER_MAP.get(ext)
    if parser is None:
        raise ValueError(f"No parser registered for extension '{ext}'.")
    return parser(file_bytes)


__all__ = ["dispatch_parser", "parse_excel", "parse_word", "parse_pdf"]

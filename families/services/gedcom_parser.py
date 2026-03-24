"""GEDCOM parsing and import helpers.

This module re-exports the existing parser/import logic so views can
depend on a dedicated service layer instead of the larger `gedcom.py`
module. It keeps the public surface area explicit and easy to swap
later (e.g., background tasks or alternative parsers).
"""

from ..gedcom import GedcomParser, GedcomParseError, import_gedcom_with_tracking

__all__ = [
    "GedcomParser",
    "GedcomParseError",
    "import_gedcom_with_tracking",
]

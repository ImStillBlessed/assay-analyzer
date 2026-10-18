"""Shared, user-facing table import for the UI and CLI."""

from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

from assaykit.common import AssayInputError


def read_table(source) -> pd.DataFrame:
    name = str(source) if isinstance(source, (str, Path)) else source.name
    suffix = Path(name).suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        raise AssayInputError("Use a .csv or .xlsx file. Save legacy .xls files as .xlsx first.")
    try:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(source) if suffix == ".xlsx" else pd.read_csv(source)
    except (ValueError, OSError, ImportError, UnicodeError, EOFError, BadZipFile) as exc:
        raise AssayInputError(f"Could not read {Path(name).name}: {exc}") from exc

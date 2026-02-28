"""Extraction provider implementations — S0-3."""

from src.ingestion.providers.base import ExtractionOptions, ExtractionProvider
from src.ingestion.providers.local_spreadsheet import LocalSpreadsheetProvider
from src.ingestion.providers.local_pdf import LocalPdfProvider
from src.ingestion.providers.azure_di import AzureDIProvider
from src.ingestion.providers.router import ExtractionRouter

__all__ = [
    "AzureDIProvider",
    "ExtractionOptions",
    "ExtractionProvider",
    "ExtractionRouter",
    "LocalPdfProvider",
    "LocalSpreadsheetProvider",
]

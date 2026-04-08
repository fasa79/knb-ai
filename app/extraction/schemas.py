"""Pydantic schemas for structured data extraction.

These schemas define the expected shape of extracted data from Khazanah's Annual Review.
Used with LLM structured output (constrained JSON generation) for reliable extraction.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Portfolio Companies ───────────────────────────────────────────

class PortfolioCompany(BaseModel):
    """A single portfolio company extracted from the Annual Review."""

    name: str = Field(description="Company name (e.g. 'Tenaga Nasional Berhad')")
    sector: str | None = Field(default=None, description="Industry sector (e.g. 'Power', 'Healthcare', 'Technology')")
    ownership_pct: float | None = Field(default=None, description="Khazanah's ownership stake as percentage (e.g. 21.6)")
    asset_class: str | None = Field(default=None, description="Asset class: Public Markets, Private Markets, Real Assets, etc.")
    description: str | None = Field(default=None, description="Brief role or description from the report")


class PortfolioExtraction(BaseModel):
    """Extracted portfolio companies data."""

    companies: list[PortfolioCompany] = Field(default_factory=list, description="List of portfolio companies")
    extraction_notes: str | None = Field(default=None, description="Any notes about data completeness or caveats")


# ── Financial Metrics ─────────────────────────────────────────────

class FinancialMetric(BaseModel):
    """A single financial metric extracted from the Annual Review."""

    metric_name: str = Field(description="Name of the metric (e.g. 'Total Assets (RAV)', 'TWRR', 'Net Worth Adjusted')")
    value: str = Field(description="The value as stated in the report (e.g. 'RM156 billion', '8.4%', 'RM111 billion')")
    year: str | None = Field(default=None, description="Reporting year (e.g. '2025', 'FY2025')")
    unit: str | None = Field(default=None, description="Unit of measurement (e.g. 'RM billion', '%', 'ratio')")
    source_context: str | None = Field(default=None, description="Brief context of where this metric appears")


class FinancialExtraction(BaseModel):
    """Extracted financial metrics data."""

    metrics: list[FinancialMetric] = Field(default_factory=list, description="List of financial metrics")
    extraction_notes: str | None = Field(default=None, description="Any notes about data completeness or caveats")


# ── Investment Performance ────────────────────────────────────────

class AssetClassPerformance(BaseModel):
    """Performance data for a single asset class."""

    asset_class: str = Field(description="Asset class name (e.g. 'Public Markets: Malaysia')")
    portfolio_weight_pct: float | None = Field(default=None, description="Percentage of total portfolio")
    twrr_latest: str | None = Field(default=None, description="Latest TWRR figure (e.g. '6.5%')")
    twrr_rolling: str | None = Field(default=None, description="Rolling TWRR if available")
    yearly_returns: dict[str, str] | None = Field(default=None, description="Year-by-year TWRR, e.g. {'2024': '34.3%', '2023': '4.5%'}")
    role: str | None = Field(default=None, description="Role of asset class in portfolio")


class InvestmentExtraction(BaseModel):
    """Extracted investment performance data."""

    asset_classes: list[AssetClassPerformance] = Field(default_factory=list, description="Performance by asset class")
    extraction_notes: str | None = Field(default=None, description="Any notes about data completeness or caveats")


# ── Key Highlights ────────────────────────────────────────────────

class KeyHighlight(BaseModel):
    """A key highlight or initiative from the Annual Review."""

    category: str = Field(description="Category: Financial, Strategic, ESG, Community, Governance, etc.")
    title: str = Field(description="Short title or label for the highlight")
    description: str = Field(description="Description of the highlight")
    value: str | None = Field(default=None, description="Associated figure or value if applicable")
    year: str | None = Field(default=None, description="Year the highlight relates to")


class HighlightsExtraction(BaseModel):
    """Extracted key highlights."""

    highlights: list[KeyHighlight] = Field(default_factory=list, description="List of key highlights")
    extraction_notes: str | None = Field(default=None, description="Any notes about data completeness or caveats")


# ── Custom / Free-form Extraction ─────────────────────────────────

class CustomExtractionItem(BaseModel):
    """A single item from a user-defined extraction request."""

    field_name: str = Field(description="The name/label of the extracted field")
    value: str = Field(description="The extracted value")
    source_context: str | None = Field(default=None, description="Where this was found in the report")


class CustomExtraction(BaseModel):
    """Free-form extraction results from user-defined queries."""

    items: list[CustomExtractionItem] = Field(default_factory=list, description="Extracted items")
    extraction_notes: str | None = Field(default=None, description="Any notes about completeness")


# ── Combined Extraction Result ────────────────────────────────────

class FullExtraction(BaseModel):
    """Combined extraction containing all structured data types."""

    portfolio: PortfolioExtraction | None = None
    financials: FinancialExtraction | None = None
    investment_performance: InvestmentExtraction | None = None
    highlights: HighlightsExtraction | None = None


# ── Registry for extraction types ─────────────────────────────────

EXTRACTION_SCHEMAS = {
    "portfolio": PortfolioExtraction,
    "financials": FinancialExtraction,
    "investment_performance": InvestmentExtraction,
    "highlights": HighlightsExtraction,
    "custom": CustomExtraction,
}

EXTRACTION_TYPES = list(EXTRACTION_SCHEMAS.keys()) + ["all"]

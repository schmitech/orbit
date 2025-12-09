"""
CSV Processor

Handles CSV files with configurable output modes:
- Full data mode: For small files, includes all rows to enable exact lookups
- Summary mode: For large files, provides token-efficient schema and samples

Configuration is read from config.yaml under files.processing.csv
"""

import logging
from typing import Dict, Any, List, Optional
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    import pandas as pd
    from io import StringIO
    CSV_AVAILABLE = True
except ImportError:
    CSV_AVAILABLE = False
    logger.warning("pandas not available. CSV processing disabled.")

# Default values (used when config is not provided)
DEFAULT_FULL_DATA_ROW_THRESHOLD = 200
DEFAULT_MAX_PREVIEW_ROWS = 5
DEFAULT_MAX_COLUMN_WIDTH = 50
DEFAULT_MAX_COLUMNS_FULL = 15


class CSVProcessor(FileProcessor):
    """
    Processor for CSV files with configurable output modes.

    For small files (<=full_data_row_threshold rows):
    - Includes ALL rows to enable exact lookups (e.g., "find ID X")

    For large files:
    - Token-efficient summary with schema and sample rows

    Configuration (from config.yaml files.processing.csv):
    - full_data_row_threshold: Max rows for full data mode (default: 200)
    - max_preview_rows: Sample rows in summary mode (default: 5)
    - max_column_width: Max chars per value before truncation (default: 50)
    - max_columns_full: Max columns to show in detail (default: 15)

    Supports: text/csv
    Requires: pandas
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize CSV processor with optional configuration.

        Args:
            config: Configuration dictionary (typically from config.yaml)
        """
        super().__init__()
        self._load_config(config)

    def _load_config(self, config: Optional[Dict[str, Any]] = None):
        """Load settings from config or use defaults."""
        csv_config = {}
        if config:
            csv_config = config.get('files', {}).get('processing', {}).get('csv', {})

        self.full_data_row_threshold = csv_config.get(
            'full_data_row_threshold', DEFAULT_FULL_DATA_ROW_THRESHOLD
        )
        self.max_preview_rows = csv_config.get(
            'max_preview_rows', DEFAULT_MAX_PREVIEW_ROWS
        )
        self.max_column_width = csv_config.get(
            'max_column_width', DEFAULT_MAX_COLUMN_WIDTH
        )
        self.max_columns_full = csv_config.get(
            'max_columns_full', DEFAULT_MAX_COLUMNS_FULL
        )

        logger.debug(
            f"CSVProcessor config: full_data_row_threshold={self.full_data_row_threshold}, "
            f"max_preview_rows={self.max_preview_rows}"
        )

    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return CSV_AVAILABLE and mime_type.lower() == 'text/csv'

    def _truncate_value(self, value: Any, max_len: int = None) -> str:
        """Truncate long values with ellipsis."""
        if max_len is None:
            max_len = self.max_column_width
        s = str(value)
        if len(s) <= max_len:
            return s
        return s[:max_len - 3] + "..."

    def _get_column_type_info(self, series: "pd.Series") -> Dict[str, Any]:
        """Get type and statistics for a column."""
        info = {
            "dtype": str(series.dtype),
            "non_null": int(series.count()),
            "null_count": int(series.isna().sum()),
        }

        # Add type-specific stats
        if pd.api.types.is_numeric_dtype(series):
            info["type"] = "numeric"
            if series.count() > 0:
                info["min"] = float(series.min()) if not pd.isna(series.min()) else None
                info["max"] = float(series.max()) if not pd.isna(series.max()) else None
                info["mean"] = round(float(series.mean()), 2) if not pd.isna(series.mean()) else None
        elif pd.api.types.is_datetime64_any_dtype(series):
            info["type"] = "datetime"
            if series.count() > 0:
                info["min"] = str(series.min())
                info["max"] = str(series.max())
        else:
            info["type"] = "text"
            # For text columns, show unique value count and sample values
            unique_count = series.nunique()
            info["unique_values"] = unique_count
            if unique_count <= 10:
                # Categorical-like: show all unique values
                info["values"] = series.dropna().unique().tolist()[:10]
            elif unique_count <= 50:
                # Semi-categorical: show sample
                info["sample_values"] = series.dropna().unique().tolist()[:5]

        return info

    def _format_column_info(self, col_name: str, col_info: Dict[str, Any]) -> str:
        """Format column information as a compact string."""
        parts = [f"  {col_name}"]

        if col_info["type"] == "numeric":
            parts.append(f"({col_info['dtype']})")
            if col_info.get("min") is not None:
                parts.append(f"range: {col_info['min']}-{col_info['max']}")
            if col_info.get("mean") is not None:
                parts.append(f"mean: {col_info['mean']}")
        elif col_info["type"] == "datetime":
            parts.append("(datetime)")
            if col_info.get("min"):
                parts.append(f"range: {col_info['min']} to {col_info['max']}")
        else:
            parts.append("(text)")
            if "unique_values" in col_info:
                parts.append(f"{col_info['unique_values']} unique")
            if "values" in col_info and col_info["values"]:
                vals = [self._truncate_value(v, 20) for v in col_info["values"][:5]]
                parts.append(f"values: [{', '.join(vals)}]")
            elif "sample_values" in col_info:
                vals = [self._truncate_value(v, 20) for v in col_info["sample_values"]]
                parts.append(f"e.g.: [{', '.join(vals)}]")

        if col_info["null_count"] > 0:
            parts.append(f"({col_info['null_count']} nulls)")

        return " ".join(parts)

    def _format_row_compact(self, row: "pd.Series", columns: List[str]) -> str:
        """Format a row compactly."""
        parts = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                parts.append(f"{col}=null")
            else:
                parts.append(f"{col}={self._truncate_value(val, 30)}")
        return " | ".join(parts)

    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """
        Extract text representation from CSV.

        For small files (<=FULL_DATA_ROW_THRESHOLD rows):
        - Includes ALL rows to enable exact lookups (e.g., "find ID X")

        For large files:
        - Token-efficient summary with schema and sample rows
        """
        if not CSV_AVAILABLE:
            raise ImportError("pandas not available")

        logger.debug(f"CSVProcessor.extract_text() called for file: {filename or 'unknown'}")

        try:
            csv_text = file_data.decode('utf-8')
        except UnicodeDecodeError:
            csv_text = file_data.decode('latin-1')

        df = pd.read_csv(StringIO(csv_text))
        lines = []

        # Header summary
        lines.append(f"CSV: {len(df)} rows × {len(df.columns)} columns")
        lines.append("")

        # Column names
        columns = df.columns.tolist()
        lines.append(f"Columns: {', '.join(columns)}")
        lines.append("")

        # For small files, include ALL data to enable exact lookups
        if len(df) <= self.full_data_row_threshold:
            logger.debug(f"CSVProcessor: Small file ({len(df)} rows), including all data for exact lookups")
            lines.append("Data:")

            for i, (_, row) in enumerate(df.iterrows()):
                # Format each row with all columns for searchability
                row_parts = []
                for col in columns:
                    val = row[col]
                    if pd.isna(val):
                        row_parts.append(f"{col}=null")
                    else:
                        row_parts.append(f"{col}={self._truncate_value(val, 50)}")
                lines.append(f"  Row {i}: {' | '.join(row_parts)}")
        else:
            # Large file: use token-efficient summary
            logger.debug(f"CSVProcessor: Large file ({len(df)} rows), using summary mode")

            # Column schema with statistics
            lines.append("Column details:")
            columns_to_show = columns[:self.max_columns_full] if len(columns) > self.max_columns_full else columns

            for col in columns_to_show:
                col_info = self._get_column_type_info(df[col])
                lines.append(self._format_column_info(col, col_info))

            if len(columns) > self.max_columns_full:
                remaining = columns[self.max_columns_full:]
                lines.append(f"  + {len(remaining)} more columns")

            # Sample rows
            lines.append("")
            lines.append("Sample data:")
            preview_cols = columns_to_show[:8] if len(columns_to_show) > 8 else columns_to_show

            for i, (_, row) in enumerate(df.head(self.max_preview_rows).iterrows()):
                lines.append(f"  Row {i}: {self._format_row_compact(row, preview_cols)}")

            if len(df) > self.max_preview_rows:
                lines.append(f"  ... ({len(df) - self.max_preview_rows - 1} more rows)")
                last_row = df.iloc[-1]
                lines.append(f"  Row {len(df)-1}: {self._format_row_compact(last_row, preview_cols)}")

        result = "\n".join(lines)
        logger.debug(f"CSVProcessor extracted {len(result)} chars from {filename or 'unknown'}")
        return result

    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from CSV."""
        metadata = await super().extract_metadata(file_data, filename)

        if not CSV_AVAILABLE:
            return metadata

        try:
            csv_text = file_data.decode('utf-8')
            df = pd.read_csv(StringIO(csv_text))

            # Get column types
            column_types = {}
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    column_types[col] = "numeric"
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    column_types[col] = "datetime"
                else:
                    column_types[col] = "text"

            metadata.update({
                'row_count': len(df),
                'column_count': len(df.columns),
                'columns': df.columns.tolist(),
                'column_types': column_types,
                'mime_type': 'text/csv',
            })

        except Exception as e:
            logger.warning(f"Error extracting CSV metadata: {e}")

        return metadata

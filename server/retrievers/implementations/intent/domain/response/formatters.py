"""
Formatting helpers for response generation
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from ...domain import DomainConfig, FieldConfig

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Handles deterministic formatting of result data"""

    def __init__(self, domain_config: DomainConfig):
        """Initialize formatter with domain configuration"""
        self.domain_config = domain_config

    def format_results(self, results: List[Dict], template: Dict) -> List[Dict]:
        """Format results according to domain field configurations"""
        formatted = []

        for result in results:
            formatted_result = self._format_single_result(result)
            formatted.append(formatted_result)

        return formatted

    def _format_single_result(self, result: Dict) -> Dict:
        """Format a single result row"""
        formatted_result = {}

        for key, value in result.items():
            # Find field configuration
            field_config = self._find_field_config(key)

            if field_config and field_config.display_format:
                formatted_value = self._apply_format(value, field_config.display_format)
                formatted_result[key] = formatted_value
            else:
                formatted_result[key] = value

        return formatted_result

    def _find_field_config(self, field_name: str) -> Optional[FieldConfig]:
        """Find field configuration across all entities"""
        for entity in self.domain_config.entities.values():
            if field_name in entity.fields:
                return entity.fields[field_name]
        return None

    def _apply_format(self, value: Any, display_format: str) -> str:
        """Apply display formatting to a value"""
        if value is None:
            return ""

        formatters = {
            "currency": self._format_currency,
            "percentage": self._format_percentage,
            "date": self._format_date,
            "datetime": self._format_datetime,
            "phone": self._format_phone,
            "email": lambda v: str(v),  # Keep emails as-is
            "title_case": lambda v: str(v).title(),
            "upper_case": lambda v: str(v).upper(),
            "lower_case": lambda v: str(v).lower(),
        }

        formatter = formatters.get(display_format)
        if formatter:
            try:
                return formatter(value)
            except Exception as e:
                logger.debug(f"Formatting error for {display_format}: {e}")
                return str(value)

        return str(value)

    def _format_currency(self, value: Any) -> str:
        """Format value as currency"""
        try:
            if isinstance(value, (int, float)):
                return f"${value:,.2f}"
            elif isinstance(value, str):
                # Try to parse string as number
                clean_value = value.replace('$', '').replace(',', '').strip()
                num_value = float(clean_value)
                return f"${num_value:,.2f}"
        except (ValueError, TypeError):
            pass
        return str(value)

    def _format_percentage(self, value: Any) -> str:
        """Format value as percentage"""
        try:
            if isinstance(value, (int, float)):
                # Assume value is already in percentage form (e.g., 25 for 25%)
                if value < 1:
                    return f"{value:.1%}"
                else:
                    return f"{value:.1f}%"
        except (ValueError, TypeError):
            pass
        return str(value)

    def _format_date(self, value: Any) -> str:
        """Format date value"""
        try:
            if isinstance(value, str):
                # Parse ISO format or other common formats
                dt = None
                for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                    try:
                        dt = datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt)
                        break
                    except ValueError:
                        continue

                if dt:
                    return dt.strftime("%B %d, %Y")

            elif isinstance(value, date):
                return value.strftime("%B %d, %Y")

        except Exception as e:
            logger.debug(f"Date formatting error: {e}")

        return str(value)

    def _format_datetime(self, value: Any) -> str:
        """Format datetime value"""
        try:
            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.strftime("%B %d, %Y at %I:%M %p")
            elif isinstance(value, datetime):
                return value.strftime("%B %d, %Y at %I:%M %p")
        except Exception as e:
            logger.debug(f"Datetime formatting error: {e}")

        return str(value)

    def _format_phone(self, value: Any) -> str:
        """Format phone number"""
        if not value:
            return ""

        # Simple phone formatting for US numbers
        phone = str(value).replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

        # Remove country code if present
        if phone.startswith('+1'):
            phone = phone[2:]
        elif phone.startswith('1') and len(phone) == 11:
            phone = phone[1:]

        if len(phone) == 10:
            return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"

        return str(value)

    def format_table_data(self, results: List[Dict], columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """Format results for table display"""
        if not results:
            return {"rows": [], "columns": []}

        # Determine columns to display
        if not columns:
            columns = list(results[0].keys()) if results else []

        # Format each row
        formatted_rows = []
        for result in results:
            row = []
            for col in columns:
                value = result.get(col, "")
                # Apply formatting if we have field config
                field_config = self._find_field_config(col)
                if field_config and field_config.display_format:
                    value = self._apply_format(value, field_config.display_format)
                row.append(value)
            formatted_rows.append(row)

        # Get display names for columns
        display_columns = []
        for col in columns:
            field_config = self._find_field_config(col)
            if field_config and field_config.display_name:
                display_columns.append(field_config.display_name)
            else:
                # Convert snake_case to Title Case
                display_columns.append(col.replace('_', ' ').title())

        return {
            "columns": display_columns,
            "rows": formatted_rows
        }

    def format_summary_data(self, results: List[Dict], summary_fields: Optional[List[str]] = None) -> str:
        """Format results for summary display"""
        if not results:
            return "No results to summarize."

        # Determine which fields to include in summary
        if not summary_fields and results:
            # Use important fields based on domain config
            summary_fields = self._get_summary_fields(results[0])

        summaries = []
        for idx, result in enumerate(results[:5], 1):  # Limit to first 5 results
            summary_parts = []

            for field in summary_fields:
                if field in result:
                    value = result[field]
                    field_config = self._find_field_config(field)

                    # Format the value
                    if field_config and field_config.display_format:
                        value = self._apply_format(value, field_config.display_format)

                    # Get display name
                    display_name = field
                    if field_config and field_config.display_name:
                        display_name = field_config.display_name

                    summary_parts.append(f"{display_name}: {value}")

            if summary_parts:
                summaries.append(f"{idx}. " + ", ".join(summary_parts))

        return "\n".join(summaries)

    def _get_summary_fields(self, sample_result: Dict) -> List[str]:
        """Determine which fields are most important for summary"""
        summary_fields = []

        # Priority order for common field types
        priority_patterns = [
            ('id', ['id', 'number', 'code']),
            ('name', ['name', 'title', 'description']),
            ('amount', ['amount', 'total', 'price', 'cost']),
            ('date', ['date', 'created', 'updated']),
            ('status', ['status', 'state', 'condition'])
        ]

        for category, patterns in priority_patterns:
            for field in sample_result.keys():
                field_lower = field.lower()
                if any(pattern in field_lower for pattern in patterns):
                    if field not in summary_fields:
                        summary_fields.append(field)
                        break

        # If we don't have enough fields, add more
        if len(summary_fields) < 3:
            for field in sample_result.keys():
                if field not in summary_fields:
                    summary_fields.append(field)
                if len(summary_fields) >= 5:
                    break

        return summary_fields[:5]  # Limit to 5 fields
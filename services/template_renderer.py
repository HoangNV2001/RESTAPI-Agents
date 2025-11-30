"""
Template Renderer Service - Render response templates with API data
"""
from typing import Any

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError


class TemplateRenderer:
    """Render Jinja2 templates with API response data"""
    
    def __init__(self):
        self.env = Environment(
            loader=BaseLoader(),
            autoescape=True
        )
        
        # Add custom filters
        self.env.filters["format_number"] = self._format_number
        self.env.filters["format_currency"] = self._format_currency
        self.env.filters["format_date"] = self._format_date
        self.env.filters["truncate_text"] = self._truncate_text
        self.env.filters["json_pretty"] = self._json_pretty
    
    def render(
        self,
        template: str,
        data: dict[str, Any],
        error_template: str | None = None
    ) -> str:
        """Render template with data"""
        try:
            tpl = self.env.from_string(template)
            return tpl.render(**data)
        
        except TemplateSyntaxError as e:
            if error_template:
                return self.render(
                    error_template,
                    {"error": f"Template syntax error: {e.message}"}
                )
            return f"Template error: {e.message}"
        
        except UndefinedError as e:
            if error_template:
                return self.render(
                    error_template,
                    {"error": f"Missing data: {e.message}"}
                )
            return f"Missing data: {e.message}"
        
        except Exception as e:
            if error_template:
                return self.render(
                    error_template,
                    {"error": str(e)}
                )
            return f"Render error: {str(e)}"
    
    def render_api_response(
        self,
        template: str,
        api_results: list[dict[str, Any]],
        error_template: str = "Xin lỗi, không thể lấy thông tin. Lỗi: {{ error }}",
        no_data_template: str = "Không tìm thấy dữ liệu phù hợp."
    ) -> str:
        """Render template with multiple API results"""
        
        # Check for errors
        errors = [r for r in api_results if not r.get("success")]
        if errors and not any(r.get("success") for r in api_results):
            error_messages = [r.get("error", "Unknown error") for r in errors]
            return self.render(error_template, {"error": "; ".join(error_messages)})
        
        # Collect successful data
        data = {}
        for i, result in enumerate(api_results):
            if result.get("success") and result.get("data"):
                # Use first result as main data
                if i == 0:
                    if isinstance(result["data"], dict):
                        data.update(result["data"])
                    data["data"] = result["data"]
                
                # Add subsequent results with index
                data[f"result_{i}"] = result["data"]
        
        if not data:
            return no_data_template
        
        # Add helper data
        data["_results"] = api_results
        data["_success_count"] = sum(1 for r in api_results if r.get("success"))
        data["_error_count"] = len(errors)
        
        return self.render(template, data, error_template)
    
    def validate_template(self, template: str) -> tuple[bool, str | None]:
        """Validate template syntax"""
        try:
            self.env.parse(template)
            return True, None
        except TemplateSyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.message}"
    
    def extract_variables(self, template: str) -> list[str]:
        """Extract variable names from template"""
        from jinja2 import meta
        
        try:
            ast = self.env.parse(template)
            return list(meta.find_undeclared_variables(ast))
        except TemplateSyntaxError:
            return []
    
    # Custom filters
    @staticmethod
    def _format_number(value, decimal_places: int = 2) -> str:
        """Format number with thousand separators"""
        try:
            num = float(value)
            if decimal_places == 0:
                return f"{int(num):,}"
            return f"{num:,.{decimal_places}f}"
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def _format_currency(
        value,
        currency: str = "VND",
        decimal_places: int = 0
    ) -> str:
        """Format as currency"""
        try:
            num = float(value)
            formatted = f"{num:,.{decimal_places}f}"
            
            if currency == "VND":
                return f"{formatted} ₫"
            elif currency == "USD":
                return f"${formatted}"
            elif currency == "EUR":
                return f"€{formatted}"
            else:
                return f"{formatted} {currency}"
        except (ValueError, TypeError):
            return str(value)
    
    @staticmethod
    def _format_date(value, format: str = "%d/%m/%Y") -> str:
        """Format date string"""
        from datetime import datetime
        
        if isinstance(value, datetime):
            return value.strftime(format)
        
        # Try to parse common date formats
        formats_to_try = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        
        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(str(value), fmt)
                return dt.strftime(format)
            except ValueError:
                continue
        
        return str(value)
    
    @staticmethod
    def _truncate_text(value, length: int = 100, suffix: str = "...") -> str:
        """Truncate text to specified length"""
        text = str(value)
        if len(text) <= length:
            return text
        return text[:length - len(suffix)] + suffix
    
    @staticmethod
    def _json_pretty(value, indent: int = 2) -> str:
        """Pretty print JSON"""
        import json
        try:
            return json.dumps(value, indent=indent, ensure_ascii=False)
        except (ValueError, TypeError):
            return str(value)


# Pre-defined templates for common scenarios
COMMON_TEMPLATES = {
    "simple_value": "{{ data }}",
    
    "list_items": """{% for item in items %}
- {{ item }}
{% endfor %}""",
    
    "key_value_pairs": """{% for key, value in data.items() %}
**{{ key }}**: {{ value }}
{% endfor %}""",
    
    "table": """| {% for col in columns %}{{ col }} | {% endfor %}
| {% for col in columns %}--- | {% endfor %}
{% for row in rows %}| {% for col in columns %}{{ row[col] }} | {% endfor %}
{% endfor %}""",
    
    "product_info": """📦 **{{ name }}**
- Giá: {{ price | format_currency }}
- Mô tả: {{ description | truncate_text(200) }}
- Tồn kho: {{ stock }} sản phẩm""",
    
    "order_status": """📋 **Đơn hàng #{{ order_id }}**
- Trạng thái: {{ status }}
- Ngày đặt: {{ created_at | format_date }}
- Tổng tiền: {{ total | format_currency }}""",
    
    "user_info": """👤 **{{ name }}**
- Email: {{ email }}
- Điện thoại: {{ phone }}
- Địa chỉ: {{ address }}""",
    
    "error": "❌ {{ error }}",
    
    "no_data": "Không tìm thấy dữ liệu phù hợp với yêu cầu của bạn."
}
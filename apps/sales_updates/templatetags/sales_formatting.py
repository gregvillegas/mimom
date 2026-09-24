from __future__ import annotations

from decimal import Decimal

from django import template
from django.utils.html import format_html

from apps.sales_updates.models import CURRENCY_PHP
from apps.sales_updates.services import TWO_PLACES, _q
from apps.sales_updates.services import currency_format as _currency_format

register = template.Library()


@register.filter(name="currency")
def currency_filter(value, currency=CURRENCY_PHP):
    """Format a money value with currency symbol, thousands separator, 2 decimals."""
    if value is None or value == "":
        value = Decimal("0")
    return _currency_format(value, currency, with_sign=False, negative_parens=False)


@register.filter(name="currency_signed")
def currency_signed_filter(value, currency=CURRENCY_PHP):
    if value is None or value == "":
        value = Decimal("0")
    return _currency_format(value, currency, with_sign=True, negative_parens=False)


@register.filter(name="currency_parens")
def currency_parens_filter(value, currency=CURRENCY_PHP):
    if value is None or value == "":
        value = Decimal("0")
    return _currency_format(value, currency, with_sign=False, negative_parens=True)


@register.filter(name="percentage")
def percentage_filter(value, digits: str | int = 1):
    try:
        digits_i = int(digits)
    except (TypeError, ValueError):
        digits_i = 1
    if value is None or value == "":
        return f"{0:.{digits_i}f}%"
    d = _q(value) if not isinstance(value, Decimal) else value.quantize(TWO_PLACES)
    quant = Decimal("1") / Decimal(10**digits_i)
    from decimal import ROUND_HALF_UP

    formatted = format(d.quantize(quant, rounding=ROUND_HALF_UP), "f")
    return f"{formatted}%"


@register.filter(name="negative_class")
def negative_class(value) -> str:
    if value is None or value == "":
        return ""
    try:
        numeric = Decimal(str(value))
    except Exception:
        return ""
    if numeric < 0:
        return "text-danger"
    if numeric > 0:
        return "text-success"
    return ""


@register.simple_tag
def currency_cell(value, currency=CURRENCY_PHP, *, signed: bool = False, parens: bool = False):
    """Render a <span class=negative_class> with formatted currency."""
    if value is None or value == "":
        numeric = Decimal("0")
    else:
        try:
            numeric = Decimal(str(value))
        except Exception:
            numeric = Decimal("0")
    cls = negative_class(numeric)
    if parens:
        text = _currency_format(numeric, currency, with_sign=False, negative_parens=True)
    elif signed:
        text = _currency_format(numeric, currency, with_sign=True, negative_parens=False)
    else:
        text = _currency_format(numeric, currency, with_sign=False, negative_parens=False)
    if cls:
        return format_html('<span class="{}">{}</span>', cls, text)
    return format_html("{}", text)

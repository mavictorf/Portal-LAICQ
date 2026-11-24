"""Funções auxiliares sem dependência do restante do app."""
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import markdown as _markdown
import nh3
from markupsafe import Markup

TZ = ZoneInfo("America/Fortaleza")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "del",
    "code", "pre", "blockquote", "a", "img", "table", "thead", "tbody", "tr",
    "th", "td",
}
_ATTRS = {"a": {"href", "title"}, "img": {"src", "alt", "title"}}

_CORES = {"estudo": "navy", "workshop": "gold", "projeto": "green"}


def hoje() -> date:
    return datetime.now(TZ).date()


def para_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:  # SQLite devolve datetimes sem fuso
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def fmt_data(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        v = para_local(v).date()
    return v.strftime("%d/%m/%Y")


def fmt_datahora(v) -> str:
    if v is None:
        return ""
    return para_local(v).strftime("%d/%m/%Y %H:%M")


def cor_rotulo(rotulo) -> str:
    return _CORES.get((rotulo or "").strip().lower(), "")


def render_md(texto) -> Markup:
    """Markdown -> HTML sanitizado (só tags da lista branca)."""
    html = _markdown.markdown(texto or "", extensions=["extra", "sane_lists"])
    limpo = nh3.clean(
        html,
        tags=_TAGS,
        attributes=_ATTRS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
    return Markup(limpo)

from __future__ import annotations

from datetime import datetime

from . import templates

_MD_SPECIAL = "\\`*_[]()"


def md_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    out = []
    for ch in s:
        if ch in _MD_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def render_currency_screen_text(rates) -> str:
    def pick(code_a: int, code_b: int = 980):
        for r in rates:
            if int(getattr(r, "currencyCodeA", -1)) == int(code_a) and int(
                getattr(r, "currencyCodeB", -1)
            ) == int(code_b):
                return r
        return None

    def fmt_rate(r) -> str:
        rb = getattr(r, "rateBuy", None)
        rs = getattr(r, "rateSell", None)
        rc = getattr(r, "rateCross", None)
        parts = []
        if rc is not None:
            parts.append(f"cross {float(rc):.4f}")
        if rb is not None:
            parts.append(f"buy {float(rb):.4f}")
        if rs is not None:
            parts.append(f"sell {float(rs):.4f}")
        return ", ".join(parts) if parts else "немає даних"

    updated_ts = 0
    for r in rates:
        try:
            updated_ts = max(updated_ts, int(getattr(r, "date", 0) or 0))
        except Exception:
            pass

    updated = "—"
    if updated_ts > 0:
        updated = datetime.fromtimestamp(updated_ts).isoformat(timespec="seconds")

    usd = pick(840)
    eur = pick(978)
    pln = pick(985)

    usd_s = md_escape(fmt_rate(usd)) if usd else None
    eur_s = md_escape(fmt_rate(eur)) if eur else None
    pln_s = md_escape(fmt_rate(pln)) if pln else None

    return templates.currency_screen_text(md_escape(updated), usd_s, eur_s, pln_s)

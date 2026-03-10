from __future__ import annotations

from collections.abc import Mapping

from mono_ai_budget_bot.analytics.coverage import CoverageStatus, classify_coverage
from mono_ai_budget_bot.bot import templates
from mono_ai_budget_bot.bot.formatting import format_money_uah_pretty, format_ts_local
from mono_ai_budget_bot.nlq.executor_support import normalize_coverage_status_for_nlq
from mono_ai_budget_bot.reports.config import ReportsConfig
from mono_ai_budget_bot.storage.reports_store import ReportsStore

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


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _period_to_cfg_period(period: str) -> str:
    if period == "today":
        return "daily"
    if period == "week":
        return "weekly"
    if period == "month":
        return "monthly"
    if period == "custom:daily":
        return "daily"
    if period == "custom:weekly":
        return "weekly"
    if period == "custom:monthly":
        return "monthly"
    return period


def _render_coverage_warning(facts: dict) -> str | None:
    cov = facts.get("coverage")
    if not isinstance(cov, dict):
        return None

    try:
        cov_from = int(cov["coverage_from_ts"])
        cov_to = int(cov["coverage_to_ts"])
        req_from = int(cov["requested_from_ts"])
        req_to = int(cov["requested_to_ts"])
    except Exception:
        return None

    has_rows = False
    totals = facts.get("totals")
    if isinstance(totals, Mapping):
        try:
            has_rows = any(
                abs(float(totals.get(key) or 0.0)) > 0.0
                for key in (
                    "real_spend_total_uah",
                    "spend_total_uah",
                    "income_total_uah",
                    "transfer_in_total_uah",
                    "transfer_out_total_uah",
                )
            )
        except Exception:
            has_rows = False

    status = classify_coverage(
        requested_from_ts=req_from,
        requested_to_ts=req_to,
        coverage_window=(cov_from, cov_to),
    )
    if cov_from <= req_from:
        status = normalize_coverage_status_for_nlq(
            status,
            (cov_from, cov_to),
            req_to,
            has_rows_in_window=has_rows,
        )
    if status != CoverageStatus.partial:
        return None

    d1 = format_ts_local(cov_from)[:10]
    d2 = format_ts_local(cov_to)[:10]
    return templates.warning(f"Дані неповні для запитаного періоду. Coverage: {d1} — {d2}.")


def _render_totals_section(facts: dict) -> str | None:
    totals = _safe_get(facts, ["totals"], {}) or {}

    real_spend = float(totals.get("real_spend_total_uah", 0.0))
    spend = float(totals.get("spend_total_uah", 0.0))
    income = float(totals.get("income_total_uah", 0.0))
    tr_in = float(totals.get("transfer_in_total_uah", 0.0))
    tr_out = float(totals.get("transfer_out_total_uah", 0.0))

    summary_lines = [
        f"💸 Реальні витрати: *{md_escape(format_money_uah_pretty(real_spend))}*",
        f"🧾 Всі списання: {md_escape(format_money_uah_pretty(spend))}",
        f"💰 Надходження: {md_escape(format_money_uah_pretty(income))}",
        f"🔁 Перекази: +{md_escape(format_money_uah_pretty(tr_in))} / -{md_escape(format_money_uah_pretty(tr_out))}",
    ]
    return templates.section("Факти", summary_lines)


def _render_uncategorized_block(facts: dict) -> str | None:
    totals = _safe_get(facts, ["totals"], {}) or {}
    real_spend = float(totals.get("real_spend_total_uah", 0.0) or 0.0)
    uncategorized = float(facts.get("uncategorized_real_spend_total_uah", 0.0) or 0.0)

    if real_spend <= 0.0 or uncategorized <= 0.0:
        return None

    uncategorized_share = round((uncategorized / real_spend) * 100.0, 1)
    categorized_share = round(max(0.0, 100.0 - uncategorized_share), 1)

    lines = [
        f"• Ще не розкладено по категоріях: *{md_escape(format_money_uah_pretty(uncategorized))}* ({md_escape(f'{uncategorized_share:.1f}%')} реальних витрат)",
        f"• Категоризована частина зараз покриває приблизно {md_escape(f'{categorized_share:.1f}%')} реальних витрат.",
        "• Через це сума часток у категоріях може бути меншою за 100%.",
    ]
    return templates.section("Некатегоризовані витрати", lines)


def _render_categories_deep_block(facts: dict) -> str | None:
    categories = facts.get("categories_real_spend") or {}
    shares = facts.get("category_shares_real_spend") or {}

    if not isinstance(categories, dict) or not categories:
        return None

    cmp_categories = _safe_get(facts, ["comparison", "categories"], {})
    if not isinstance(cmp_categories, dict):
        cmp_categories = {}

    rows: list[tuple[str, float, float, float | None, float | None]] = []
    for cat, amt in categories.items():
        if cat is None:
            continue
        cat_s = str(cat)
        cur = float(amt or 0.0)
        share = float(shares.get(cat_s, 0.0) or 0.0)

        delta: float | None = None
        pct: float | None = None
        if cat_s in cmp_categories and isinstance(cmp_categories.get(cat_s), dict):
            v = cmp_categories[cat_s]
            delta = float(v.get("delta_uah", 0.0))
            pct_v = v.get("pct_change")
            pct = None if pct_v is None else float(pct_v)

        rows.append((cat_s, cur, share, delta, pct))

    rows.sort(key=lambda x: x[1], reverse=True)
    top_by_spend = rows[:7]

    spend_lines: list[str] = []
    spend_lines.append("*За часткою витрат:*")
    for cat, cur, share, delta, pct in top_by_spend:
        base = f"• {md_escape(cat)} — {md_escape(format_money_uah_pretty(cur))} ({md_escape(f'{share:.1f}%')})"
        if delta is None:
            spend_lines.append(base)
            continue

        sign = "+" if delta >= 0 else ""
        pct_txt = "—" if pct is None else f"{pct:+.2f}%"
        spend_lines.append(
            f"{base} | Δ {md_escape(sign + format_money_uah_pretty(delta))} ({md_escape(pct_txt)})"
        )

    movers_lines: list[str] = []
    movers = [x for x in rows if x[3] is not None and abs(float(x[3] or 0.0)) >= 1.0]
    movers.sort(key=lambda x: abs(float(x[3] or 0.0)), reverse=True)
    movers = movers[:5]

    if movers:
        movers_lines.append("")
        movers_lines.append("*Топ зміни vs попередній період:*")
        for cat, _, _, delta, pct in movers:
            d = float(delta or 0.0)
            sign = "+" if d >= 0 else ""
            pct_txt = "—" if pct is None else f"{float(pct):+.2f}%"
            movers_lines.append(
                f"• {md_escape(cat)}: Δ {md_escape(sign + format_money_uah_pretty(d))} ({md_escape(pct_txt)})"
            )

    return templates.section("Категорії детально", [*spend_lines, *movers_lines])


def _render_breakdowns_section(facts: dict) -> str | None:
    parts: list[str] = []

    top_named = facts.get("top_categories_named_real_spend", []) or []
    if top_named:
        items: list[str] = []
        for i, row in enumerate(top_named[:5], start=1):
            cat = md_escape(str(row.get("category", "—")))
            amt = float(row.get("amount_uah", 0.0))
            items.append(f"{i}. {cat} — {md_escape(format_money_uah_pretty(amt))}")
        parts.append(templates.section("Топ категорій", items))

    top_merchants = facts.get("top_merchants_real_spend", []) or []
    if top_merchants:
        items2: list[str] = []
        for i, row in enumerate(top_merchants[:5], start=1):
            m = md_escape(str(row.get("merchant", "—")))
            amt = float(row.get("amount_uah", 0.0))
            items2.append(f"{i}. {m} — {md_escape(format_money_uah_pretty(amt))}")
        parts.append(templates.section("Топ мерчантів", items2))

    uncategorized_block = _render_uncategorized_block(facts)
    if uncategorized_block:
        parts.append(uncategorized_block)

    deep_categories_block = _render_categories_deep_block(facts)
    if deep_categories_block:
        parts.append(deep_categories_block)

    if not parts:
        return None
    return "\n\n".join(parts).strip()


def _render_compare_section(facts: dict) -> str | None:
    comparison = facts.get("comparison")
    if not isinstance(comparison, dict):
        return None

    totals_cmp = comparison.get("totals", {})
    delta = totals_cmp.get("delta", {}) if isinstance(totals_cmp, dict) else {}
    pct = totals_cmp.get("pct_change", {}) if isinstance(totals_cmp, dict) else {}

    d_real = delta.get("real_spend_total_uah")
    p_real = pct.get("real_spend_total_uah")

    if d_real is None:
        return None

    d_real_f = float(d_real)
    sign = "+" if d_real_f >= 0 else ""
    pct_txt = "—" if p_real is None else f"{float(p_real):+.2f}%"

    cmp_lines: list[str] = [
        f"Реальні витрати: {md_escape(sign + format_money_uah_pretty(d_real_f))} ({md_escape(pct_txt)})"
    ]

    cat_cmp = comparison.get("categories", {})
    if isinstance(cat_cmp, dict) and cat_cmp:
        items3: list[tuple[str, float, float | None]] = []
        for k, v in cat_cmp.items():
            if not isinstance(v, dict):
                continue
            items3.append((str(k), float(v.get("delta_uah", 0.0)), v.get("pct_change")))
        items3.sort(key=lambda x: abs(x[1]), reverse=True)

        for k, dlt, pctv in items3[:5]:
            sign2 = "+" if dlt >= 0 else ""
            pct_txt2 = "—" if pctv is None else f"{float(pctv):+.2f}%"
            cmp_lines.append(
                f"{md_escape(k)}: {md_escape(sign2 + format_money_uah_pretty(dlt))} ({md_escape(pct_txt2)})"
            )

    return templates.section("Порівняння з попереднім періодом", cmp_lines)


def _render_facts_block_by_config(facts: dict, enabled: set[str]) -> str:
    parts: list[str] = []

    if "totals" in enabled:
        sec = _render_totals_section(facts)
        if sec:
            parts.append(sec)

    if "breakdowns" in enabled:
        sec2 = _render_breakdowns_section(facts)
        if sec2:
            parts.append(sec2)

    if "compare_baseline" in enabled:
        sec3 = _render_compare_section(facts)
        if sec3:
            parts.append(sec3)

    return "\n\n".join(parts).strip()


def _render_trends_block(trends: dict) -> str | None:
    if not isinstance(trends, dict):
        return None

    growing = trends.get("growing") or []
    declining = trends.get("declining") or []

    if not growing and not declining:
        return None

    lines: list[str] = []
    lines.append("*Тренди (7 днів vs попередні 7):*")

    def fmt_item(x: dict) -> str:
        label = md_escape(str(x.get("label", "—")))
        delta = float(x.get("delta_uah", 0.0))
        pct = x.get("pct")
        sign = "+" if delta > 0 else ""
        pct_part = f" ({sign}{int(pct)}%)" if isinstance(pct, (int, float)) else ""
        return f"• {label} {sign}{md_escape(format_money_uah_pretty(delta))}{pct_part}"

    if growing:
        lines.append("")
        lines.append("📈 *Зростання:*")
        for x in growing[:3]:
            lines.append(fmt_item(x))

    if declining:
        lines.append("")
        lines.append("📉 *Падіння:*")
        for x in declining[:3]:
            lines.append(fmt_item(x))

    return "\n".join(lines).strip()


_ANOMALY_REASON_TEXT: dict[str, str] = {
    "first_time_large": "вперше велика сума за період",
    "spike_vs_median": "сплеск відносно типової (медіани)",
}


def _render_anomalies_block(facts: dict) -> str | None:
    raw = facts.get("anomalies")
    items: list[dict] = []

    if isinstance(raw, list):
        items = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, Mapping):
        v = raw.get("items")
        if isinstance(v, list):
            items = [x for x in v if isinstance(x, dict)]

    if not items:
        return None

    lines: list[str] = []
    for i, a in enumerate(items[:5], start=1):
        label = md_escape(str(a.get("label", "—")))
        last_uah = float(a.get("last_day_uah", 0.0) or 0.0)
        base_uah = float(a.get("baseline_median_uah", 0.0) or 0.0)

        reason = str(a.get("reason", "") or "").strip()
        reason_txt = _ANOMALY_REASON_TEXT.get(reason, reason if reason else "аномалія")

        lines.append(
            f"{i}. {label} — *{md_escape(format_money_uah_pretty(last_uah))}* "
            f"(звично ~ {md_escape(format_money_uah_pretty(base_uah))}) · {md_escape(reason_txt)}"
        )

    return templates.section("Аномалії", lines)


def _render_refunds_block(facts: dict) -> str | None:
    r = facts.get("refunds") or {}
    if not isinstance(r, dict):
        return None

    count = int(r.get("count") or 0)
    if count <= 0:
        return None

    total = float(r.get("total_uah") or 0.0)
    items = r.get("items") or []
    if not isinstance(items, list):
        items = []

    if count <= 1:
        lines = [f"• Виявлено повернення: *{md_escape(format_money_uah_pretty(total))}*"]
        return templates.section("Повернення", lines)

    lines: list[str] = []
    lines.append(
        f"• Виявлено повернень: *{count}* на суму *{md_escape(format_money_uah_pretty(total))}*"
    )

    top = items[:3]
    if top:
        lines.append("")
        lines.append("Топ:")
        for it in top:
            if not isinstance(it, dict):
                continue
            merchant = md_escape(str(it.get("merchant") or "—"))
            amt = float(it.get("amount_uah") or 0.0)
            lines.append(f"• {merchant} — {md_escape(format_money_uah_pretty(amt))}")

    return templates.section("Повернення", lines)


def _render_whatif_block(facts: dict) -> str | None:
    whatifs = facts.get("whatif_suggestions") or []
    if not isinstance(whatifs, list) or not whatifs:
        return None

    lines: list[str] = []
    lines.append("*What-if (можлива економія):*")

    for w in whatifs[:2]:
        title = md_escape(str(w.get("title", "—")))
        base = float(w.get("monthly_spend_uah", 0.0))
        scenarios = w.get("scenarios") or []

        parts: list[str] = []
        if isinstance(scenarios, list):
            for s in scenarios[:2]:
                pct = int(s.get("pct", 0))
                sav = float(s.get("monthly_savings_uah", 0.0))
                parts.append(f"-{pct}% → ~{md_escape(format_money_uah_pretty(sav))}/міс")

        tail = "; ".join(parts) if parts else "—"
        lines.append(f"• {title} (зараз ~{md_escape(format_money_uah_pretty(base))}/міс): {tail}")

    return "\n".join(lines).strip()


def _render_ai_block(ai_block: str | None) -> str | None:
    if not ai_block:
        return None
    return f"🤖 *AI інсайти:*\n{ai_block.strip()}"


def render_report_for_user(
    reports_store: ReportsStore,
    tg_id: int,
    period: str,
    facts: dict,
    *,
    ai_block: str | None = None,
) -> str:
    cfg: ReportsConfig = reports_store.load(tg_id)
    cfg_period = _period_to_cfg_period(period)
    enabled = set(cfg.get_enabled_blocks(cfg_period))

    title_map = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}
    title = title_map.get(period, period)

    requested_label = facts.get("requested_period_label")
    if (
        isinstance(requested_label, str)
        and requested_label.strip()
        and str(period).startswith("custom:")
    ):
        title = requested_label.strip()

    header = f"📊 {md_escape(title)}"

    facts_block = _render_facts_block_by_config(facts, enabled)

    cov_warn = _render_coverage_warning(facts)
    if cov_warn:
        facts_block = "\n\n".join([cov_warn, facts_block]).strip()

    trends_block = None
    if "trends" in enabled:
        trends_block = _render_trends_block(facts.get("trends") or {})

    anomalies_block = None
    if "anomalies" in enabled:
        anomalies_block = _render_anomalies_block(facts)

    whatif_block = None
    if "what_if" in enabled:
        whatif_block = _render_whatif_block(facts)

    refunds_block = _render_refunds_block(facts) if "totals" in enabled else None
    insight_block = _render_ai_block(ai_block)

    return templates.report_layout(
        header=header,
        facts_block=facts_block,
        trends_block=trends_block,
        anomalies_block=anomalies_block,
        whatif_block=whatif_block,
        insight_block=insight_block,
        refunds_block=refunds_block,
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.nlq.memory_store import (
    DEFAULT_MERCHANT_ALIASES,
    resolve_merchant_filters,
    resolve_recipient_candidates,
)
from mono_ai_budget_bot.nlq.models import ResolutionState, Slots, canonical_intent_family
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest

ResolutionDecision = Literal["matched", "clarify", "not_found", "none"]
ResolutionEntity = Literal["recipient", "merchant", "category", "unknown"]


@dataclass(frozen=True)
class EvidenceResolution:
    entity: ResolutionEntity
    decision: ResolutionDecision
    normalized_values: list[str]
    display_values: list[str]
    alias: str | None = None


def resolve(req: NLQRequest, intent: NLQIntent) -> NLQIntent:
    state = resolve_canonical(req, intent)
    return state.to_intent()


def resolve_canonical(req: NLQRequest, intent: NLQIntent) -> ResolutionState:
    slots = Slots(dict(intent.slots or {}))
    confidence = str(slots.get("slots_confidence") or "high").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "high"
    return ResolutionState(
        intent=canonical_intent(intent),
        slots=slots,
        resolved_slots=slots,
        confidence=confidence,
        needs_clarification=False,
    )


def canonical_intent(intent: NLQIntent):
    from mono_ai_budget_bot.nlq.models import QueryIntent

    return QueryIntent(
        name=intent.name,
        family=canonical_intent_family(intent.name),
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        raw = item.strip()
        key = norm(item)
        if not raw or not key or key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


def _dedupe_normalized(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        key = norm(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _merchant_key(value: str) -> str:
    return norm(value).replace(" ", "")


def _recipient_name_stems(alias: str) -> list[str]:
    raw = norm(alias)
    if not raw:
        return []

    out: list[str] = [raw]
    for suffix in ("ії", "ій", "ію", "ия", "і", "у", "а", "ю", "я", "е", "о"):
        if raw.endswith(suffix) and len(raw) - len(suffix) >= 3:
            out.append(raw[: -len(suffix)])

    dedup: list[str] = []
    for item in out:
        if item and item not in dedup:
            dedup.append(item)
    return dedup


def _kind_prefix_from_intent(intent_name: str) -> str | None:
    name = str(intent_name or "").strip()
    if name.startswith("transfer_out"):
        return "transfer_out"
    if name.startswith("transfer_in"):
        return "transfer_in"
    return None


def _direct_recipient_candidates(
    rows: list[Any],
    *,
    alias: str,
    kind_prefix: str | None,
    limit: int = 5,
) -> list[str]:
    stems = _recipient_name_stems(alias)
    if not stems:
        return []

    scored: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(
            getattr(r, "amount", 0), getattr(r, "mcc", None), getattr(r, "description", "")
        )
        if kind_prefix == "transfer_out" and kind != "transfer_out":
            continue
        if kind_prefix == "transfer_in" and kind != "transfer_in":
            continue
        if kind_prefix is None and kind not in {"transfer_out", "transfer_in"}:
            continue

        desc = str(getattr(r, "description", "") or "").strip()
        if not desc:
            continue

        desc_norm = norm(desc)
        if not desc_norm:
            continue

        tokens = desc_norm.split()
        if any(stem in desc_norm or any(tok.startswith(stem) for tok in tokens) for stem in stems):
            scored[desc] = scored.get(desc, 0) + abs(int(getattr(r, "amount", 0) or 0))

    items = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in items[: max(1, min(int(limit), 15))]]


def _top_recipient_candidates(
    rows: list[Any],
    *,
    kind_prefix: str | None,
    limit: int = 5,
) -> list[str]:
    scored: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(
            getattr(r, "amount", 0), getattr(r, "mcc", None), getattr(r, "description", "")
        )
        if kind_prefix == "transfer_out" and kind != "transfer_out":
            continue
        if kind_prefix == "transfer_in" and kind != "transfer_in":
            continue
        if kind_prefix is None and kind not in {"transfer_out", "transfer_in"}:
            continue

        desc = str(getattr(r, "description", "") or "").strip()
        if not desc:
            continue

        scored[desc] = scored.get(desc, 0) + abs(int(getattr(r, "amount", 0) or 0))

    items = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in items[: max(1, min(int(limit), 15))]]


def resolve_recipient_by_evidence(
    telegram_user_id: int,
    rows: list[Any],
    *,
    alias: str | None,
    target: str | None,
    mode: str | None,
    intent_name: str,
) -> EvidenceResolution:
    alias_raw = str(alias or "").strip()
    target_raw = str(target or "").strip()
    lookup = target_raw or alias_raw
    if not lookup:
        return EvidenceResolution(
            entity="recipient",
            decision="none",
            normalized_values=[],
            display_values=[],
            alias=None,
        )

    kind_prefix = _kind_prefix_from_intent(intent_name)
    learned = resolve_recipient_candidates(telegram_user_id, alias_raw or lookup) or []
    direct = _direct_recipient_candidates(
        rows,
        alias=lookup,
        kind_prefix=kind_prefix,
        limit=5,
    )

    merged = _dedupe_strings([*learned, *direct])
    normalized = [item.strip().lower() for item in merged if item.strip()]

    mode_key = str(mode or "").strip().lower()
    if mode_key == "explicit":
        if len(merged) == 1:
            return EvidenceResolution(
                entity="recipient",
                decision="matched",
                normalized_values=[merged[0].strip().lower()],
                display_values=[merged[0].strip()],
                alias=lookup,
            )
        if len(merged) > 1:
            return EvidenceResolution(
                entity="recipient",
                decision="clarify",
                normalized_values=normalized,
                display_values=merged,
                alias=lookup,
            )
        return EvidenceResolution(
            entity="recipient",
            decision="not_found",
            normalized_values=[],
            display_values=[],
            alias=lookup,
        )

    if len(learned) == 1:
        picked = learned[0].strip()
        return EvidenceResolution(
            entity="recipient",
            decision="matched",
            normalized_values=[picked.lower()],
            display_values=[picked],
            alias=alias_raw or lookup,
        )
    if len(learned) > 1:
        learned_display = _dedupe_strings(learned)
        return EvidenceResolution(
            entity="recipient",
            decision="clarify",
            normalized_values=[item.lower() for item in learned_display],
            display_values=learned_display,
            alias=alias_raw or lookup,
        )

    options = _top_recipient_candidates(rows, kind_prefix=kind_prefix, limit=5)
    if options:
        return EvidenceResolution(
            entity="recipient",
            decision="clarify",
            normalized_values=[item.strip().lower() for item in options if item.strip()],
            display_values=_dedupe_strings(options),
            alias=alias_raw or lookup,
        )

    return EvidenceResolution(
        entity="recipient",
        decision="not_found",
        normalized_values=[],
        display_values=[],
        alias=alias_raw or lookup,
    )


def resolve_merchant_by_evidence(
    telegram_user_id: int,
    *,
    merchant_contains: str | None,
    merchant_targets: list[str] | None,
) -> EvidenceResolution:
    raw_targets = [
        str(x).strip() for x in (merchant_targets or []) if isinstance(x, str) and str(x).strip()
    ]
    if not raw_targets and isinstance(merchant_contains, str) and merchant_contains.strip():
        raw_targets = [merchant_contains.strip()]

    if not raw_targets:
        return EvidenceResolution(
            entity="merchant",
            decision="none",
            normalized_values=[],
            display_values=[],
            alias=None,
        )

    resolved: list[str] = []
    for target in raw_targets:
        vals = resolve_merchant_filters(telegram_user_id, target) or []
        target_norm = norm(target)
        default_alias = DEFAULT_MERCHANT_ALIASES.get(target_norm)

        cleaned_vals = [str(item).strip() for item in vals if str(item).strip()]
        if cleaned_vals:
            only_raw_fallback = len(cleaned_vals) == 1 and norm(cleaned_vals[0]) == target_norm
            if only_raw_fallback and isinstance(default_alias, str) and default_alias.strip():
                resolved.append(default_alias.strip())
            else:
                resolved.extend(cleaned_vals)
            continue

        if isinstance(default_alias, str) and default_alias.strip():
            resolved.append(default_alias.strip())
            continue

        resolved.append(target)

    normalized_values: list[str] = []
    seen: set[str] = set()
    for item in resolved:
        key = _merchant_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized_values.append(key)

    if normalized_values:
        return EvidenceResolution(
            entity="merchant",
            decision="matched",
            normalized_values=normalized_values,
            display_values=raw_targets,
            alias=str(merchant_contains or raw_targets[0]).strip(),
        )

    return EvidenceResolution(
        entity="merchant",
        decision="not_found",
        normalized_values=[],
        display_values=raw_targets,
        alias=str(merchant_contains or raw_targets[0]).strip(),
    )


def resolve_category_by_evidence(
    *,
    category: str | None,
    category_targets: list[str] | None,
) -> EvidenceResolution:
    targets = [
        str(x).strip() for x in (category_targets or []) if isinstance(x, str) and str(x).strip()
    ]
    if not targets and isinstance(category, str) and category.strip():
        targets = [category.strip()]

    targets = _dedupe_strings(targets)
    if not targets:
        return EvidenceResolution(
            entity="category",
            decision="none",
            normalized_values=[],
            display_values=[],
            alias=None,
        )

    return EvidenceResolution(
        entity="category",
        decision="matched",
        normalized_values=targets,
        display_values=targets,
        alias=targets[0],
    )

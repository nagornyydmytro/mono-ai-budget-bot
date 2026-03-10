from mono_ai_budget_bot.currency.convert import (
    alpha_to_numeric,
    convert_amount,
    parse_currency_conversion_query,
    parse_currency_rate_query,
)
from mono_ai_budget_bot.currency.models import MonoCurrencyRate
from mono_ai_budget_bot.nlq.router import parse_nlq_intent


def _rates():
    return [
        MonoCurrencyRate(
            currencyCodeA=840,
            currencyCodeB=980,
            date=1_700_000_000,
            rateBuy=40.0,
            rateSell=41.0,
            rateCross=None,
        ),
        MonoCurrencyRate(
            currencyCodeA=978,
            currencyCodeB=980,
            date=1_700_000_000,
            rateBuy=43.0,
            rateSell=44.0,
            rateCross=None,
        ),
        MonoCurrencyRate(
            currencyCodeA=985,
            currencyCodeB=980,
            date=1_700_000_000,
            rateBuy=None,
            rateSell=None,
            rateCross=10.0,
        ),
    ]


def test_parse_currency_conversion_query_variants():
    c1 = parse_currency_conversion_query("1500 грн в USD")
    assert c1 is not None
    assert c1.amount == 1500.0
    assert c1.from_alpha == "UAH"
    assert c1.to_alpha == "USD"

    c2 = parse_currency_conversion_query("55.34 usd в uah")
    assert c2 is not None
    assert c2.amount == 55.34
    assert c2.from_alpha == "USD"
    assert c2.to_alpha == "UAH"

    c3 = parse_currency_conversion_query("100 EUR -> PLN")
    assert c3 is not None
    assert c3.amount == 100.0
    assert c3.from_alpha == "EUR"
    assert c3.to_alpha == "PLN"

    c4 = parse_currency_conversion_query("$100 в грн")
    assert c4 is not None
    assert c4.amount == 100.0
    assert c4.from_alpha == "USD"
    assert c4.to_alpha == "UAH"

    c5 = parse_currency_conversion_query("100 € у PLN")
    assert c5 is not None
    assert c5.amount == 100.0
    assert c5.from_alpha == "EUR"
    assert c5.to_alpha == "PLN"

    c6 = parse_currency_conversion_query("1500 hryvnia to usd")
    assert c6 is not None
    assert c6.amount == 1500.0
    assert c6.from_alpha == "UAH"
    assert c6.to_alpha == "USD"


def test_router_detects_currency_convert_intent():
    out = parse_nlq_intent("1500 грн в USD")
    assert out["intent"] == "currency_convert"
    assert out["amount"] == 1500.0
    assert out["from"] == "UAH"
    assert out["to"] == "USD"


def test_convert_amount_supported_pairs():
    rates = _rates()
    uah = alpha_to_numeric("UAH")
    usd = alpha_to_numeric("USD")
    eur = alpha_to_numeric("EUR")
    pln = alpha_to_numeric("PLN")
    assert uah == 980
    assert usd == 840
    assert eur == 978
    assert pln == 985

    out1 = convert_amount(1500.0, from_num=uah, to_num=usd, rates=rates)
    assert out1 is not None
    assert round(out1, 2) == round(1500.0 / 41.0, 2)

    out2 = convert_amount(10.0, from_num=usd, to_num=uah, rates=rates)
    assert out2 is not None
    assert round(out2, 2) == 400.0

    out3 = convert_amount(10.0, from_num=usd, to_num=eur, rates=rates)
    assert out3 is not None
    assert round(out3, 4) == round((10.0 * 40.0) / 44.0, 4)

    out4 = convert_amount(100.0, from_num=pln, to_num=uah, rates=rates)
    assert out4 is not None
    assert round(out4, 2) == 1000.0


def test_executor_currency_convert_success(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    class DummyPublicClient:
        def currency(self, *args, **kwargs):
            return _rates()

        def close(self):
            return None

    monkeypatch.setattr(ex, "MonobankPublicClient", DummyPublicClient)

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "amount": 1500, "from": "UAH", "to": "USD"},
    )
    assert "1500.00 UAH" in msg
    assert "≈" in msg
    assert "USD" in msg


def test_executor_currency_convert_unknown_currency(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    class DummyPublicClient:
        def currency(self, *args, **kwargs):
            return _rates()

        def close(self):
            return None

    monkeypatch.setattr(ex, "MonobankPublicClient", DummyPublicClient)

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "amount": 10, "from": "UAH", "to": "ZZZ"},
    )
    assert "Не знаю таку валюту" in msg


def test_executor_currency_convert_missing_pair(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    class DummyPublicClient:
        def currency(self, *args, **kwargs):
            return [
                MonoCurrencyRate(
                    currencyCodeA=840,
                    currencyCodeB=980,
                    date=1_700_000_000,
                    rateBuy=40.0,
                    rateSell=41.0,
                )
            ]

        def close(self):
            return None

    monkeypatch.setattr(ex, "MonobankPublicClient", DummyPublicClient)

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "amount": 10, "from": "EUR", "to": "USD"},
    )
    assert "Немає даних по парі EUR→USD" in msg


def test_executor_currency_convert_unknown_currency_has_guided_message(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    class DummyPublicClient:
        def currency(self, *args, **kwargs):
            return _rates()

        def close(self):
            return None

    monkeypatch.setattr(ex, "MonobankPublicClient", DummyPublicClient)

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "amount": 10, "from": "UAH", "to": "ZZZ"},
    )
    assert "Не знаю таку валюту" in msg
    assert "грн / UAH / hryvnia" in msg
    assert "$ / USD" in msg
    assert "€ / EUR" in msg


def test_router_detects_currency_convert_intent_for_symbol_prefix():
    out = parse_nlq_intent("$100 в грн")
    assert out["intent"] == "currency_convert"
    assert out["amount"] == 100.0
    assert out["from"] == "USD"
    assert out["to"] == "UAH"


def test_parse_currency_conversion_query_returns_none_for_missing_target_currency():
    assert parse_currency_conversion_query("1500 грн") is None


def test_parse_currency_conversion_query_returns_none_for_missing_source_currency():
    assert parse_currency_conversion_query("1500 в USD") is None


def test_parse_currency_conversion_query_returns_none_for_zero_amount():
    assert parse_currency_conversion_query("0 грн в USD") is None


def test_convert_amount_returns_same_amount_for_same_currency():
    rates = _rates()
    uah = alpha_to_numeric("UAH")
    assert uah == 980
    out = convert_amount(123.45, from_num=uah, to_num=uah, rates=rates)
    assert out == 123.45


def test_executor_currency_convert_missing_amount_has_guided_message():
    import mono_ai_budget_bot.nlq.executor as ex

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "from": "UAH", "to": "USD"},
    )
    assert "Не бачу суму для конвертації" in msg
    assert "1500 грн в USD" in msg


def test_executor_currency_convert_missing_currency_has_guided_message():
    import mono_ai_budget_bot.nlq.executor as ex

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_convert", "amount": 1500},
    )
    assert "Не бачу валюту" in msg
    assert "$100 в грн" in msg


def test_parse_currency_conversion_query_supports_spelled_out_amount_query():
    c = parse_currency_conversion_query("скільки буде 100 доларів у гривнях")
    assert c is not None
    assert c.amount == 100.0
    assert c.from_alpha == "USD"
    assert c.to_alpha == "UAH"


def test_parse_currency_rate_query_variants():
    q1 = parse_currency_rate_query("який зараз курс долара")
    assert q1 is not None
    assert q1.base_alpha == "USD"
    assert q1.quote_alpha == "UAH"

    q2 = parse_currency_rate_query("курс євро в доларах")
    assert q2 is not None
    assert q2.base_alpha == "EUR"
    assert q2.quote_alpha == "USD"


def test_router_detects_currency_rate_intent():
    out = parse_nlq_intent("який зараз курс долара")
    assert out["intent"] == "currency_rate"
    assert out["from"] == "USD"
    assert out["to"] == "UAH"


def test_executor_currency_rate_success(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    class DummyPublicClient:
        def currency(self, *args, **kwargs):
            return _rates()

        def close(self):
            return None

    monkeypatch.setattr(ex, "MonobankPublicClient", DummyPublicClient)

    msg = ex.execute_intent(
        telegram_user_id=1,
        intent_payload={"intent": "currency_rate", "from": "USD", "to": "UAH"},
    )
    assert "1 USD" in msg
    assert "UAH" in msg
    assert "40.00" in msg


def test_currency_explain_question_goes_to_safe_llm():
    import mono_ai_budget_bot.nlq.pipeline as pl
    from mono_ai_budget_bot.nlq.types import NLQRequest

    req = NLQRequest(
        telegram_user_id=1,
        text="що вигідніше зараз: тримати в usd чи eur",
        now_ts=1000,
    )

    assert pl._select_answer_policy(req, None) == "safe_llm"

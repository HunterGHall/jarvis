import json
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def get_stock_price(symbol):
    symbol = symbol.strip().upper()
    data = _get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1d"
    )
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        previous_close = meta["chartPreviousClose"]
    except (KeyError, IndexError, TypeError):
        return {}
    change = price - previous_close
    return {
        "symbol": symbol,
        "name": meta.get("longName") or meta.get("shortName"),
        "currency": meta.get("currency"),
        "price": round(price, 2),
        "previous_close": round(previous_close, 2),
        "change": round(change, 2),
        "change_percent": round(100 * change / previous_close, 2) if previous_close else 0.0,
    }


def get_crypto_price(coin_id="bitcoin", currency="usd"):
    coin_id, currency = coin_id.strip().lower(), currency.strip().lower()
    query = urllib.parse.urlencode({"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"})
    data = _get_json(f"https://api.coingecko.com/api/v3/simple/price?{query}")
    try:
        entry = data[coin_id]
        return {
            "coin": coin_id,
            "currency": currency.upper(),
            "price": entry[currency],
            "change_24h_percent": round(entry.get(f"{currency}_24h_change", 0.0), 2),
        }
    except (KeyError, TypeError):
        return {}


def convert_currency(amount, from_currency, to_currency):
    from_currency, to_currency = from_currency.strip().upper(), to_currency.strip().upper()
    query = urllib.parse.urlencode({"amount": amount, "from": from_currency, "to": to_currency})
    data = _get_json(f"https://api.frankfurter.dev/v1/latest?{query}")
    try:
        converted = data["rates"][to_currency]
    except (KeyError, TypeError):
        return {}
    return {
        "amount": amount,
        "from": from_currency,
        "to": to_currency,
        "converted": converted,
        "rate": round(converted / amount, 6) if amount else None,
        "date": data.get("date"),
    }


if __name__ == "__main__":
    print(json.dumps(get_stock_price("AAPL"), indent=2))
    print(json.dumps(get_crypto_price("bitcoin"), indent=2))
    print(json.dumps(convert_currency(100, "USD", "EUR"), indent=2))

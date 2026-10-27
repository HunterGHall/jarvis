# USD per million tokens: (input, output, cache read). Cache writes bill at 1.25x input.
MODEL_PRICES = {
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "claude-fable-5": (10.00, 50.00, 0.25),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-opus-4-7": (5.00, 25.00, 0.50),
    "claude-opus-4-6": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}

# Haiku 5.5 prompts over 100K tokens bill at higher rates.
HAIKU_5_5_LONG_PROMPT = 100_000
HAIKU_5_5_LONG_PRICES = (0.50, 2.50, 0.05)


def estimate_cost(model, usage):
    """(input, output) cost in USD of one API call from its usage dict, or None for an unknown model."""
    prices = MODEL_PRICES.get(model)
    if prices is None:
        return None

    input_tokens = usage.get("input_tokens") or 0
    cache_write = usage.get("cache_creation_input_tokens") or 0
    cache_read = usage.get("cache_read_input_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0

    if model == "claude-haiku-5-5" and input_tokens + cache_write + cache_read > HAIKU_5_5_LONG_PROMPT:
        prices = HAIKU_5_5_LONG_PRICES
    input_price, output_price, cache_read_price = prices

    input_cost = (input_tokens * input_price + cache_write * input_price * 1.25 + cache_read * cache_read_price) / 1_000_000
    output_cost = output_tokens * output_price / 1_000_000
    return input_cost, output_cost


def format_cost(cost):
    return f"${cost:.4f}" if cost < 0.1 else f"${cost:.2f}"


def format_tokens(count):
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)

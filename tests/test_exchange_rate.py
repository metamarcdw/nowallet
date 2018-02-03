from nowallet import exchange_rate

def test_fetch_exchange_rates(event_loop):
    rates = event_loop.run_until_complete(
        exchange_rate.fetch_exchange_rates())["btcav"]
    for rate in rates.items():
        assert isinstance(rate, tuple)
        assert len(rate) == 2
        symbol, float_ = rate
        assert isinstance(symbol, str)
        assert isinstance(float_, float)

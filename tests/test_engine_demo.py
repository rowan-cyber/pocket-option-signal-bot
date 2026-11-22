import asyncio

from signalbot.config import Config
from signalbot.engine import SignalEngine
from signalbot.pocket.client import DemoMarketClient, _normalize_df, create_client


def test_create_client_demo_vs_live():
    assert isinstance(create_client("", is_demo=True), DemoMarketClient)
    # Non-empty ssid -> live client type (no network call here).
    live = create_client("42[\"auth\",{}]", is_demo=True)
    assert live.is_live is True


def test_demo_client_returns_ohlc():
    async def run():
        client = DemoMarketClient(seed=42)
        await client.connect()
        df = await client.get_candles("EURUSD_otc", 60, 120)
        return df

    df = asyncio.run(run())
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 120
    assert (df["high"] >= df["low"]).all()


def test_normalize_df_handles_missing_volume_and_case():
    import pandas as pd

    raw = pd.DataFrame(
        {"Open": [1.0], "High": [1.2], "Low": [0.9], "Close": [1.1]}
    )
    out = _normalize_df(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out["volume"].iloc[0] == 0.0


def test_engine_scan_returns_list():
    async def run():
        config = Config()
        config.assets = ["EURUSD_otc", "GBPUSD_otc"]
        config.min_confidence = 0  # accept everything for the test
        engine = SignalEngine(config, DemoMarketClient(seed=7))
        await engine.connect()
        return await engine.scan(apply_cooldown=False)

    signals = asyncio.run(run())
    assert isinstance(signals, list)
    for s in signals:
        assert s.direction in {"CALL", "PUT"}
        assert s.live is False

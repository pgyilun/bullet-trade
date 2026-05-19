import pytest

from bullet_trade.server.adapters.base import AccountRouter
from bullet_trade.server.adapters.qmt import QmtBrokerAdapter
from bullet_trade.server.config import AccountConfig, ServerConfig


class _FakeBroker:
    def __init__(self):
        self.calls = []

    async def buy(self, security, amount, price=None, wait_timeout=None, remark=None, market=False):
        self.calls.append(
            {
                "side": "BUY",
                "security": security,
                "amount": amount,
                "price": price,
                "wait_timeout": wait_timeout,
                "remark": remark,
                "market": market,
            }
        )
        return "OID-1"

    async def sell(self, security, amount, price=None, wait_timeout=None, remark=None, market=False):
        self.calls.append(
            {
                "side": "SELL",
                "security": security,
                "amount": amount,
                "price": price,
                "wait_timeout": wait_timeout,
                "remark": remark,
                "market": market,
            }
        )
        return "OID-2"

    def get_positions(self):
        return [
            {
                "security": "159967.SZ",
                "closeable_amount": 1000,
                "amount": 1000,
            }
        ]


@pytest.mark.asyncio
async def test_qmt_server_market_order_prefers_client_protect_price(monkeypatch):
    from bullet_trade.core import pricing

    async def _fake_snapshot(_security):
        return {
            "last_price": 0.636,
            "high_limit": 0.700,
            "low_limit": 0.600,
            "paused": False,
        }

    def _unexpected_compute(*args, **kwargs):
        raise AssertionError("客户端已提供保护价时，不应在服务端重算")

    monkeypatch.setattr(pricing, "compute_market_protect_price", _unexpected_compute)

    config = ServerConfig(
        server_type="qmt",
        listen="127.0.0.1",
        port=0,
        token="t",
        enable_data=False,
        enable_broker=True,
        accounts=[AccountConfig(key="default", account_id="demo")],
    )
    router = AccountRouter(config.accounts)
    adapter = QmtBrokerAdapter(config, router)
    ctx = router.get("default")
    fake_broker = _FakeBroker()
    adapter._brokers[ctx.config.key] = fake_broker
    monkeypatch.setattr(adapter, "_get_live_snapshot", _fake_snapshot)

    result = await adapter.place_order(
        ctx,
        {
            "security": "159967.SZ",
            "side": "SELL",
            "amount": 1000,
            "style": {"type": "market", "price": 0.626},
            "wait_timeout": 5,
            "order_remark": "bt:test:abcd1234",
        },
    )

    assert fake_broker.calls[0]["market"] is True
    assert fake_broker.calls[0]["price"] == pytest.approx(0.626)
    assert fake_broker.calls[0]["wait_timeout"] == 5
    assert result["order_price"] == pytest.approx(0.626)
    assert result["requested_order_price"] == pytest.approx(0.626)


@pytest.mark.asyncio
async def test_qmt_server_forwards_zero_wait_timeout(monkeypatch):
    async def _fake_snapshot(_security):
        return {
            "last_price": 10.0,
            "high_limit": 11.0,
            "low_limit": 9.0,
            "paused": False,
        }

    config = ServerConfig(
        server_type="qmt",
        listen="127.0.0.1",
        port=0,
        token="t",
        enable_data=False,
        enable_broker=True,
        accounts=[AccountConfig(key="default", account_id="demo")],
    )
    router = AccountRouter(config.accounts)
    adapter = QmtBrokerAdapter(config, router)
    ctx = router.get("default")
    fake_broker = _FakeBroker()
    adapter._brokers[ctx.config.key] = fake_broker
    monkeypatch.setattr(adapter, "_get_live_snapshot", _fake_snapshot)

    await adapter.place_order(
        ctx,
        {
            "security": "000001.XSHE",
            "side": "BUY",
            "amount": 100,
            "style": {"type": "limit", "price": 10.0},
            "wait_timeout": 0,
        },
    )

    assert fake_broker.calls[0]["wait_timeout"] == 0

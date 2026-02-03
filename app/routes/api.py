import logging

import numpy as np
from flask import Blueprint, current_app, jsonify, request

from app.backtest.engine import run_backtest
from app.data.fetcher import fetch_candles
from app.strategies import get_all_strategies, get_strategy
from config import Config

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/strategies")
def list_strategies():
    return jsonify({"strategies": get_all_strategies()})


@api_bp.route("/strategy/<name>/parameters")
def strategy_parameters(name):
    try:
        strategy = get_strategy(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"parameters": strategy.get_parameters()})


@api_bp.route("/backtest", methods=["POST"])
def backtest():
    body = request.get_json(silent=True) or {}

    strategy_name = body.get("strategy")
    instrument = body.get("instrument", Config.DEFAULT_INSTRUMENT)
    interval = body.get("interval", Config.DEFAULT_INTERVAL)
    from_date = body.get("from_date")
    to_date = body.get("to_date")
    params = body.get("parameters", {})

    if not strategy_name:
        return jsonify({"error": "Missing 'strategy' field"}), 400

    try:
        strategy = get_strategy(strategy_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    if params:
        strategy.set_parameters(params)

    # Fetch data
    try:
        df = fetch_candles(instrument, interval, from_date, to_date)
    except Exception:
        logger.exception("Data fetch failed")
        return jsonify({"error": "Failed to fetch market data"}), 502

    # Generate signals
    df = strategy.generate_signals(df)

    # Run backtest
    spread = Config.SPREADS.get(instrument, 1.5)
    result = run_backtest(df, spread_pips=spread)

    # Prepare response
    def _safe(val):
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return 0.0
        return val

    candles = []
    for _, row in df.iterrows():
        candles.append(
            {
                "time": row["time"].isoformat() if hasattr(row["time"], "isoformat") else str(row["time"]),
                "open": round(float(row["open"]), 5),
                "high": round(float(row["high"]), 5),
                "low": round(float(row["low"]), 5),
                "close": round(float(row["close"]), 5),
            }
        )

    signals = []
    for i, row in df.iterrows():
        if row.get("signal", 0) != 0:
            signals.append(
                {
                    "time": row["time"].isoformat() if hasattr(row["time"], "isoformat") else str(row["time"]),
                    "position": "belowBar" if row["signal"] == 1 else "aboveBar",
                    "color": "#22c55e" if row["signal"] == 1 else "#ef4444",
                    "shape": "arrowUp" if row["signal"] == 1 else "arrowDown",
                    "text": "BUY" if row["signal"] == 1 else "SELL",
                    "value": round(float(row["close"]), 5),
                }
            )

    # Overlay data
    overlays = {}
    overlay_cols = strategy.get_overlay_columns()
    for overlay_name, columns in overlay_cols.items():
        overlay_data = {}
        for col in columns:
            if col in df.columns:
                overlay_data[col] = [
                    {
                        "time": row["time"].isoformat() if hasattr(row["time"], "isoformat") else str(row["time"]),
                        "value": round(float(row[col]), 5) if not np.isnan(row[col]) else None,
                    }
                    for _, row in df.iterrows()
                ]
                # Filter out None values
                overlay_data[col] = [p for p in overlay_data[col] if p["value"] is not None]
        overlays[overlay_name] = overlay_data

    metrics = {
        "total_trades": result.total_trades,
        "win_rate": round(_safe(result.win_rate) * 100, 1),
        "total_pnl": round(_safe(result.total_pnl), 2),
        "sharpe_ratio": round(_safe(result.sharpe_ratio), 2),
        "max_drawdown": round(_safe(result.max_drawdown) * 100, 2),
    }

    return jsonify(
        {
            "candles": candles,
            "signals": signals,
            "metrics": metrics,
            "overlays": overlays,
            "trades": result.trades,
            "equity_curve": [round(e, 2) for e in result.equity_curve],
        }
    )

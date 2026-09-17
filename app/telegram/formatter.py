"""Telegram Message Formatter for Qualified Trading Signals."""

from app.signal import explanation as exp
from app.signal.models import SignalCandidate


class TelegramSignalFormatter:
    """
    Formats SignalCandidate instances into clean, professional HTML notifications
    without any deceptive probability or profit claims.
    """

    @staticmethod
    def format(
        candidate: SignalCandidate,
        is_dry_run: bool = True,
        dry_run_label: str = "DRY RUN — READ ONLY",
    ) -> str:
        icon = "🟢" if candidate.direction == "LONG" else "🔴"
        direction = candidate.direction
        symbol = candidate.symbol
        score = candidate.long_score if direction == "LONG" else candidate.short_score
        status = candidate.signal_status.value
        regime = candidate.regime

        header = f"🧪 <b>[{dry_run_label}]</b>\n" if is_dry_run else ""
        header += f"{icon} <b>{direction} SIGNAL — {status}</b>\n\n"

        # Formatting price precision based on magnitude
        price = candidate.current_price
        prec = 4 if price < 10 else 2 if price < 1000 else 1 if price < 10000 else 2
        fmt = f",.{prec}f"

        entry_low = format(candidate.entry_zone_low, fmt)
        entry_high = format(candidate.entry_zone_high, fmt)
        sl = format(candidate.stop_loss, fmt)
        tp1 = format(candidate.take_profit_1, fmt)
        tp2 = format(candidate.take_profit_2, fmt)

        # Multi-timeframe context strings
        ctx = candidate.timeframe_context or {}
        h4_desc = ctx.get("h4_trend", "NEUTRAL")
        h1_desc = ctx.get("h1_structure", "NEUTRAL")
        m15_desc = ctx.get("m15_setup", "NEUTRAL")
        m5_desc = ctx.get("m5_entry", "NEUTRAL")

        # Top confluences (limit to 5)
        reasons_list = candidate.reason_codes[:5]
        confluences_html = "\n".join(
            f"• {exp.format_reason(r)}" for r in reasons_list
        ) if reasons_list else "• Technical alignment across timeframes"

        # Warnings (if any)
        warnings_block = ""
        if candidate.warning_codes:
            warnings_html = "\n".join(
                f"⚠️ {exp.format_reason(w)}" for w in candidate.warning_codes
            )
            warnings_block = f"\n<b>Risk Notes:</b>\n{warnings_html}\n"

        # Component scores
        comps = candidate.component_scores or {}
        c_htf = int(comps.get("htf_trend", 0))
        c_struct = int(comps.get("market_structure", 0))
        c_liq = int(comps.get("liquidity", 0))
        c_mom = int(comps.get("momentum", 0))
        c_vol = int(comps.get("volume", 0))
        c_vola = int(comps.get("volatility", 0))
        c_deriv = int(comps.get("derivatives", 0))
        c_pa = int(comps.get("price_action", 0))

        message = (
            f"{header}"
            f"<b>Symbol:</b> #{symbol}\n"
            f"<b>Signal Score:</b> {score:.1f}/100\n"
            f"<b>Directional Edge:</b> +{candidate.directional_edge:.1f} pts\n"
            f"<b>Market Regime:</b> {regime}\n\n"
            f"<b>Entry Zone:</b> {entry_low} – {entry_high}\n"
            f"<b>Stop Loss:</b> {sl}\n"
            f"<b>TP1:</b> {tp1} (1:{candidate.risk_reward_tp1:.1f} RR)\n"
            f"<b>TP2:</b> {tp2} (1:{candidate.risk_reward_tp2:.1f} RR)\n\n"
            f"<b>Timeframe Alignment:</b>\n"
            f"• 4H Global: {h4_desc}\n"
            f"• 1H Structure: {h1_desc}\n"
            f"• 15M Setup: {m15_desc}\n"
            f"• 5M Entry: {m5_desc}\n\n"
            f"<b>Key Confluences:</b>\n"
            f"{confluences_html}\n"
            f"{warnings_block}\n"
            f"<b>Factor Breakdown (0-100):</b>\n"
            f"HTF Trend: {c_htf} | Structure: {c_struct} | Liquidity: {c_liq}\n"
            f"Momentum: {c_mom} | Volume: {c_vol} | Volatility: {c_vola}\n"
            f"Derivatives: {c_deriv} | Price Action: {c_pa}\n\n"
            f"<i>Notice: Score represents multi-factor rule alignment (0-100). "
            f"Analysis and alerts only; no automated execution. {'[DRY RUN TEST]' if is_dry_run else ''}</i>"
        )
        return message

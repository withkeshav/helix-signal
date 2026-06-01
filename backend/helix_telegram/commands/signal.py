"""Telegram bot command: /signal <asset> - Returns current risk score breakdown for a specific asset."""

import logging
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from services.dashboard import build_dashboard_response
from helix_telegram.templates import TelegramTemplates

logger = logging.getLogger(__name__)

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /signal <asset> command - returns current risk score breakdown for a specific asset."""
    try:
        # Validate input
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Usage: `/signal <asset>`\n"
                "Example: `/signal USDT`\n"
                "Returns risk metrics for a stablecoin asset.",
                parse_mode="Markdown"
            )
            return

        asset_symbol = context.args[0].upper().strip()
        
        # Get real data
        db = SessionLocal()
        try:
            try:
                dashboard = build_dashboard_response(db, asset_symbol)
            except Exception as e:
                if "not enabled" in str(e).lower():
                    await update.message.reply_text(f"❌ Asset `{asset_symbol}` is not enabled.", parse_mode="Markdown")
                    return
                raise

            # Format response
            risk_components = dashboard.asset_signal.components
            message = (
                f"📊 *Risk Signal for {asset_symbol}*\n"
                f"──────────────────\n"
                f"📈 Overall: {dashboard.asset_signal.score}/100 ({dashboard.asset_signal.band})\n\n"
            )

            # Add component scores
            if 'peg_stability' in risk_components:
                peg = risk_components['peg_stability']
                message += f"🔗 Peg Stability: {int(peg['score'])}/100 ({peg['label']})\n"
                if peg.get('reason'):
                    message += f"   └ {peg['reason']}\n"
                message += "\n"
            
            if 'liquidity_depth' in risk_components:
                liq = risk_components['liquidity_depth']
                message += f"💧 Liquidity: {int(liq['score'])}/100 ({liq['label']})\n"
                if liq.get('reason'):
                    message += f"   └ {liq['reason']}\n"
                message += "\n"
            
            if 'supply_stability' in risk_components:
                supply = risk_components['supply_stability']
                message += f"🏦 Supply: {int(supply['score'])}/100 ({supply['label']})\n"
                if supply.get('reason'):
                    message += f"   └ {supply['reason']}\n"
                message += "\n"
            
            if 'concentration' in risk_components:
                conc = risk_components['concentration']
                message += f"🎯 Concentration: {int(conc['score'])}/100 ({conc['label']})\n"
                if conc.get('reason'):
                    message += f"   └ {conc['reason']}\n"
                message += "\n"
            
            if 'data_confidence' in risk_components:
                conf = risk_components['data_confidence']
                message += f"📡 Data Quality: {int(conf['score'])}/100 ({conf['label']})\n"
                if conf.get('reason'):
                    message += f"   └ {conf['reason']}\n"

            # Add supply info
            if dashboard.total_supply_current:
                supply_val = dashboard.total_supply_current
                supply_str = f"${supply_val:,.0f}" if supply_val >= 1_000_000 else f"${supply_val:,.2f}"
                message += f"\n💰 Total Supply: {supply_str}\n"
            
            # Add price info
            if dashboard.depeg_index.current_price:
                price = dashboard.depeg_index.current_price
                dev_pct = dashboard.depeg_index.deviation_pct or 0
                message += f"💳 Price: ${price:.6f} ({'+' if dev_pct >= 0 else ''}{dev_pct:.4f}%)\n"

            await update.message.reply_text(message, parse_mode="Markdown")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in /signal command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error retrieving signal data. Please try again later.",
            parse_mode="Markdown"
        )
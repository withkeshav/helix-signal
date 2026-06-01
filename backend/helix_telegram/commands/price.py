"""Telegram bot command: /price <asset> - Returns current price from sources."""

import logging
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal
from services.dashboard import build_dashboard_response
from helix_telegram.templates import TelegramTemplates

logger = logging.getLogger(__name__)

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /price <asset> command - returns current price from sources."""
    try:
        # Validate input
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Usage: `/price <asset>`\n"
                "Example: `/price USDT`\n"
                "Returns current price data from multiple sources.",
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

            # Find chain with price data
            chain_with_price = None
            for chain in dashboard.chains:
                if chain.price is not None:
                    chain_with_price = chain
                    break
            
            if not chain_with_price:
                await update.message.reply_text(f"❌ No price data available for `{asset_symbol}`.", parse_mode="Markdown")
                return

            # Format response
            message = f"💰 *Price Data for {asset_symbol}*\n"
            message += f"──────────────────\n"
            message += f"📍 Chain: {chain_with_price.chain_name}\n\n"

            # Show all available prices
            prices = []
            if chain_with_price.price_coingecko is not None:
                prices.append(f"🌐 CoinGecko: `${chain_with_price.price_coingecko:.6f}`")
            if chain_with_price.price_dexscreener is not None:
                prices.append(f"🔍 DEX Screener: `${chain_with_price.price_dexscreener:.6f}`")
            if chain_with_price.price is not None:
                prices.append(f"⚖️ Composite: `${chain_with_price.price:.6f}`")
            
            message += "\n".join(prices) + "\n\n" if prices else "No prices available.\n\n"

            # Add deviation if available
            if dashboard.depeg_index.deviation_pct is not None:
                dev_pct = dashboard.depeg_index.deviation_pct
                dev_abs = dashboard.depeg_index.deviation_abs or 0
                message += f"🔗 *Peg Deviation*\n"
                message += f"   Absolute: {'+' if dev_abs >= 0 else ''}${dev_abs:.6f}\n"
                message += f"   Percent: {'+' if dev_pct >= 0 else ''}{dev_pct:.4f}%\n\n"
            
            # Add market data if available
            if chain_with_price.market_cap:
                mc_val = chain_with_price.market_cap
                mc_str = f"${mc_val:,.0f}" if mc_val >= 1_000_000 else f"${mc_val:,.2f}"
                message += f"📊 Market Cap: {mc_str}\n"
            
            if chain_with_price.volume_24h:
                vol_val = chain_with_price.volume_24h
                vol_str = f"${vol_val:,.0f}" if vol_val >= 1_000_000 else f"${vol_val:,.2f}"
                message += f"📈 24h Volume: {vol_str}\n"

            await update.message.reply_text(message, parse_mode="Markdown")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in /price command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error retrieving price data. Please try again later.",
            parse_mode="Markdown"
        )
# Grant Strategy

> Target grants for open-source stablecoin risk intelligence infrastructure.
> Helix-Signal is MIT-licensed public good — no tokens, no VC, no closed-source monetization.

## Target Programs

| Program | Value | Angle | Key Deliverable | Timeline |
|---------|-------|-------|-----------------|----------|
| **Alchemy Developer Grant** | Up to $50k credits | RPC credits for open-source stablecoin monitoring across 17+ chains | Working ingest pipeline; DeFiLlama + CoinGecko + DEX Screener already integrated; RPC not required for baseline | Q3 2025 |
| **Ethereum Foundation ESP** | $10k–50k | Open-source DeFi risk intelligence infrastructure | Canonical schemas, benchmark report on peg stability metrics, reproducibility via Docker Compose + pytest | Q3 2025 |
| **Optimism Retro Funding** | Retroactive | Superchain stablecoin analytics | OP Mainnet + Base module; attestation and supply feed freshness for Superchain stablecoins | Q4 2025 |
| **Uniswap Foundation** | $5k–25k | Pool risk monitoring for stablecoin pairs | DEX Screener liquidity depth, pool concentration, slippage estimation — already integrated | Q3 2025 |
| **Gitcoin Grants** | Matching (varies) | Public-good market intelligence | Public demo at helix.withkeshav.com; comprehensive documentation and quickstart | Ongoing |

## Application Materials to Prepare

| Material | Status | Notes |
|----------|--------|-------|
| README with architecture | ✅ Exists | Needs v3.2.0 pass (done in Phase 7) |
| Grant strategy brief | ✅ This file | |
| Public demo | ✅ helix.withkeshav.com | Production VPS deployment |
| Docker Compose quickstart | ✅ `docker compose up -d` | |
| Test suite results | ✅ 106 passing | Reproducible regression checks |
| Architecture doc | ✅ `docs/architecture.md` | Updated for ClickHouse + DB manager |
| License | ✅ MIT | In-repo |

## Pitch Summary

> Helix-Signal is an open-source, self-hostable stablecoin intelligence platform.
> It monitors USDT, USDC, DAI, and PYUSD across 17+ chains with:
> - Multi-source price validation (DeFiLlama, CoinGecko, DEX Screener)
> - V3 composite risk scoring with transparent evidence
> - TimesFM zero-shot forecasting for depeg prediction
> - FinBERT OSINT sentiment with attestation parsing
> - Anomaly detection via Isolation Forest and Z-score
> - Full Docker Compose deployment in 3 commands
>
> 106 regression tests pass. Zero paid API dependencies for core operation.
> MIT licensed. Self-hostable on a single VPS for ~$15/mo.

## Next Steps

1. Submit Alchemy Grant (quickest path — RPC credits are most useful for chain expansion)
2. Submit Gitcoin Grant (matching rounds align with public-good infra)
3. Prepare ESP application with canonical schema documentation
4. Apply to Optimism Retro Funding after OP Mainnet module is hardened

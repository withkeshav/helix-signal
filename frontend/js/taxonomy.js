export const STABLECOIN_TAXONOMY = {
  USDT:  { type: "fiat_backed",         sub_type: "offshore_issuer" },
  USDC:  { type: "fiat_backed",         sub_type: "regulated_us" },
  PYUSD: { type: "fiat_backed",         sub_type: "regulated_us" },
  FDUSD: { type: "fiat_backed",         sub_type: "offshore_issuer" },
  GUSD:  { type: "fiat_backed",         sub_type: "regulated_us" },
  RLUSD: { type: "fiat_backed",         sub_type: "regulated_us" },
  USD1:  { type: "fiat_backed",         sub_type: "political_actor" },
  USDG:  { type: "fiat_backed",         sub_type: "consortium" },
  DAI:   { type: "crypto_collateralized", sub_type: "multi_collateral" },
  USDS:  { type: "crypto_collateralized", sub_type: "sky_protocol" },
  LUSD:  { type: "crypto_collateralized", sub_type: "eth_only" },
  GHO:   { type: "crypto_collateralized", sub_type: "aave_backed" },
  crvUSD:{ type: "crypto_collateralized", sub_type: "llamma_amm" },
  USDY:  { type: "yield_bearing",       sub_type: "tbill_tokenized" },
  BUIDL: { type: "yield_bearing",       sub_type: "tbill_tokenized" },
  USYC:  { type: "yield_bearing",       sub_type: "tbill_tokenized" },
  sDAI:  { type: "yield_bearing",       sub_type: "defi_lending" },
  sUSDS: { type: "yield_bearing",       sub_type: "defi_lending" },
  aUSDC: { type: "yield_bearing",       sub_type: "defi_lending" },
  syrupUSDC:{ type: "yield_bearing",    sub_type: "undercollat_lending" },
  USDe:  { type: "yield_bearing",       sub_type: "delta_neutral" },
  sUSDe: { type: "yield_bearing",       sub_type: "delta_neutral" },
  USDD:  { type: "algorithmic",         sub_type: "reserve_backed" },
  FRAX:  { type: "algorithmic",         sub_type: "fractional" },
};

export const TYPE_META = {
  fiat_backed:         { label: "Fiat",   badge: "badge-fiat",   color: "#3b82f6" },
  crypto_collateralized: { label: "Crypto", badge: "badge-crypto", color: "#8b5cf6" },
  yield_bearing:       { label: "Yield",  badge: "badge-yield",  color: "#10b981" },
  algorithmic:         { label: "Algo",   badge: "badge-algo",   color: "#f59e0b" },
};

export function getTypeBadge(symbol) {
  const info = STABLECOIN_TAXONOMY[symbol];
  if (!info) return { label: "", badgeClass: "", color: "", type: "unknown" };
  const meta = TYPE_META[info.type] || {};
  return { label: meta.label || info.type, badgeClass: meta.badge || "", color: meta.color || "", type: info.type };
}

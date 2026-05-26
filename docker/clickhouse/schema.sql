-- ClickHouse schema for Helix Signal time-series analytics
-- ReplacingMergeTree(created_at) uses the most recent version per sort key.
-- Always query with FINAL or use argMax() for deduplicated results.

CREATE TABLE IF NOT EXISTS asset_trend_snapshots (
    asset_symbol String,
    timestamp DateTime64(3, 'UTC'),
    bucket_id UInt32,
    total_supply Nullable(Float64),
    price Nullable(Float64),
    depeg_index UInt8,
    signal_score UInt8,
    signal_band String,
    concentration_score UInt8,
    data_confidence_label String,
    source_status String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (asset_symbol, timestamp, bucket_id);

CREATE TABLE IF NOT EXISTS chain_trend_snapshots (
    asset_symbol String,
    chain_key String,
    chain_name String,
    timestamp DateTime64(3, 'UTC'),
    bucket_id UInt32,
    supply Nullable(Float64),
    supply_share_pct Nullable(Float64),
    chain_tvl Nullable(Float64),
    chain_signal_score UInt8,
    chain_signal_band String,
    data_confidence_score UInt8,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (asset_symbol, chain_key, timestamp);



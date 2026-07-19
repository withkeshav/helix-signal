import { formatUsd } from '../utils.js';

export function useFundamentals() {
  return {
    fundamentals: { yield: null, collateral: null, reserve: null },
    fundamentalsLoading: false,
    fundamentalsError: '',
    fundamentalsSymbol: '',

    async loadFundamentals(symbol) {
      this.fundamentalsSymbol = symbol;
      this.fundamentalsLoading = true;
      this.fundamentalsError = '';
      this.fundamentals = { yield: null, collateral: null, reserve: null };
      const failures = [];
      try {
        const [yRes, cRes, rRes] = await Promise.all([
          fetch(`/api/v1/assets/${symbol}/yield`, { cache: 'no-store' }).catch(() => null),
          fetch(`/api/v1/assets/${symbol}/collateral`, { cache: 'no-store' }).catch(() => null),
          fetch(`/api/v1/assets/${symbol}/reserve`, { cache: 'no-store' }).catch(() => null),
        ]);
        if (yRes && yRes.ok) this.fundamentals.yield = await yRes.json();
        else if (yRes && yRes.status !== 404) failures.push(`yield (${yRes.status})`);
        if (cRes && cRes.ok) this.fundamentals.collateral = await cRes.json();
        else if (cRes && cRes.status !== 404) failures.push(`collateral (${cRes.status})`);
        if (rRes && rRes.ok) this.fundamentals.reserve = await rRes.json();
        else if (rRes && rRes.status !== 404) failures.push(`reserve (${rRes.status})`);
        if (failures.length) this.fundamentalsError = `Failed: ${failures.join(', ')}`;
      } catch (e) {
        this.fundamentalsError = `Failed to load fundamentals: ${e.message}`;
      } finally {
        this.fundamentalsLoading = false;
      }
    },

    hasAnyFundamentals() {
      return !!(this.fundamentals.yield || this.fundamentals.collateral || this.fundamentals.reserve);
    },

    fmtPct(v) {
      if (v == null) return '-';
      return (v * 100).toFixed(2) + '%';
    },

    fmtUsd: formatUsd,

    fmtDate(iso) {
      if (!iso) return '-';
      return new Date(iso).toLocaleDateString();
    },
  };
}
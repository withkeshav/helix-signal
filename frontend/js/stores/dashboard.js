export function registerDashboardStore(Alpine) {
  Alpine.store('dashboard', {
    asset: 'USDT',
    timeRange: '7d',
    chainData: [],
    sources: [],
    signal: {},
    crossSource: {},
    supplyFeed: {},
    attSignal: {},
    depeg: {},
    concentration: {},
    freshness: {},
    totalSupply: null,
    supplyChange: null,
    generatedAt: '',
    staleWarning: '',
    errorOverview: '',
    predictive: {},
    marketOverview: '',
    aiNarrative: '',
    aiInsights: '',
    nlpAvailable: false,
    loading: false,

    init() {
      this.asset = 'USDT';
      this.timeRange = '7d';
    },

    setAsset(symbol) {
      this.asset = symbol;
    },

    setTimeRange(range) {
      this.timeRange = range;
    },
  });
}

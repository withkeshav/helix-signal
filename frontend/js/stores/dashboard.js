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
    dews: {},
    anomalyCount: 0,
    marketOverview: '',
    aiNarrative: '',
    aiInsights: '',
    nlpAvailable: false,
    signalSpark: '',
    dewsSpark: '',
    pegSpark: '',
    supplySpark: '',
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

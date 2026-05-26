export function helixForecast() {
  return {
    forecastSignals: [],
    correlations: [],
    forecastAccuracy: [],
    refreshingForecast: false,
    refreshingCorrelations: false,
    loadingForecast: false,
    errorForecast: '',
    _forecastData: null,

    async loadForecastData(asset) {
      if (this.refreshingForecast) return;
      this.refreshingForecast = true;
      this.loadingForecast = true;
      this.errorForecast = '';
      try {
        await this.loadCorrelations(asset);
        const f = await fetch(`/api/forecasts?asset=${asset}`, { cache: 'no-store' });
        if (f.ok) {
          this._forecastData = await f.json();
        } else {
          this.errorForecast = `Forecast API: HTTP ${f.status}`;
        }
        const ev = await fetch(`/api/events?asset=${asset}&limit=20`, { cache: 'no-store' });
        if (ev.ok) {
          const eventsBody = await ev.json();
          this.forecastSignals = (eventsBody.events || []).filter(e => String(e.event_type || '').startsWith('forecast_'));
        }
        if (typeof this.renderForecastCharts === 'function') {
          this.renderForecastCharts();
        }
      } catch (e) { this.errorForecast = 'Failed to load forecast data'; }
      finally { this.refreshingForecast = false; this.loadingForecast = false; }
    },

    async loadCorrelations(asset) {
      if (this.refreshingCorrelations) return;
      this.refreshingCorrelations = true;
      try {
        const r = await fetch(`/api/analytics/correlations?asset=${asset}&window_days=30`, { cache: 'no-store' });
        if (r.ok) { const j = await r.json(); this.correlations = j.pairs || []; }
      } catch (e) { this.correlations = []; }
      finally { this.refreshingCorrelations = false; }
    },

    async loadForecastAccuracy(asset) {
      try {
        const r = await fetch(`/api/analytics/forecast-accuracy?asset=${asset}&max_runs=5`, { cache: 'no-store' });
        if (r.ok) this.forecastAccuracy = await r.json();
      } catch (e) {}
    },
  };
}

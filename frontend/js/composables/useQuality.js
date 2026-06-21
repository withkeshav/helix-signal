export function useQuality() {
  return {
    // Data quality metrics
    overallQualityScore: null,
    sourceHealthScore: null,
    assetCompletenessScore: null,
    consistencyScore: null,
    freshnessScore: null,
    
    // Source metrics
    totalSources: 0,
    healthySources: 0,
    degradedSources: 0,
    downSources: 0,
    sourcesByStatus: {},
    
    // Usage metrics
    totalApiCalls: null,
    totalAiTokens: null,
    
    // UI state
    lastUpdated: null,
    loading: false,
    error: null,
    
    async init() {
      await this.loadQualityData();
    },

    get adminToken() {
      return this.$store.ui.adminToken;
    },
    
    _adminHeaders() {
      return this.$store.ui.adminHeaders();
    },
    
    async loadQualityData() {
      try {
        this.loading = true;
        this.error = null;
        
        // Fetch data quality overview
        const response = await fetch('/api/data-quality/overview', {
          headers: this._adminHeaders()
        });
        
        if (response.ok) {
          const data = await response.json();
          
          // Update quality scores
          this.overallQualityScore = data.overall_score;
          this.sourceHealthScore = data.source_health_score;
          this.assetCompletenessScore = data.asset_completeness_score;
          this.consistencyScore = data.consistency_score;
          this.freshnessScore = data.freshness_score;
          
          // Update source metrics if available
          if (data.components && data.components.source_quality) {
            const sourceQuality = data.components.source_quality;
            this.totalSources = sourceQuality.total_sources || 0;
            this.healthySources = sourceQuality.healthy_sources || 0;
            this.degradedSources = sourceQuality.degraded_sources || 0;
            this.downSources = sourceQuality.down_sources || 0;
            this.sourcesByStatus = sourceQuality.sources_by_status || {};
          }
          
          // Update usage metrics if available
          if (data.components && data.components.usage_metrics) {
            const usage = data.components.usage_metrics;
            this.totalApiCalls = usage.total_api_calls || 0;
            this.totalAiTokens = usage.total_ai_tokens || 0;
          }
          
          this.lastUpdated = new Date().toLocaleTimeString();
        } else {
          this.error = `Failed to load data quality metrics: ${response.status}`;
        }
      } catch (e) {
        this.error = `Error loading data quality metrics: ${e.message}`;
        console.error('Error loading quality data:', e);
      } finally {
        this.loading = false;
      }
    },
    
    async refreshQualityData() {
      await this.loadQualityData();
    },
    
    async loadSourceQuality() {
      try {
        const response = await fetch('/api/data-quality/sources', {
          headers: this._adminHeaders()
        });
        
        if (response.ok) {
          const data = await response.json();
          // Process source quality data
          return data;
        }
      } catch (e) {
        console.error('Error loading source quality:', e);
      }
      return null;
    },
    
    async loadAssetQuality(asset = null) {
      try {
        const url = asset 
          ? `/api/data-quality/assets?asset=${encodeURIComponent(asset)}`
          : `/api/data-quality/assets`;
          
        const response = await fetch(url, {
          headers: this._adminHeaders()
        });
        
        if (response.ok) {
          const data = await response.json();
          // Process asset quality data
          return data;
        }
      } catch (e) {
        console.error('Error loading asset quality:', e);
      }
      return null;
    }
  };
}
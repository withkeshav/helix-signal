function formatUsd(v) {
  if (v == null || Number.isNaN(Number(v))) return 'N/A';
  const n=Number(v);
  if(Math.abs(n)>=1e9) return `$${(n/1e9).toFixed(2)}B`;
  if(Math.abs(n)>=1e6) return `$${(n/1e6).toFixed(2)}M`;
  return `$${n.toLocaleString(undefined,{maximumFractionDigits:2})}`;
}
function formatWhen(iso) {
  if(!iso)return'';const d=new Date(iso);const s=(Date.now()-d.getTime())/1e3;
  if(s<90)return'just now';if(s<3600)return`${Math.round(s/60)} min ago`;
  if(s<86400)return`${Math.round(s/3600)}h ago · ${d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
  return `${d.toLocaleString()} · ${Intl.DateTimeFormat().resolvedOptions().timeZone}`;
}
function formatFeedAge(minutes) {
  if(minutes==null||Number.isNaN(Number(minutes)))return'No data';
  const m=Number(minutes);
  if(m<1)return'just now';if(m<60)return`${Math.round(m)}m ago`;
  if(m<1440)return`${Math.round(m/60)}h ago`;return`${Math.round(m/1440)}d ago`;
}
function statusBand(status) {
  if(status==='fresh'||status==='normal')return'normal';
  if(status==='aging'||status==='watch')return'watch';
  if(status==='n/a')return'normal';
  return'risk';
}
function attestationSummary(a) {
  if(!a)return'No data';
  if(a.attestation_status==='n/a')return'On-chain only';
  if(a.attestation_status==='unknown')return'Report: unknown';
  const age=a.attestation_age_days!=null?` (${a.attestation_age_days}d)`:'';
  return`Report: ${a.attestation_status}${age}`;
}
function supplyFeedSummary(a) {
  if(!a)return'No data';
  const age=formatFeedAge(a.supply_feed_age_minutes);
  return`Supply feed: ${a.supply_feed_status||'unknown'} · ${age}`;
}
function pegLabel(p) {
  const d=Math.abs(p-1);if(d<=.001)return'Healthy';if(d<=.005)return'Watch';return'Alert';
}
function helixApp() {
  return {
    tab:'market',theme:'light',asset:'USDT',searchQuery:'',searchResults:[],
    enabledAssets:['USDT','USDC','DAI','PYUSD'],
    chains:[],signal:{},depeg:{},concentration:{},freshness:{},sources:[],
    attestation:{},osintArticles:[],events:[],totalSupply:null,supplyChange:null,
    crossSource:{},staleWarning:'',generatedAt:'',
    _charts:new Map(),_echarts:null,_timer:null,_refreshingStale:false,
    refreshing:false,refreshingForecast:false,refreshingCorrelations:false,
    predictive:{},aiSummary:'',tickerItems:[],
    evidenceOpen:false,evidenceTitle:'',evidenceFormula:'',evidenceComponents:{},evidenceSources:{},
    forecastSignals:[],correlations:[],dataQualityHistory:[],
    get gaugeArc() {
      const s=Number(this.signal.score);if(Number.isNaN(s))return 0;
      return Math.max(0,Math.min(251,(s/100)*251));
    },
    get gaugeColor() {
      const b=(this.signal.band||'').toLowerCase();
      if(b==='risk')return'var(--down)';if(b==='watch')return'var(--neutral)';return'var(--up)';
    },
    async init() {
      const root=document.documentElement;
      this.theme=root.getAttribute('data-theme')||'light';
      await this.loadAssets();
      await this.loadDashboard();
      await this.loadAttestation();
      this._timer=setInterval(()=>{this.loadDashboard();},60000);
    },
    async search() {
      const q=this.searchQuery.trim();
      if(!q||q.length<2){this.searchResults=[];return;}
      this.searchResults=[];
      for(const a of this.enabledAssets){
        if(a.toLowerCase().includes(q.toLowerCase())){
          this.searchResults.push({id:`asset-${a}`,label:a,type:'Asset'});
        }
      }
      if(this.searchResults.length===0&&q.length>=2){
        this.searchResults.push({id:'custom',label:q.toUpperCase(),type:'Switch asset'});
      }
    },
    selectSearchResult(r) {
      if(r.id==='custom'&&!this.enabledAssets.includes(r.label)){
        this.enabledAssets.push(r.label);
      }
      this.asset=r.label;
      this.searchQuery='';
      this.searchResults=[];
      this.switchAsset();
    },
    showEvidence(type) {
      if(type==='score'){
        this.evidenceTitle=`Risk Score Evidence · ${this.asset}`;
        this.evidenceFormula='score = peg_deviation * w1 + concentration * w2 + liquidity * w3 + supply_momentum * w4';
        this.evidenceComponents=this.signal.components||{};
        this.evidenceSources={};
        for(const s of this.sources)this.evidenceSources[s.source_name]={status:s.status};
      }else if(type==='peg'){
        this.evidenceTitle=`Peg Evidence · ${this.asset}`;
        this.evidenceFormula='depeg_index = round(abs(deviation_bps) / 100 * 100, 0)';
        this.evidenceComponents={
          current_price:this.depeg.current_price,
          deviation_abs:this.depeg.deviation_abs,
          deviation_pct:this.depeg.deviation_pct,
          peg_status:this.depeg.peg_status,
          depeg_index:this.depeg.score,
        };
        this.evidenceSources={
          defillama:{status:'ok'},
          coingecko:{status:'ok'},
          dexscreener:{status:'ok'},
        };
      }
      this.evidenceOpen=true;
    },
    copyEvidence() {
      const txt=[`Title: ${this.evidenceTitle}`];
      if(this.evidenceFormula)txt.push(`Formula: ${this.evidenceFormula}`);
      const comps=Object.entries(this.evidenceComponents).map(([k,v])=>`  ${k}: ${v}`);
      if(comps.length)txt.push('Components:',...comps);
      navigator.clipboard?.writeText(txt.join('\n'));
    },
    async loadPredictive() {
      try{
        const r=await fetch(`/api/predictive?asset=${this.asset}`,{cache:'no-store'});
        if(r.ok)this.predictive=await r.json();
      }catch(e){this.predictive={available:false};}
    },
    async loadAiExplain() {
      try{
        const r=await fetch(`/api/ai/explain?asset=${this.asset}`,{cache:'no-store'});
        if(r.ok){const j=await r.json();this.aiSummary=j.available?j.summary:(j.reason||'');}
      }catch(e){this.aiSummary='';}
    },
    async loadTicker() {
      try{
        const r=await fetch(`/api/events?asset=${this.asset}&limit=12`,{cache:'no-store'});
        if(!r.ok)return;
        const j=await r.json();
        const evs=j.events||[];
        const items=evs.map(e=>`${e.severity?.toUpperCase()||'INFO'} · ${e.title||'event'} · ${formatWhen(e.timestamp)}`);
        this.tickerItems=items.length?items.concat(items):[];
      }catch(e){this.tickerItems=[];}
    },
    async loadAttestation() {
      try{const r=await fetch('/api/osint/attestation',{cache:'no-store'});if(r.ok)this.attestation=await r.json();}catch(e){}
    },
    async loadAssets() {
      try{const r=await fetch('/api/assets',{cache:'no-store'});if(r.ok){const a=await r.json();this.enabledAssets=a.map(x=>x.symbol);}}catch(e){}
    },
    async loadDashboard() {
      try{
        const r=await fetch(`/api/dashboard?asset=${this.asset}`,{cache:'no-store'});
        if(!r.ok)throw Error(`HTTP ${r.status}`);
        const d=await r.json();
        this.assetName=d.asset?.name||this.asset;
        this.chains=d.chains||[];
        this.signal=d.asset_signal||{};
        this.depeg=d.depeg_index||{};
        this.concentration=d.chain_concentration||{};
        this.freshness=d.freshness||{};
        this.sources=d.sources||[];
        this.totalSupply=d.total_supply_current;
        this.supplyChange=d.total_supply_change_24h_pct;
        this.generatedAt=new Date().toLocaleTimeString();
        this.staleWarning=this.freshness.status==='Stale'?'Data is stale. Metrics may not reflect current conditions.':'';
        if(d.data_quality) {
          this.dataQualityHistory=[d.data_quality];
        }
        if(this.freshness.status==='Stale'&&!this._refreshingStale){
          this._refreshingStale=true;
          this.refresh().finally(()=>{this._refreshingStale=false;});
        }
        this.renderCharts(d);
        this._updateCrossSource();
        await this.loadPredictive();
        await this.loadTicker();
        await this.loadAiExplain();
        if(this.tab==='intel')this.loadIntel();
        if(this.tab==='events')this.loadEvents();
        if(this.tab==='forecast'){this.loadForecastData();}
      }catch(e){this.staleWarning=`Dashboard error: ${e.message}`;}
    },
    _updateCrossSource() {
      const prices=[];
      for(const c of this.chains){
        if(c.price>0)prices.push(c.price);
        if(c.price_coingecko>0)prices.push(c.price_coingecko);
        if(c.price_dexscreener>0)prices.push(c.price_dexscreener);
      }
      if(prices.length<2){this.crossSource={sources_agreeing:prices.length,discrepancy_flag:false,max_discrepancy_pct:0};return;}
      const mean=prices.reduce((a,b)=>a+b,0)/prices.length;
      const maxDisc=Math.max(...prices.map(v=>Math.abs(v-mean)/mean*100));
      this.crossSource={sources_agreeing:prices.length,max_discrepancy_pct:maxDisc,discrepancy_flag:maxDisc>0.5};
    },
    async loadTab() {
      if(this.tab==='forecast')this.loadForecastData();
      if(this.tab==='intel')this.loadIntel();
      if(this.tab==='events')this.loadEvents();
      if(this.tab==='supply')this.loadSupplyTrend();
    },
    async loadEvents() {
      try{
        const ev=await fetch(`/api/events?asset=${this.asset}&limit=30`,{cache:'no-store'});
        if(ev.ok){const j=await ev.json();this.events=j.events||[];}
      }catch(e){}
      try{
        const r=await fetch(`/api/osint/feed?asset=${this.asset}&limit=15`,{cache:'no-store'});
        if(r.ok){this.osintArticles=await r.json();}
      }catch(e){}
      try{
        const s=await fetch(`/api/osint/sentiment?asset=${this.asset}&window_days=7`,{cache:'no-store'});
        if(s.ok){
          const series=await s.json();
          if(Array.isArray(series)&&series.length>0){this.renderSentimentChart(series);}
        }
      }catch(e){}
    },
    async loadIntel() {
      await this.loadAttestation();
    },
    async loadForecastData() {
      if(this.refreshingForecast)return;
      this.refreshingForecast=true;
      try{
        await this.loadCorrelations();
        const f=await fetch(`/api/forecasts?asset=${this.asset}`,{cache:'no-store'});
        if(f.ok){
          const body=await f.json();
          this.forecastSignals=body.forecasts||[];
          this._forecastData=body;
        }
        this.renderForecastCharts();
      }catch(e){}finally{this.refreshingForecast=false;}
    },
    async loadCorrelations() {
      if(this.refreshingCorrelations)return;
      this.refreshingCorrelations=true;
      try{
        const r=await fetch(`/api/analytics/correlations?asset=${this.asset}&window_days=30`,{cache:'no-store'});
        if(r.ok){const j=await r.json();this.correlations=j.pairs||[];}
      }catch(e){this.correlations=[];}finally{this.refreshingCorrelations=false;}
    },
    async loadSupplyTrend() {
      try{
        const r=await fetch(`/api/trends?asset=${this.asset}&window=30d`,{cache:'no-store'});
        if(r.ok){
          const j=await r.json();
          if(j.points&&j.points.length&&typeof Chart!=='undefined'){
            const el=document.getElementById('chart-supply-trend');
            if(!el)return;
            if(this._charts.has('chart-supply-trend'))this._charts.get('chart-supply-trend').destroy();
            const pts=j.points.filter(p=>p.total_supply!=null).map(p=>({x:new Date(p.timestamp).getTime(),y:Number(p.total_supply)}));
            const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
            this._charts.set('chart-supply-trend',new Chart(el.getContext('2d'),{
              type:'line',
              data:{datasets:[{data:pts,borderColor:primary,backgroundColor:'rgba(59,130,246,0.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}]},
              options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},
                scales:{x:{type:'linear',ticks:{display:false},grid:{display:false}},y:{ticks:{callback:v=>formatUsd(v)}}}}
            }));
          }
        }
      }catch(e){}
    },
    async refresh() {
      this.refreshing=true;
      try{const r=await fetch('/api/refresh',{method:'POST',cache:'no-store'});if(!r.ok)throw Error(`HTTP ${r.status}`);}catch(e){}
      await this.loadDashboard();
      this.refreshing=false;
    },
    cycleTheme() {
      const root=document.documentElement;
      this.theme=this.theme==='light'?'dark':'light';
      root.setAttribute('data-theme',this.theme);
      if (this.chains.length) {
        this.destroyCharts();
        this.renderCharts({chains: this.chains});
      }
    },
    destroyCharts(){
      for(const[_,c]of this._charts)c.destroy();
      this._charts.clear();
    },
    renderCharts(data){
      this.destroyCharts();
      if(typeof Chart==='undefined')return;
      const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
      const chains=data.chains||[];
      if(chains.length){
        const sorted=[...chains].sort((a,b)=>Number(b.chain_share_pct||0)-Number(a.chain_share_pct||0)).slice(0,12);
        const labels=sorted.map(c=>c.chain_name);
        const vals=sorted.map(c=>c.chain_share_pct||0);
        const supplyLabels=sorted.map(c=>c.chain_name);
        const supplyVals=sorted.map(c=>c.supply_current||0);
        this._makeBar('chart-distribution',labels,vals,primary);
        this._makeBar('chart-supply-bar',supplyLabels,supplyVals,primary);
      }
      this.loadTrendChart();
    },
    loadTrendChart(){
      const _asset=this.asset;
      try{
        const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#9aa8c4';
        const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
        fetch(`/api/trends?asset=${this.asset}&window=7d`,{cache:'no-store'})
          .then(r=>r.ok?r.json():null)
          .then(t=>{
            if(this.asset!==_asset) return;
            if(!t||!t.points||!t.points.length||typeof Chart==='undefined') return;
            const el=document.getElementById('chart-trend-signal');
            if(!el) return;
            if(this._charts.has('chart-trend-signal')) this._charts.get('chart-trend-signal').destroy();
            const pts=t.points.map(p=>({x:new Date(p.timestamp).getTime(),y:p.signal_score!=null?Number(p.signal_score):null}));
            this._charts.set('chart-trend-signal',new Chart(el.getContext('2d'),{
              type:'line',
              data:{datasets:[{data:pts,borderColor:primary,backgroundColor:'rgba(59,130,246,0.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}]},
              options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},
                scales:{x:{type:'linear',ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}},y:{min:0,max:100,ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}}}}
            }));
          })
          .catch(()=>{});
      }catch(e){}
    },
    _makeBar(canvasId,labels,values,color) {
      if(this._charts.has(canvasId))this._charts.get(canvasId).destroy();
      const el=document.getElementById(canvasId);
      if(!el||typeof Chart==='undefined')return;
      const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#9aa8c4';
      this._charts.set(canvasId,new Chart(el.getContext('2d'),{
        type:'bar',data:{labels,datasets:[{label:'',data:values,backgroundColor:color,borderRadius:4}]},
        options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},
          scales:{x:{ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}},y:{ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}}}}
      }));
    },
    renderSentimentChart(series){
      if(!series||!series.length||typeof Chart==='undefined')return;
      if(this._charts.has('chart-sentiment'))this._charts.get('chart-sentiment').destroy();
      const el=document.getElementById('chart-sentiment');
      if(!el)return;
      const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
      this._charts.set('chart-sentiment',new Chart(el.getContext('2d'),{type:'line',data:{labels:series.map(s=>s.date),datasets:[{label:'Avg Sentiment',data:series.map(s=>s.avg_sentiment),borderColor:primary,fill:false,tension:.25}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{min:-1,max:1}}}}));
    },
    renderForecastCharts() {
      if(typeof echarts==='undefined')return;
      if(this._echarts){echarts.dispose(this._echarts);this._echarts=null;}
      const elPeg=document.getElementById('chart-peg-forecast');
      const elSupply=document.getElementById('chart-supply-forecast');
      if(!elPeg||!elSupply)return;
      const textColor=getComputedStyle(document.documentElement).getPropertyValue('--text').trim()||'#e8edf7';
      const lineColor=getComputedStyle(document.documentElement).getPropertyValue('--line').trim()||'#273247';
      const baseConfig={
        tooltip:{trigger:'axis'},grid:{left:50,right:16,top:20,bottom:36},
        xAxis:{type:'time',axisLine:{lineStyle:{color:lineColor}},axisLabel:{color:textColor}},
        yAxis:{type:'value',splitLine:{lineStyle:{color:lineColor,opacity:0.2}},axisLabel:{color:textColor}},
        legend:{bottom:0,textStyle:{color:textColor,fontSize:11}},
        animation:false,
      };
      const data=this._forecastData||{};
      const forecast=(data.forecast_points&&(data.forecast_points.peg||data.forecast_points.supply))||[];
      const historical=(data.historical&&(data.historical.peg||data.historical.supply))||[];
      this._renderForecastCanvas(elPeg,'Peg Forecast',historical,forecast||[],baseConfig,textColor,lineColor);
      const supplyForecast=(data.forecast_points&&data.forecast_points.supply)||[];
      const supplyHistorical=(data.historical&&data.historical.supply)||[];
      this._renderForecastCanvas(elSupply,'Supply Forecast',supplyHistorical,supplyForecast,baseConfig,textColor,lineColor);
    },
    _renderForecastCanvas(el,title,historical,forecast,baseConfig,textColor,lineColor) {
      if(this._charts.has(el.id)){this._charts.get(el.id).dispose();this._charts.delete(el.id);}
      const chart=echarts.init(el);
      this._charts.set(el.id,chart);
      const option={...baseConfig,
        title:{text:title,left:'center',top:0,textStyle:{color:textColor,fontSize:13,fontWeight:500}},
        grid:{left:50,right:16,top:36,bottom:40},
        series:forecast&&forecast.length?[
          {name:'q10 base',type:'line',data:forecast.map(p=>[p.timestamp,p.q10??p.q50*0.997]),lineStyle:{opacity:0},itemStyle:{opacity:0},stack:'confidence',areaStyle:{color:'rgba(59,130,246,0.06)'},symbol:'none'},
          {name:'90% Band',type:'line',data:forecast.map(p=>[p.timestamp,Math.max(0,(p.q90??p.q50)-p.q10)]),lineStyle:{opacity:0},itemStyle:{opacity:0},stack:'confidence',areaStyle:{color:'rgba(59,130,246,0.08)'},symbol:'none'},
          {name:'Median',type:'line',data:forecast.map(p=>[p.timestamp,p.q50]),lineStyle:{width:2,color:'#3b82f6'},symbol:'none',z:10},
          {name:'Historical',type:'line',data:historical?historical.map(p=>[p.timestamp,p.value]):[],lineStyle:{width:1.5,color:textColor},symbolSize:2,z:10},
        ]:[
          {name:'No forecast data',type:'line',data:historical?historical.map(p=>[p.timestamp,p.value]):[],lineStyle:{width:1.5,color:textColor},symbolSize:2,z:10},
        ],
      };
      chart.setOption(option);
      if(!window._helixResizeHandler){
        window._helixResizeHandler=()=>{for(const[_,c]of this._charts){if(!c.isDisposed())c.resize();}};
        window.addEventListener('resize',window._helixResizeHandler);
      }
    },
    async switchAsset() {
      this.destroyCharts();
      if(this._echarts){echarts.dispose(this._echarts);this._echarts=null;}
      await this.loadDashboard();
    }
  };
}

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
        if(m<1)return'just now';
        if(m<60)return`${Math.round(m)}m ago`;
        if(m<1440)return`${Math.round(m/60)}h ago`;
        return`${Math.round(m/1440)}d ago`;
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
          tab: 'overview', asset: 'USDT', assetName: 'Tether USD', enabledAssets: ['USDT','USDC','DAI','PYUSD'],
          chains: [], signal: {}, depeg: {}, concentration: {}, freshness: {}, sources: [],
          attestation: {}, osintArticles: [], events: [], totalSupply: null, supplyChange: null,
          crossSource: {}, staleWarning: '', generatedAt: '', _charts: new Map(), _timer: null,
          async init() {
            await this.loadAssets();
            await this.loadDashboard();
            await this.loadAttestation();
            this._timer=setInterval(()=>this.loadDashboard(),60000);
          },
          async loadAttestation() {
            try{
              const r=await fetch('/api/osint/attestation',{cache:'no-store'});
              if(r.ok)this.attestation=await r.json();
            }catch(e){}
          },
          async loadAssets() {
            try{
              const r=await fetch('/api/assets',{cache:'no-store'});
              if(r.ok){const a=await r.json();this.enabledAssets=a.map(x=>x.symbol);}
            }catch(e){}
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
              this.renderCharts(d);
              if(this.tab==='intel')this.loadIntel();
            }catch(e){this.staleWarning=`Dashboard error: ${e.message}`;}
          },
          async loadTab() {
            if(this.tab==='intel')this.loadIntel();
          },
          async loadIntel() {
            try{
              const r=await fetch(`/api/osint/feed?asset=${this.asset}&limit=10`,{cache:'no-store'});
              if(r.ok){
                const rows=await r.json();
                if(Array.isArray(rows)&&rows.length>0){
                  this.osintArticles=rows;
                }else{
                  const fallback=await fetch(`/api/osint/feed?limit=10`,{cache:'no-store'});
                  this.osintArticles=fallback.ok?await fallback.json():[];
                }
              }
            }catch(e){}
            await this.loadAttestation();
            try{
              const ev=await fetch(`/api/events?asset=${this.asset}&limit=20`,{cache:'no-store'});
              if(ev.ok){const j=await ev.json();this.events=j.events||[];}
            }catch(e){}
            try{
              const s=await fetch(`/api/osint/sentiment?asset=${this.asset}&window_days=7`,{cache:'no-store'});
              if(s.ok){
                const series=await s.json();
                if(Array.isArray(series)&&series.length>0){
                  this.renderSentimentChart(series);
                }else{
                  const fallback=await fetch(`/api/osint/sentiment?window_days=7`,{cache:'no-store'});
                  if(fallback.ok)this.renderSentimentChart(await fallback.json());
                }
              }
            }catch(e){}
          },
          async refresh() {
            try{await fetch('/api/refresh',{method:'POST',cache:'no-store'});}catch(e){}
            await this.loadDashboard();
          },
          cycleTheme() {
            const root=document.documentElement;
            const cur=root.getAttribute('data-theme')||'light';
            root.setAttribute('data-theme',cur==='light'?'dark':'light');
          },
          destroyCharts(){
            for(const[_,c]of this._charts)c.destroy();
            this._charts.clear();
          },
          renderCharts(data){
            this.destroyCharts();
            if(typeof Chart==='undefined')return;
            const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
            const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#9aa8c4';
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
            try{
              const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#9aa8c4';
              const primary=getComputedStyle(document.documentElement).getPropertyValue('--spark').trim()||'#60a5fa';
              fetch(`/api/trends?asset=${this.asset}&window=7d`,{cache:'no-store'})
                .then(r=>r.ok?r.json():null)
                .then(t=>{
                  if(!t||!t.points||!t.points.length||typeof Chart==='undefined') return;
                  const el=document.getElementById('chart-trend-signal');
                  if(!el) return;
                  if(this._charts.has('chart-trend-signal')) this._charts.get('chart-trend-signal').destroy();
                  const pts=t.points.map(p=>({x:new Date(p.timestamp).getTime(), y:p.signal_score!=null?Number(p.signal_score):null}));
                  const trendChart=new Chart(el.getContext('2d'),{
                    type:'line',
                    data:{datasets:[{data:pts,borderColor:primary,backgroundColor:'rgba(59,130,246,0.08)',fill:true,tension:.25,pointRadius:0,borderWidth:2}]},
                    options:{
                      responsive:true,
                      maintainAspectRatio:false,
                      animation:false,
                      plugins:{legend:{display:false}},
                      scales:{
                        x:{type:'linear',ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}},
                        y:{min:0,max:100,ticks:{color:muted},grid:{color:'rgba(128,128,128,0.1)'}}
                      }
                    }
                  });
                  this._charts.set('chart-trend-signal',trendChart);
                })
                .catch(()=>{});
            }catch(e){}
          },
          _makeBar(canvasId, labels, values, color) {
            if(this._charts.has(canvasId))this._charts.get(canvasId).destroy();
            const el=document.getElementById(canvasId);
            if(!el||typeof Chart==='undefined')return;
            const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#9aa8c4';
            this._charts.set(canvasId, new Chart(el.getContext('2d'),{
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
          async switchAsset() {
            await this.loadDashboard();
          }
        };
      }

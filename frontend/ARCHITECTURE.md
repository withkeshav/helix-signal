# Helix Signal Frontend Architecture

## Overview

This document describes the Alpine.js component architecture introduced in Phase 1 of the frontend overhaul (May 2026). The system follows a clean, modular pattern with separation of concerns, reactive state management, and composable components.

## Core Patterns

### 1. Alpine Stores (Global State Management)

Shared reactive state is managed through Alpine stores. Each store handles a specific domain of data.

**Available Stores:**
- `stores/dashboard.js` - Asset, time range, and core dashboard data
- `stores/ui.js` - Theme, active tab, search state, auth tokens, version
- `stores/osint.js` - OSINT/Events tab shared data
- `stores/forecast.js` - Forecast tab shared data

**Usage:**
```js
// In JavaScript components
Alpine.store('ui').theme
Alpine.store('dashboard').asset

// In HTML templates  
$store.ui.theme
$store.dashboard.asset
```

**Best Practices:**
- Use stores for data that multiple components need
- Keep store data normalized and minimal
- Update store data through store methods, not directly
- Prefer specific stores over generic ones

### 2. Alpine Composables (Reusable Component Logic)

Composable functions encapsulate component-specific logic and state. Each tab/feature area has its own composable.

**Available Composables:**
- `composables/useGovernance.js` - Settings tab logic
- `composables/useHealth.js` - Health/status tab logic
- `composables/useMarket.js` - Market/Overview tab logic
- `composables/useOSINT.js` - OSINT/Events tab logic
- `composables/useForecast.js` - Forecast tab logic
- `composables/useQuality.js` - Data quality tab logic

**Usage:**
```js
// In init.js - register composable
import { useGovernance } from 'composables/useGovernance.js'
Alpine.data('governance', useGovernance)

// In HTML - bind component
<div x-data="governance" x-init="loadSettings()">
```

**Structure:**
```js
export function useMyComponent() {
  return {
    // Reactive state properties
    myData: [],
    loading: false,
    
    // Computed properties (getters)
    get formattedData() {
      return this.myData.map(item => formatItem(item));
    },
    
    // Methods
    async loadData() {
      this.loading = true;
      try {
        const response = await fetch('/api/my-endpoint');
        this.myData = await response.json();
      } finally {
        this.loading = false;
      }
    },
    
    // Lifecycle hooks
    init() {
      // Component initialization
      this.loadData();
    }
  };
}
```

### 3. HTML Component Binding

Tabs bind to their composables via `x-data`. This creates isolated component scopes.

**Binding Pattern:**
```html
<!-- Settings tab -->
<div x-data="governance" x-init="loadSettings(); loadAiBudget();">

<!-- Events/Intel tabs -->  
<div x-data="osint">

<!-- Forecast tab -->
<div x-data="forecast">

<!-- Overview/Market tab -->
<div x-data="market">
```

## Data Flow Architecture

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   Stores    │◄──▶│ Composables  │◄──▶│   Template   │
│ (Global     │    │ (Component   │    │   (HTML)     │
│  State)     │    │  Logic)      │    │              │
└─────────────┘    └──────────────┘    └──────────────┘
       ▲                    ▲                   ▲
       │                    │                   │
       ▼                    ▼                   ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   API       │    │   Charts     │    │   Events     │
│ (Backend)   │    │ (Rendering)  │    │ (Messaging)  │
└─────────────┘    └──────────────┘    └──────────────┘
```

**Flow Steps:**
1. **Data Loading**: Components fetch data via API calls
2. **State Storage**: Data stored in appropriate Alpine stores
3. **Component Binding**: HTML binds to composables via `x-data`
4. **Reactivity**: Templates automatically update when store data changes
5. **Chart Management**: Charts rendered and cleaned up appropriately

## Chart Management

### Lifecycle Management
- Each composable manages its own chart instances
- Automatic cleanup when switching tabs
- Theme-aware re-rendering on theme changes
- Resize handling via global resize handler

### Implementation Pattern
```js
// In composable
import { renderMyChart, destroyMyChart } from '../charts.js';

export function useMyComponent() {
  return {
    _charts: new Map(),
    _echarts: new Map(),
    
    _renderChart() {
      renderMyChart.call(this, this.chartData);
    },
    
    _destroyCharts() {
      for (const [, c] of this._charts) this._disposeChart(c);
      this._charts.clear();
      for (const [, c] of this._echarts) this._disposeChart(c);
      this._echarts.clear();
    },
    
    init() {
      // Re-render on data changes
      this.$watch('chartData', () => this._renderChart());
      
      // Clean up when switching tabs
      this.$watch('$store.ui.tab', (newTab) => {
        if (newTab !== 'mytab') this._destroyCharts();
      });
    }
  };
}
```

## Event-Based Communication

Components communicate through custom events rather than direct method calls.

**Pattern:**
```js
// Parent dispatching events
this.$dispatch('asset-changed', { asset: symbol });

// Child listening for events (in init)
this.$watch('$store.ui.tab', (newTab) => {
  if (newTab === 'mytab') this.loadData();
});

// Cross-component communication
window.addEventListener('theme-changed', (e) => {
  this.reRenderWithTheme(e.detail.theme);
});
```

## Adding a New Tab (Step-by-Step Guide)

### 1. Create Store (if needed)
```js
// stores/mytab.js
export function registerMyTabStore(Alpine) {
  Alpine.store('mytab', {
    data: [],
    loading: false,
    
    async loadData() {
      this.loading = true;
      try {
        const r = await fetch('/api/my-endpoint');
        if (r.ok) this.data = await r.json();
      } finally {
        this.loading = false;
      }
    }
  });
}
```

### 2. Create Composable
```js
// composables/useMyTab.js
export function useMyTab() {
  return {
    // Properties will be reactive
    get myData() { return Alpine.store('mytab').data; },
    get loading() { return Alpine.store('mytab').loading; },
    
    async loadData() {
      await Alpine.store('mytab').loadData();
    },
    
    init() {
      this.loadData();
    }
  };
}
```

### 3. Register in init.js
```js
import { registerMyTabStore } from 'stores/mytab.js';
import { useMyTab } from 'composables/useMyTab.js';

registerMyTabStore(Alpine);
Alpine.data('mytab', useMyTab);
```

### 4. Create HTML Template
```html
<div class="tab-content" :class="tab === 'mytab' && 'active'" x-data="mytab">
  <div x-show="loading">Loading...</div>
  <div x-show="!loading">
    <template x-for="item in myData" :key="item.id">
      <div x-text="item.name"></div>
    </template>
  </div>
</div>
```

### 5. Add Navigation
```html
<button class="nav-link" :class="tab==='mytab'&&'active'" 
        @click="tab='mytab'">My Tab</button>
```

## Migration Status

- ✅ All frontend architecture overhaul complete
- ✅ Foundation (Import map, stores, composables)
- ✅ Core migrations (OSINT, Forecast, chart lifecycle, tests)
- ✅ Market/Overview tab migration
- ✅ Settings completion and hardening

## Best Practices

### State Management
- ✅ Use stores for shared/global data
- ✅ Keep component state in composables
- ✅ Prefer derived/computed properties over duplicated state
- ✅ Update state through defined methods, not direct mutation

### Component Design
- ✅ Single responsibility per composable
- ✅ Extract shared logic to utility functions
- ✅ Use clear, descriptive property/method names
- ✅ Handle loading/error states gracefully

### Performance  
- ✅ Clean up resources (charts, timers, event listeners)
- ✅ Use `$watch` judiciously to avoid unnecessary updates
- ✅ Debounce expensive operations
- ✅ Lazy load non-critical data

### Testing
- ✅ Backend API endpoints covered by integration tests
- ✅ Frontend interactions covered by E2E tests (Playwright)
- ✅ Core logic unit-testable in composables
- ✅ State changes testable through store methods

## Common Patterns

### Loading States
```html
<div x-show="loading" class="loading-spinner">Loading...</div>
<div x-show="error" class="error-message" x-text="error"></div>
<div x-show="!loading && !error && data.length === 0" class="empty-state">
  No data available
</div>
```

### Error Handling
```js
async loadData() {
  try {
    this.error = null;
    this.loading = true;
    const response = await fetch('/api/data');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    this.data = await response.json();
  } catch (err) {
    this.error = `Failed to load data: ${err.message}`;
    this.data = [];
  } finally {
    this.loading = false;
  }
}
```

### Theme Awareness
```js
init() {
  // Re-render on theme changes
  this.$watch('$store.ui.theme', () => {
    this._renderChart();
  });
}
```

## Getting Help

- **Architecture Questions**: Review this document and existing components
- **Implementation Help**: Study similar tabs (Governance/OSINT/Forecast/Market)
- **Debugging**: Use browser dev tools to inspect Alpine component scopes
- **Testing**: Run existing test suites and add coverage for new features
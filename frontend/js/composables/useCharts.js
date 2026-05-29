export function useCharts() {
  const _charts = new Map();
  const _echarts = new Map();
  let _resizeHandler = null;

  function dispose(c) {
    if (!c) return;
    if (typeof c.dispose === 'function') {
      if (typeof c.isDisposed !== 'function' || !c.isDisposed()) c.dispose();
    } else if (typeof c.destroy === 'function') {
      c.destroy();
    }
  }

  function destroyAll() {
    for (const [, c] of _charts) dispose(c);
    _charts.clear();
    for (const [, c] of _echarts) dispose(c);
    _echarts.clear();
    if (_resizeHandler) {
      window.removeEventListener('resize', _resizeHandler);
      _resizeHandler = null;
    }
  }

  function setupResize() {
    if (_resizeHandler) return;
    _resizeHandler = () => {
      for (const [, c] of _charts) {
        if (typeof c.resize === 'function') c.resize();
      }
      for (const [, c] of _echarts) {
        if (typeof c.isDisposed === 'function' && !c.isDisposed()) c.resize();
      }
    };
    window.addEventListener('resize', _resizeHandler);
  }

  function registerChart(key, instance, type = 'chartjs') {
    const map = type === 'echarts' ? _echarts : _charts;
    dispose(map.get(key));
    map.set(key, instance);
  }

  function getChart(key, type = 'chartjs') {
    const map = type === 'echarts' ? _echarts : _charts;
    return map.get(key);
  }

  function removeChart(key, type = 'chartjs') {
    const map = type === 'echarts' ? _echarts : _charts;
    dispose(map.get(key));
    map.delete(key);
  }

  return {
    dispose,
    destroyAll,
    setupResize,
    registerChart,
    getChart,
    removeChart,
    _charts,
    _echarts,
  };
}

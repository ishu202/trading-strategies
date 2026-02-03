/**
 * Main application logic.
 */
document.addEventListener('DOMContentLoaded', () => {
    // State
    let activeStrategy = null;
    let strategyParams = {};
    let autoRefreshTimer = null;

    // DOM refs
    const tabs = document.querySelectorAll('.strategy-tab');
    const instrumentSelect = document.getElementById('instrument-select');
    const intervalSelect = document.getElementById('interval-select');
    const fromDateInput = document.getElementById('from-date');
    const toDateInput = document.getElementById('to-date');
    const runBtn = document.getElementById('run-backtest');
    const toggleParamsBtn = document.getElementById('toggle-params');
    const paramsPanel = document.getElementById('params-panel');
    const paramsContainer = document.getElementById('params-container');
    const chartLoading = document.getElementById('chart-loading');

    // ----- Strategy tabs -----
    function activateTab(btn) {
        tabs.forEach(t => {
            t.classList.remove('bg-accent', 'text-white');
            t.classList.add('bg-surface', 'text-gray-400');
        });
        btn.classList.remove('bg-surface', 'text-gray-400');
        btn.classList.add('bg-accent', 'text-white');
        activeStrategy = btn.dataset.strategy;
        loadParameters(activeStrategy);
    }

    tabs.forEach(btn => {
        btn.addEventListener('click', () => activateTab(btn));
    });

    // Set default date range (last 30 days)
    const today = new Date();
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(today.getDate() - 30);
    toDateInput.value = today.toISOString().slice(0, 10);
    fromDateInput.value = thirtyDaysAgo.toISOString().slice(0, 10);

    // Activate first tab
    if (tabs.length > 0) {
        activateTab(tabs[0]);
    }

    // ----- Parameters -----
    toggleParamsBtn.addEventListener('click', () => {
        paramsPanel.classList.toggle('hidden');
    });

    async function loadParameters(strategyName) {
        try {
            const resp = await fetch(`/api/strategy/${strategyName}/parameters`);
            const data = await resp.json();
            strategyParams = data.parameters || {};
            renderParams(strategyParams);
        } catch (e) {
            console.error('Failed to load parameters:', e);
            paramsContainer.innerHTML = '<span class="text-red-400">Failed to load parameters</span>';
        }
    }

    function renderParams(params) {
        paramsContainer.innerHTML = '';
        for (const [key, value] of Object.entries(params)) {
            const wrapper = document.createElement('div');
            wrapper.className = 'flex flex-col gap-1';

            const label = document.createElement('label');
            label.className = 'text-gray-500 text-xs uppercase tracking-wider';
            label.textContent = key.replace(/_/g, ' ');
            wrapper.appendChild(label);

            if (typeof value === 'boolean') {
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = value;
                input.className = 'param-checkbox w-4 h-4';
                input.dataset.param = key;
                input.addEventListener('change', () => {
                    strategyParams[key] = input.checked;
                });
                wrapper.appendChild(input);
            } else {
                const input = document.createElement('input');
                input.type = typeof value === 'number' ? 'number' : 'text';
                input.value = value;
                input.step = Number.isInteger(value) ? '1' : '0.1';
                input.className = 'bg-surface border border-gray-700 rounded px-2 py-1 text-gray-200 w-24 text-sm focus:border-accent focus:outline-none';
                input.dataset.param = key;
                input.addEventListener('change', () => {
                    strategyParams[key] = input.type === 'number' ? parseFloat(input.value) : input.value;
                });
                wrapper.appendChild(input);
            }

            paramsContainer.appendChild(wrapper);
        }
    }

    // ----- Backtest -----
    runBtn.addEventListener('click', runBacktest);

    async function runBacktest() {
        if (!activeStrategy) return;

        chartLoading.classList.remove('hidden');
        runBtn.disabled = true;
        runBtn.textContent = 'Running…';

        try {
            const resp = await fetch('/api/backtest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy: activeStrategy,
                    instrument: instrumentSelect.value,
                    interval: intervalSelect.value,
                    from_date: fromDateInput.value,
                    to_date: toDateInput.value,
                    parameters: strategyParams,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.error || 'Backtest failed');
            }

            const data = await resp.json();
            renderResults(data);
        } catch (e) {
            console.error('Backtest error:', e);
            alert('Backtest failed: ' + e.message);
        } finally {
            chartLoading.classList.add('hidden');
            runBtn.disabled = false;
            runBtn.textContent = 'Run Backtest';
        }
    }

    function renderResults(data) {
        // Chart
        const chartContainer = document.getElementById('main-chart');
        ChartManager.createMainChart(chartContainer);
        ChartManager.setCandles(data.candles);
        ChartManager.setSignals(data.signals);

        // Overlays (Bollinger on main chart)
        const { rsi, ...mainOverlays } = data.overlays || {};
        ChartManager.setOverlays(mainOverlays);

        // RSI subplot
        let rsiContainer = document.getElementById('rsi-chart');
        if (!rsiContainer) {
            rsiContainer = document.createElement('div');
            rsiContainer.id = 'rsi-chart';
            rsiContainer.className = 'w-full border-t border-gray-700';
            rsiContainer.style.display = 'none';
            chartContainer.parentElement.appendChild(rsiContainer);
        }
        ChartManager.setRSI(rsiContainer, rsi);

        // Metrics
        updateMetrics(data.metrics);
    }

    function updateMetrics(m) {
        document.getElementById('metric-trades').textContent = m.total_trades;

        const winrateEl = document.getElementById('metric-winrate');
        winrateEl.textContent = m.win_rate + '%';
        winrateEl.className = 'font-semibold ' + (m.win_rate >= 50 ? 'text-green-400' : 'text-red-400');

        const pnlEl = document.getElementById('metric-pnl');
        pnlEl.textContent = (m.total_pnl >= 0 ? '+' : '') + m.total_pnl.toFixed(2);
        pnlEl.className = 'font-semibold ' + (m.total_pnl >= 0 ? 'text-green-400' : 'text-red-400');

        const sharpeEl = document.getElementById('metric-sharpe');
        sharpeEl.textContent = m.sharpe_ratio.toFixed(2);
        sharpeEl.className = 'font-semibold ' + (m.sharpe_ratio >= 1 ? 'text-green-400' : m.sharpe_ratio >= 0 ? 'text-yellow-400' : 'text-red-400');

        const ddEl = document.getElementById('metric-maxdd');
        ddEl.textContent = m.max_drawdown.toFixed(2) + '%';
        ddEl.className = 'font-semibold ' + (m.max_drawdown <= 10 ? 'text-green-400' : m.max_drawdown <= 20 ? 'text-yellow-400' : 'text-red-400');
    }

    // ----- Auto-refresh -----
    const refreshIntervalSelect = document.getElementById('refresh-interval');
    const autoRefreshBtn = document.getElementById('auto-refresh-btn');

    function startAutoRefresh() {
        stopAutoRefresh();
        const seconds = parseInt(refreshIntervalSelect.value, 10) * 1000;
        autoRefreshTimer = setInterval(() => {
            runBacktest();
        }, seconds);
        autoRefreshBtn.textContent = 'Stop';
        autoRefreshBtn.classList.remove('bg-surface', 'text-gray-400', 'hover:border-accent', 'hover:text-white');
        autoRefreshBtn.classList.add('bg-green-700', 'text-white', 'border-green-600');
    }

    function stopAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
            autoRefreshTimer = null;
        }
        autoRefreshBtn.textContent = 'Auto Refresh';
        autoRefreshBtn.classList.remove('bg-green-700', 'text-white', 'border-green-600');
        autoRefreshBtn.classList.add('bg-surface', 'text-gray-400', 'hover:border-accent', 'hover:text-white');
    }

    autoRefreshBtn.addEventListener('click', () => {
        if (autoRefreshTimer) {
            stopAutoRefresh();
        } else {
            startAutoRefresh();
        }
    });

    refreshIntervalSelect.addEventListener('change', () => {
        if (autoRefreshTimer) {
            startAutoRefresh();
        }
    });

    // ----- Timezone session toggles -----
    document.querySelectorAll('.tz-toggle').forEach(btn => {
        let active = false;
        btn.addEventListener('click', () => {
            active = !active;
            const tz = btn.dataset.tz;
            if (active) {
                btn.style.backgroundColor = btn.dataset.activeBg;
                btn.style.borderColor = btn.dataset.activeBorder;
                btn.style.color = btn.dataset.activeText;
            } else {
                btn.style.backgroundColor = '';
                btn.style.borderColor = '';
                btn.style.color = '';
            }
            ChartManager.setTimezoneSession(tz, active);
        });
    });

    // ----- Resize handling -----
    window.addEventListener('resize', () => {
        ChartManager.resize();
    });
});

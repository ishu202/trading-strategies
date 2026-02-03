/**
 * Chart rendering module using TradingView Lightweight Charts.
 */

// ── Timezone session highlight primitive ──

class SessionHighlightRenderer {
    constructor(primitive) {
        this._primitive = primitive;
    }

    draw(target) {
        try {
            target.useBitmapCoordinateSpace(scope => {
                const { context, bitmapSize, horizontalPixelRatio } = scope;
                const prim = this._primitive;
                if (!prim._chart) return;

                const timeScale = prim._chart.timeScale();
                const visibleRange = timeScale.getVisibleRange();
                if (!visibleRange) return;

                const fromDate = new Date(visibleRange.from * 1000);
                const toDate = new Date(visibleRange.to * 1000);
                fromDate.setUTCDate(fromDate.getUTCDate() - 1);
                toDate.setUTCDate(toDate.getUTCDate() + 1);
                fromDate.setUTCHours(0, 0, 0, 0);

                for (const [, session] of Object.entries(prim._sessions)) {
                    if (!session.enabled) continue;

                    const d = new Date(fromDate);
                    while (d <= toDate) {
                        // Skip weekends
                        const dow = d.getUTCDay();
                        if (dow === 0 || dow === 6) {
                            d.setUTCDate(d.getUTCDate() + 1);
                            continue;
                        }

                        const t1 = Math.floor(Date.UTC(
                            d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(),
                            session.startHour, 0, 0
                        ) / 1000);
                        const t2 = Math.floor(Date.UTC(
                            d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(),
                            session.endHour, 0, 0
                        ) / 1000);

                        const x1 = timeScale.timeToCoordinate(t1);
                        const x2 = timeScale.timeToCoordinate(t2);

                        if (x1 !== null && x2 !== null) {
                            context.fillStyle = session.color;
                            context.fillRect(
                                Math.round(x1 * horizontalPixelRatio),
                                0,
                                Math.round((x2 - x1) * horizontalPixelRatio),
                                bitmapSize.height
                            );
                        }

                        d.setUTCDate(d.getUTCDate() + 1);
                    }
                }
            });
        } catch (e) {
            // Silently ignore render errors to avoid breaking the chart
        }
    }
}

class SessionHighlightPrimitive {
    constructor() {
        this._chart = null;
        this._series = null;
        this._requestUpdate = null;
        this._sessions = {
            asia:    { enabled: false, startHour: 0,  endHour: 9,  color: 'rgba(255, 200, 50, 0.08)' },
            london:  { enabled: false, startHour: 7,  endHour: 16, color: 'rgba(50, 150, 255, 0.08)' },
            eastern: { enabled: false, startHour: 13, endHour: 22, color: 'rgba(255, 100, 100, 0.08)' },
        };
        this._paneView = {
            zOrder() { return 'bottom'; },
            renderer: () => new SessionHighlightRenderer(this),
        };
    }

    attached({ chart, series, requestUpdate }) {
        this._chart = chart;
        this._series = series;
        this._requestUpdate = requestUpdate;
    }

    detached() {
        this._chart = null;
        this._series = null;
        this._requestUpdate = null;
    }

    paneViews() {
        return [this._paneView];
    }

    setSession(name, enabled) {
        if (this._sessions[name]) {
            this._sessions[name].enabled = enabled;
            if (this._requestUpdate) this._requestUpdate();
        }
    }

    getSession(name) {
        return this._sessions[name] ? this._sessions[name].enabled : false;
    }
}

// ── ChartManager ──

const ChartManager = (() => {
    let chart = null;
    let candleSeries = null;
    let overlaySeries = {};
    let rsiChart = null;
    let rsiSeries = null;
    let sessionPrimitive = null;

    // Persist toggle state across chart re-creates
    let sessionState = { asia: false, london: false, eastern: false };

    const CHART_BG = '#1a1a2e';
    const GRID_COLOR = 'rgba(255,255,255,0.04)';

    function createMainChart(container) {
        if (chart) {
            chart.remove();
            chart = null;
        }
        overlaySeries = {};

        chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: container.clientHeight,
            layout: {
                background: { type: 'solid', color: CHART_BG },
                textColor: '#9ca3af',
                fontSize: 12,
            },
            grid: {
                vertLines: { color: GRID_COLOR },
                horzLines: { color: GRID_COLOR },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#333',
            },
            timeScale: {
                borderColor: '#333',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        candleSeries = chart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderUpColor: '#22c55e',
            borderDownColor: '#ef4444',
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        // Attach timezone session highlight primitive
        try {
            sessionPrimitive = new SessionHighlightPrimitive();
            candleSeries.attachPrimitive(sessionPrimitive);
            // Restore persisted toggle state
            for (const [name, enabled] of Object.entries(sessionState)) {
                sessionPrimitive.setSession(name, enabled);
            }
        } catch (e) {
            console.warn('Failed to attach session highlight primitive:', e);
            sessionPrimitive = null;
        }

        return chart;
    }

    function setCandles(data) {
        if (!candleSeries) return;
        const formatted = data.map(c => ({
            time: toTimestamp(c.time),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));
        candleSeries.setData(formatted);
        chart.timeScale().fitContent();
    }

    function setSignals(signals) {
        if (!candleSeries) return;
        const markers = signals.map(s => ({
            time: toTimestamp(s.time),
            position: s.position,
            color: s.color,
            shape: s.shape,
            text: s.text,
        }));
        markers.sort((a, b) => a.time - b.time);
        candleSeries.setMarkers(markers);
    }

    function setOverlays(overlays) {
        // Remove old overlay series
        Object.values(overlaySeries).forEach(s => {
            try { chart.removeSeries(s); } catch (e) { /* ignore */ }
        });
        overlaySeries = {};

        if (!overlays) return;

        const colors = {
            bb_upper: 'rgba(100,149,237,0.5)',
            bb_middle: 'rgba(100,149,237,0.8)',
            bb_lower: 'rgba(100,149,237,0.5)',
        };

        for (const [name, data] of Object.entries(overlays)) {
            if (name === 'rsi') continue; // handled separately
            for (const [col, points] of Object.entries(data)) {
                const series = chart.addLineSeries({
                    color: colors[col] || 'rgba(255,255,255,0.3)',
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                });
                const formatted = points.map(p => ({
                    time: toTimestamp(p.time),
                    value: p.value,
                }));
                series.setData(formatted);
                overlaySeries[col] = series;
            }
        }
    }

    function setRSI(container, rsiData) {
        // Destroy previous RSI chart
        if (rsiChart) {
            rsiChart.remove();
            rsiChart = null;
            rsiSeries = null;
        }

        if (!rsiData || !rsiData.rsi || rsiData.rsi.length === 0) {
            container.style.display = 'none';
            return;
        }

        container.style.display = 'block';

        rsiChart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: 120,
            layout: {
                background: { type: 'solid', color: CHART_BG },
                textColor: '#9ca3af',
                fontSize: 11,
            },
            grid: {
                vertLines: { color: GRID_COLOR },
                horzLines: { color: GRID_COLOR },
            },
            rightPriceScale: {
                borderColor: '#333',
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            timeScale: {
                visible: false,
            },
        });

        rsiSeries = rsiChart.addLineSeries({
            color: '#a78bfa',
            lineWidth: 1.5,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const formatted = rsiData.rsi.map(p => ({
            time: toTimestamp(p.time),
            value: p.value,
        }));
        rsiSeries.setData(formatted);

        // Oversold/overbought lines
        const addLevel = (val, color) => {
            const line = rsiChart.addLineSeries({
                color: color,
                lineWidth: 1,
                lineStyle: 2, // dashed
                priceLineVisible: false,
                lastValueVisible: false,
            });
            if (formatted.length >= 2) {
                line.setData([
                    { time: formatted[0].time, value: val },
                    { time: formatted[formatted.length - 1].time, value: val },
                ]);
            }
        };
        addLevel(30, 'rgba(34,197,94,0.4)');
        addLevel(70, 'rgba(239,68,68,0.4)');

        // Sync time scales
        if (chart) {
            chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
                if (range && rsiChart) {
                    rsiChart.timeScale().setVisibleLogicalRange(range);
                }
            });
        }

        rsiChart.timeScale().fitContent();
    }

    function resize() {
        const container = document.getElementById('main-chart');
        if (chart && container) {
            chart.resize(container.clientWidth, container.clientHeight);
        }
        const rsiContainer = document.getElementById('rsi-chart');
        if (rsiChart && rsiContainer) {
            rsiChart.resize(rsiContainer.clientWidth, 120);
        }
    }

    function toTimestamp(timeStr) {
        // TradingView expects UTC timestamps in seconds
        return Math.floor(new Date(timeStr).getTime() / 1000);
    }

    function setTimezoneSession(name, enabled) {
        sessionState[name] = enabled;
        if (sessionPrimitive) {
            sessionPrimitive.setSession(name, enabled);
        }
    }

    return {
        createMainChart,
        setCandles,
        setSignals,
        setOverlays,
        setRSI,
        resize,
        setTimezoneSession,
    };
})();

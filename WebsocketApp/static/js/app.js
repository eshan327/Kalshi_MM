// Kalshi WebSocket Dashboard - JavaScript Client
class KalshiDashboard {
    constructor() {
        this.socket = null;
        this.marketData = {};
        this.connectionStatus = 'disconnected';
        this.subscribedMarkets = new Set();
        this.logs = [];
        this.priceChart = null;
        this.priceData = {}; // {market_id: [{timestamp, yes_price, no_price}]}
        this.selectedOrderbookMarket = null;
        this.selectedChartMarket = null;
        this.maxDataPoints = 500;
        this.init();
    }
    
    init() {
        this.connectSocket();
        this.bindEvents();
        // Seed status from server
        fetch('/api/status')
            .then(r => r.json())
            .then(s => {
                if (s && s.connection_status) {
                    this.updateConnectionStatus(s.connection_status);
                    this.addLog('info', `Server status: ${s.connection_status}`);
                    
                    // Restore subscribed markets from server
                    if (s.subscribed_markets && Array.isArray(s.subscribed_markets)) {
                        s.subscribed_markets.forEach(marketId => {
                            this.subscribedMarkets.add(marketId);
                        });
                    }
                } else {
                    this.updateConnectionStatus('connecting');
                }
            })
            .catch(() => this.updateConnectionStatus('connecting'));
        this.updateStats();
        this.updateLogsDisplay();
        this.updateSubscriptionsList();
        this.initChart();
    }
    
    connectSocket() {
        // Connect to Flask-SocketIO server
        this.socket = io();
        
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.addLog('success', 'Connected to server');
            this.updateConnectionStatus('connected');
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.addLog('warning', 'Disconnected from server');
            this.updateConnectionStatus('disconnected');
        });

        this.socket.on('connect_error', (error) => {
            this.addLog('error', `Socket connection error: ${error && error.message ? error.message : 'unknown'}`);
            this.updateConnectionStatus('error');
        });
        
        this.socket.on('status', (data) => {
            if (data.status) {
                this.updateConnectionStatus(data.status);
            }
        });
        
        this.socket.on('log_update', (data) => {
            this.addLog(data.level, data.message, data.details);
        });
        
        this.socket.on('raw_message', (data) => {
            this.addLog('info', 'WebSocket Message', {raw: data.message});
        });
        
        this.socket.on('orderbook_update', (data) => {
            const marketId = data.market_id;
            if (!this.marketData[marketId]) {
                this.marketData[marketId] = {
                    orderbook: {},
                    ticker: {},
                    trades: [],
                    yes_price: null,
                    no_price: null
                };
            }
            this.marketData[marketId].orderbook = data.orderbook_data;
            console.log('Orderbook update received for', marketId, data.orderbook_data);
            this.updateOrderbookDisplay();
            
            // If this is the selected orderbook market, make sure it's displayed
            if (this.selectedOrderbookMarket === marketId) {
                this.updateOrderbookDisplay();
            }
        });
        
        this.socket.on('ticker_update', (data) => {
            const marketId = data.market_id;
            if (!this.marketData[marketId]) {
                this.marketData[marketId] = {
                    orderbook: {},
                    ticker: {},
                    trades: [],
                    yes_price: null,
                    no_price: null
                };
            }
            this.marketData[marketId].ticker = data.ticker_data;
            // Extract prices from ticker
            if (data.ticker_data.yes_bid && data.ticker_data.yes_ask) {
                this.marketData[marketId].yes_price = (parseFloat(data.ticker_data.yes_bid) + parseFloat(data.ticker_data.yes_ask)) / 2;
                this.marketData[marketId].no_price = 100 - this.marketData[marketId].yes_price;
                this.updateChartData(marketId, this.marketData[marketId].yes_price, this.marketData[marketId].no_price);
            }
        });
        
        this.socket.on('trade_update', (data) => {
            const marketId = data.market_id;
            if (!this.marketData[marketId]) {
                this.marketData[marketId] = {
                    orderbook: {},
                    ticker: {},
                    trades: [],
                    yes_price: null,
                    no_price: null
                };
            }
            this.marketData[marketId].trades.unshift(data.trade_data);
            if (this.marketData[marketId].trades.length > 50) {
                this.marketData[marketId].trades = this.marketData[marketId].trades.slice(0, 50);
            }
        });
        
        this.socket.on('price_update', (data) => {
            console.log('Price update received for', data.market_id, 'yes:', data.yes_price, 'no:', data.no_price);
            this.updateChartData(data.market_id, data.yes_price, data.no_price);
            
            // If this is the selected chart market, update it
            if (this.selectedChartMarket === data.market_id) {
                this.updateChartMarket(data.market_id);
            }
        });
        
        this.socket.on('initial_price_data', (data) => {
            console.log('Initial price data received:', data);
            if (data.price_data) {
                // Merge initial price data
                Object.entries(data.price_data).forEach(([marketId, priceArray]) => {
                    if (Array.isArray(priceArray)) {
                        this.priceData[marketId] = priceArray.map(p => ({
                            timestamp: p.timestamp,
                            label: new Date(p.timestamp).toLocaleTimeString(),
                            yes_price: p.yes_price,
                            no_price: p.no_price
                        }));
                    }
                });
                // Update chart if a market is selected
                if (this.selectedChartMarket) {
                    this.updateChartMarket(this.selectedChartMarket);
                }
            }
        });
        
        this.socket.on('subscription_result', (data) => {
            if (data.success) {
                this.subscribedMarkets.add(data.market_id);
                this.addLog('success', `Subscribed to market: ${data.market_id}`);
            } else {
                this.addLog('error', `Failed to subscribe to market: ${data.market_id}`);
            }
            this.updateStats();
            this.updateMarketSelects();
            this.updateSubscriptionsList();
            if (this.updateMarketMakerSelect) {
                this.updateMarketMakerSelect();
            }
        });
        
        this.socket.on('unsubscription_result', (data) => {
            this.subscribedMarkets.delete(data.market_id);
            this.addLog('success', `Unsubscribed from market: ${data.market_id}`);
            this.updateStats();
            this.updateMarketSelects();
            this.updateSubscriptionsList();
            if (this.updateMarketMakerSelect) {
                this.updateMarketMakerSelect();
            }
        });
    }
    
    bindEvents() {
        // Subscribe button
        const subscribeBtn = document.getElementById('subscribe-btn');
        const marketIdInput = document.getElementById('market-id');
        
        subscribeBtn.addEventListener('click', () => {
            const marketId = marketIdInput.value.trim();
            if (marketId) {
                this.subscribeToMarket(marketId);
                marketIdInput.value = '';
            }
        });
        
        // Enter key on input
        marketIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                subscribeBtn.click();
            }
        });
        
        marketIdInput.addEventListener('input', () => {
            const hasInput = marketIdInput.value.trim().length > 0;
            subscribeBtn.disabled = this.connectionStatus !== 'connected' || !hasInput;
        });

        // Control buttons
        document.getElementById('force-reconnect').addEventListener('click', () => {
            this.forceReconnect();
        });
        
        document.getElementById('clear-logs').addEventListener('click', () => {
            this.clearLogs();
        });
        
        // Orderbook market select
        document.getElementById('orderbook-market-select').addEventListener('change', (e) => {
            this.selectedOrderbookMarket = e.target.value;
            console.log('Orderbook market selected:', this.selectedOrderbookMarket);
            console.log('Market data:', this.marketData[this.selectedOrderbookMarket]);
            this.updateOrderbookDisplay();
        });
        
        // Chart controls
        document.getElementById('chart-market-select').addEventListener('change', (e) => {
            this.selectedChartMarket = e.target.value;
            console.log('Chart market selected:', this.selectedChartMarket);
            console.log('Price data:', this.priceData[this.selectedChartMarket]);
            this.updateChartMarket(e.target.value);
        });
        
        document.getElementById('clear-chart').addEventListener('click', () => {
            this.clearChart();
        });
        
        // Strategy bankroll inputs
        this.setupStrategyInputs();
        
        // Market Maker section
        this.setupMarketMaker();
    }
    
    subscribeToMarket(marketId) {
        this.socket.emit('subscribe_market', { market_id: marketId });
    }
    
    unsubscribeFromMarket(marketId) {
        this.socket.emit('unsubscribe_market', { market_id: marketId });
    }
    
    forceReconnect() {
        this.addLog('info', 'Force reconnecting...');
        fetch('/api/reconnect', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.addLog('success', 'Reconnection initiated');
                }
            })
            .catch(error => {
                this.addLog('error', 'Failed to initiate reconnection', error);
            });
    }
    
    clearLogs() {
        this.logs = [];
        this.updateLogsDisplay();
        fetch('/api/clear-logs', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.addLog('info', 'Logs cleared');
                }
            });
    }
    
    addLog(level, message, details = null) {
        const logEntry = {
            id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
            timestamp: Date.now(),
            level: level,
            message: message,
            details: details
        };
        
        this.logs.push(logEntry);
        
        // Keep last 100 logs
        if (this.logs.length > 100) {
            this.logs = this.logs.slice(-100);
        }
        
        this.updateLogsDisplay();
        
        // Also log to console
        const emojiMap = {
            'error': '🚨',
            'warning': '⚠️',
            'success': '✅',
            'info': 'ℹ️'
        };
        
        console.log(`${emojiMap[level] || '📝'} ${message}`, details || '');
    }
    
    updateLogsDisplay() {
        const logsContent = document.getElementById('logs-content');
        const logsPlaceholder = document.getElementById('logs-placeholder');
        
        if (this.logs.length === 0) {
            logsContent.style.display = 'none';
            logsPlaceholder.style.display = 'block';
            return;
        }
        
        logsPlaceholder.style.display = 'none';
        logsContent.style.display = 'block';
        
        logsContent.innerHTML = this.logs.map(log => `
            <div class="log-entry ${log.level}">
                <div class="log-header">
                    <div class="log-message">
                        <span class="log-icon">${this.getLogIcon(log.level)}</span>
                        <span>${log.message}</span>
                    </div>
                    <span class="log-timestamp">${new Date(log.timestamp).toLocaleTimeString()}</span>
                </div>
                ${log.details ? `
                    <div class="log-details">
                        <pre>${JSON.stringify(log.details, null, 2)}</pre>
                    </div>
                ` : ''}
            </div>
        `).join('');
        
        // Auto-scroll to bottom
        const terminal = document.getElementById('logs-terminal');
        terminal.scrollTop = terminal.scrollHeight;
    }
    
    getLogIcon(level) {
        const iconMap = {
            'error': '🚨',
            'warning': '⚠️',
            'success': '✅',
            'info': 'ℹ️'
        };
        return iconMap[level] || '📝';
    }
    
    updateConnectionStatus(status) {
        this.connectionStatus = status;
        const statusCard = document.getElementById('connection-status');
        const statusTitle = document.getElementById('status-title');
        const statusMessage = document.getElementById('status-message');
        const connectionStatusText = document.getElementById('connection-status-text');
        
        statusCard.className = 'status-card';
        statusCard.classList.add(status);
        
        const statusConfig = {
            'connected': {
                title: '✅ Connected to Kalshi',
                message: 'Live market data streaming',
                text: 'CONNECTED'
            },
            'connecting': {
                title: '🔄 Connecting...',
                message: 'Establishing WebSocket connection...',
                text: 'CONNECTING'
            },
            'disconnected': {
                title: '❌ Disconnected',
                message: 'Attempting to reconnect...',
                text: 'DISCONNECTED'
            },
            'error': {
                title: '❌ Connection Error',
                message: 'Attempting to reconnect...',
                text: 'ERROR'
            }
        };
        
        const config = statusConfig[status] || statusConfig['disconnected'];
        statusTitle.textContent = config.title;
        statusMessage.textContent = config.message;
        connectionStatusText.textContent = config.text;
        connectionStatusText.className = status === 'connected' ? 'connected' : 'disconnected';
        
        // Update subscribe button state
        const subscribeBtn = document.getElementById('subscribe-btn');
        const marketIdInput = document.getElementById('market-id');
        const hasInput = marketIdInput.value.trim().length > 0;
        subscribeBtn.disabled = status !== 'connected' || !hasInput;
    }
    
    updateStats() {
        document.getElementById('subscribed-count').textContent = this.subscribedMarkets.size;
        document.getElementById('active-markets-count').textContent = Object.keys(this.marketData).length;
    }
    
    updateSubscriptionsList() {
        const list = document.getElementById('subscriptions-list');
        
        if (this.subscribedMarkets.size === 0) {
            list.innerHTML = '<div class="no-subscriptions"><p>No active subscriptions</p></div>';
            return;
        }
        
        list.innerHTML = Array.from(this.subscribedMarkets).map(marketId => `
            <div class="subscription-item" data-market-id="${marketId}">
                <span class="subscription-name">${marketId}</span>
                <button class="subscription-remove" data-market-id="${marketId}" title="Unsubscribe">
                    ×
                </button>
            </div>
        `).join('');
        
        // Add click handlers for remove buttons
        list.querySelectorAll('.subscription-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const marketId = btn.getAttribute('data-market-id');
                if (marketId) {
                    this.unsubscribeFromMarket(marketId);
                }
            });
        });
    }
    
    updateMarketSelects() {
        const orderbookSelect = document.getElementById('orderbook-market-select');
        const chartSelect = document.getElementById('chart-market-select');
        
        const currentOrderbookValue = orderbookSelect.value;
        const currentChartValue = chartSelect.value;
        
        // Clear and rebuild options
        orderbookSelect.innerHTML = '<option value="">Select Market</option>';
        chartSelect.innerHTML = '<option value="">Select Market</option>';
        
        this.subscribedMarkets.forEach(marketId => {
            const option1 = document.createElement('option');
            option1.value = marketId;
            option1.textContent = marketId;
            orderbookSelect.appendChild(option1);
            
            const option2 = document.createElement('option');
            option2.value = marketId;
            option2.textContent = marketId;
            chartSelect.appendChild(option2);
        });
        
        // Restore selections
        if (currentOrderbookValue && this.subscribedMarkets.has(currentOrderbookValue)) {
            orderbookSelect.value = currentOrderbookValue;
        }
        if (currentChartValue && this.subscribedMarkets.has(currentChartValue)) {
            chartSelect.value = currentChartValue;
        }
    }
    
    updateOrderbookDisplay() {
        const display = document.getElementById('orderbook-display');
        
        if (!this.selectedOrderbookMarket) {
            display.innerHTML = '<div class="no-market-selected"><p>Select a market from the dropdown above to view the orderbook</p></div>';
            return;
        }
        
        if (!this.marketData[this.selectedOrderbookMarket]) {
            display.innerHTML = '<div class="no-market-selected"><p>No data available for this market yet. Waiting for orderbook data...</p></div>';
            return;
        }
        
        const market = this.marketData[this.selectedOrderbookMarket];
        const orderbook = market.orderbook || {};
        
        console.log('Updating orderbook display for', this.selectedOrderbookMarket, 'orderbook:', orderbook);
        
        const yesBids = orderbook.yes_bids || [];
        const yesAsks = orderbook.yes_asks || [];
        
        // Helper to format entry (handles both {price, size} objects and [price, size] arrays)
        const formatEntry = (entry) => {
            if (typeof entry === 'object' && entry !== null) {
                if ('price' in entry && 'size' in entry) {
                    return { price: entry.price, size: entry.size };
                } else if (Array.isArray(entry) && entry.length >= 2) {
                    return { price: entry[0], size: entry[1] };
                }
            }
            return { price: entry, size: 0 };
        };
        
        display.innerHTML = `
            <div class="orderbook-grid">
                <div class="orderbook-column">
                    <h4>YES Bids</h4>
                    <div class="orderbook-list bids">
                        ${yesBids.length === 0 ? '<div class="no-data">No bids</div>' : 
                            yesBids.map(bid => {
                                const entry = formatEntry(bid);
                                return `
                                <div class="orderbook-item">
                                    <span class="orderbook-price">${this.formatPrice(entry.price)}</span>
                                    <span class="orderbook-size">${this.formatSize(entry.size)}</span>
                                </div>
                            `;
                            }).join('')}
                    </div>
                </div>
                <div class="orderbook-column">
                    <h4>YES Asks</h4>
                    <div class="orderbook-list asks">
                        ${yesAsks.length === 0 ? '<div class="no-data">No asks</div>' : 
                            yesAsks.map(ask => {
                                const entry = formatEntry(ask);
                                return `
                                <div class="orderbook-item">
                                    <span class="orderbook-price">${this.formatPrice(entry.price)}</span>
                                    <span class="orderbook-size">${this.formatSize(entry.size)}</span>
                                </div>
                            `;
                            }).join('')}
                    </div>
                </div>
            </div>
        `;
    }
    
    formatPrice(price) {
        if (typeof price === 'object' && price !== null) {
            price = price.price || price;
        }
        return parseFloat(price || 0).toFixed(2);
    }
    
    formatSize(size) {
        return parseFloat(size || 0).toLocaleString();
    }
    
    initChart() {
        const ctx = document.getElementById('priceChart').getContext('2d');
        
        this.priceChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'YES Price',
                        data: [],
                        borderColor: '#00ff00',
                        backgroundColor: 'rgba(0, 255, 0, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 4,  // Always show points
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#00ff00',
                        pointBorderColor: '#00ff00'
                    },
                    {
                        label: 'NO Price',
                        data: [],
                        borderColor: '#ff0000',
                        backgroundColor: 'rgba(255, 0, 0, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 4,  // Always show points
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#ff0000',
                        pointBorderColor: '#ff0000'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, position: 'top', labels: { color: '#cccccc' } }
                },
                scales: {
                    x: {
                        display: true,
                        grid: { color: '#333333' },
                        ticks: { color: '#888888' },
                        min: undefined,  // Let Chart.js auto-calculate
                        max: undefined
                    },
                    y: {
                        display: true,
                        grid: { color: '#333333' },
                        ticks: { 
                            color: '#888888',
                            callback: function(value) {
                                return value.toFixed(2);
                            }
                        },
                        min: 0,
                        max: 100
                    }
                }
            }
        });
    }
    
    updateChartData(marketId, yesPrice, noPrice) {
        if (!this.priceData[marketId]) {
            this.priceData[marketId] = [];
        }
        
        const now = new Date();
        const timeLabel = now.toLocaleTimeString();
        
        this.priceData[marketId].push({
            timestamp: now.getTime(),
            label: timeLabel,
            yes_price: yesPrice,
            no_price: noPrice
        });
        
        // Keep only the last maxDataPoints
        if (this.priceData[marketId].length > this.maxDataPoints) {
            this.priceData[marketId] = this.priceData[marketId].slice(-this.maxDataPoints);
        }
        
        // Update chart if this is the selected market
        if (this.selectedChartMarket === marketId && this.priceChart) {
            this.updateChartMarket(marketId);
        }
    }
    
    updateChartMarket(marketId) {
        if (!marketId || !this.priceData[marketId] || this.priceData[marketId].length === 0) {
            if (this.priceChart) {
                this.priceChart.data.labels = [];
                this.priceChart.data.datasets[0].data = [];
                this.priceChart.data.datasets[1].data = [];
                this.priceChart.update();
            }
            return;
        }
        
        const data = this.priceData[marketId];
        // Filter out null values but keep the data points
        const validData = data.filter(d => d.yes_price !== null && d.yes_price !== undefined);
        
        if (validData.length === 0) {
            if (this.priceChart) {
                this.priceChart.data.labels = [];
                this.priceChart.data.datasets[0].data = [];
                this.priceChart.data.datasets[1].data = [];
                this.priceChart.update();
            }
            return;
        }
        
        const labels = validData.map(d => d.label || new Date(d.timestamp).toLocaleTimeString());
        const yesPrices = validData.map(d => d.yes_price);
        const noPrices = validData.map(d => d.no_price || (100 - d.yes_price)); // Calculate NO price if missing
        
        if (this.priceChart) {
            this.priceChart.data.labels = labels;
            this.priceChart.data.datasets[0].data = yesPrices;
            this.priceChart.data.datasets[1].data = noPrices;
            
            // For single data point, ensure the chart displays properly
            if (validData.length === 1) {
                // Set explicit y-axis range for single point to ensure visibility
                const singlePrice = yesPrices[0];
                this.priceChart.options.scales.y.min = Math.max(0, singlePrice - 10);
                this.priceChart.options.scales.y.max = Math.min(100, singlePrice + 10);
                // Ensure x-axis shows the single point
                this.priceChart.options.scales.x.min = 0;
                this.priceChart.options.scales.x.max = 1;
            } else {
                // Reset to auto for multiple points
                this.priceChart.options.scales.y.min = undefined;
                this.priceChart.options.scales.y.max = undefined;
                this.priceChart.options.scales.x.min = undefined;
                this.priceChart.options.scales.x.max = undefined;
            }
            
            // Always use animation for updates to ensure chart renders
            this.priceChart.update('default');
        }
    }
    
    clearChart() {
        if (this.priceChart) {
            this.priceChart.data.labels = [];
            this.priceChart.data.datasets[0].data = [];
            this.priceChart.data.datasets[1].data = [];
            this.priceChart.update();
        }
        
        // Clear price data for selected market
        if (this.selectedChartMarket) {
            this.priceData[this.selectedChartMarket] = [];
        }
    }
    
    setupStrategyInputs() {
        // Market Making strategy bankroll input
        const mmBankrollInput = document.getElementById('mm-bankroll');
        const mmConfirmBtn = document.getElementById('mm-confirm-btn');
        const mmStatus = document.getElementById('mm-status');
        
        if (!mmBankrollInput || !mmConfirmBtn) return;
        
        // Enable/disable confirm button based on input
        mmBankrollInput.addEventListener('input', () => {
            const value = parseFloat(mmBankrollInput.value);
            mmConfirmBtn.disabled = !value || value <= 0 || isNaN(value);
        });
        
        // Handle Enter key press
        mmBankrollInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !mmConfirmBtn.disabled) {
                mmConfirmBtn.click();
            }
        });
        
        // Handle confirm button click
        mmConfirmBtn.addEventListener('click', () => {
            const bankroll = parseFloat(mmBankrollInput.value);
            if (bankroll && bankroll > 0) {
                this.executeMarketMakingStrategy(bankroll, mmStatus);
            }
        });
    }
    
    executeMarketMakingStrategy(bankroll, statusElement) {
        // Update status
        statusElement.textContent = `Executing Market Making strategy with bankroll: $${bankroll.toFixed(2)}...`;
        statusElement.className = 'strategy-status info';
        
        // Log the strategy execution
        this.addLog('info', `Market Making strategy initiated with bankroll: $${bankroll.toFixed(2)}`);
        
        // TODO: Implement actual strategy execution
        // This would typically make an API call to the backend to start the strategy
        // For now, we'll just show a success message after a short delay
        
        setTimeout(() => {
            statusElement.textContent = `Strategy active with bankroll: $${bankroll.toFixed(2)}`;
            statusElement.className = 'strategy-status success';
            this.addLog('success', `Market Making strategy started with bankroll: $${bankroll.toFixed(2)}`);
            
            // In a real implementation, you would:
            // 1. Send a request to the backend to start the strategy
            // 2. The backend would initialize the BasicMM class with the bankroll
            // 3. The backend would start the strategy execution
            // 4. Real-time updates would be sent via WebSocket
        }, 1000);
    }
    
    setupMarketMaker() {
        // Find Opportunities Section
        const findBtn = document.getElementById('find-opportunities-btn');
        const findNflBtn = document.getElementById('find-nfl-opportunities-btn');
        const opportunitiesStatusDiv = document.getElementById('opportunities-status');
        const opportunitiesListDiv = document.getElementById('opportunities-list');
        
        // Market Maker Controls Section
        const marketSelect = document.getElementById('mm-market-select');
        const mmBankrollInput = document.getElementById('mm-bankroll-input');
        const mmStopLossInput = document.getElementById('mm-stop-loss-input');
        const startMMBtn = document.getElementById('start-market-maker-btn');
        const mmStatusDiv = document.getElementById('market-maker-status');
        
        if (!findBtn || !findNflBtn || !marketSelect || !mmBankrollInput || !mmStopLossInput || !startMMBtn) return;
        
        // Update market select when subscribed markets change
        this.updateMarketMakerSelect = () => {
            const currentValue = marketSelect.value;
            marketSelect.innerHTML = '<option value="">Select a subscribed market</option>';
            
            const sortedMarkets = Array.from(this.subscribedMarkets).sort();
            sortedMarkets.forEach(marketId => {
                const option = document.createElement('option');
                option.value = marketId;
                option.textContent = marketId;
                marketSelect.appendChild(option);
            });
            
            // Restore selection if still valid
            if (currentValue && this.subscribedMarkets.has(currentValue)) {
                marketSelect.value = currentValue;
            }
            
            // Update button state
            this.updateStartMMButtonState();
        };
        
        // Enable/disable start market maker button (needs market and bankroll)
        this.updateStartMMButtonState = () => {
            const hasMarket = marketSelect.value && marketSelect.value !== '';
            const hasBankroll = mmBankrollInput.value && parseFloat(mmBankrollInput.value) > 0;
            startMMBtn.disabled = !hasMarket || !hasBankroll;
        };
        
        // Find Opportunities button handler (standalone, no requirements)
        findBtn.addEventListener('click', () => {
            this.findMarketOpportunities(opportunitiesStatusDiv, opportunitiesListDiv, false);
        });
        
        findNflBtn.addEventListener('click', () => {
            this.findMarketOpportunities(opportunitiesStatusDiv, opportunitiesListDiv, true);
        });
        
        // Market Maker Controls button handlers
        marketSelect.addEventListener('change', () => {
            this.updateStartMMButtonState();
        });
        
        mmBankrollInput.addEventListener('input', () => {
            this.updateStartMMButtonState();
        });
        
        startMMBtn.addEventListener('click', () => {
            const marketId = marketSelect.value;
            const bankroll = parseFloat(mmBankrollInput.value);
            const stopLoss = parseFloat(mmStopLossInput.value) || 0;
            if (marketId && bankroll > 0) {
                this.startMarketMaking(marketId, bankroll, stopLoss, mmStatusDiv);
            }
        });
        
        // Initial updates
        this.updateMarketMakerSelect();
    }
    
    findMarketOpportunities(statusDiv, listDiv, filterNfl = false) {
        // Show loading status with spinner
        const searchType = filterNfl ? 'NFL' : 'market';
        statusDiv.innerHTML = `<div class="loading-container"><div class="spinner"></div><span>Finding ${searchType} opportunities from ALL markets on Kalshi... This may take several minutes. Please wait...</span></div>`;
        statusDiv.className = 'opportunities-status info';
        listDiv.style.display = 'none';
        
        // Disable buttons during loading
        const findBtn = document.getElementById('find-opportunities-btn');
        const findNflBtn = document.getElementById('find-nfl-opportunities-btn');
        const originalBtnText = findBtn.textContent;
        const originalNflBtnText = findNflBtn.textContent;
        findBtn.disabled = true;
        findNflBtn.disabled = true;
        findBtn.textContent = 'Searching...';
        findNflBtn.textContent = 'Searching...';
        
        // Log the action
        const logMessage = filterNfl 
            ? 'Finding NFL market opportunities from ALL markets on Kalshi (this may take several minutes)...'
            : 'Finding market opportunities from ALL markets on Kalshi (this may take several minutes)...';
        this.addLog('info', logMessage);
        
        // Call backend API with filter_nfl parameter
        fetch('/api/find-opportunities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filter_nfl: filterNfl
            })
        })
        .then(response => {
            // Check if response is ok
            if (!response.ok) {
                // Try to parse error message
                return response.json().then(errData => {
                    throw new Error(errData.error || `HTTP ${response.status}: ${response.statusText}`);
                }).catch(() => {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                });
            }
            return response.json();
        })
        .then(data => {
            // Re-enable buttons
            findBtn.disabled = false;
            findNflBtn.disabled = false;
            findBtn.textContent = originalBtnText;
            findNflBtn.textContent = originalNflBtnText;
            
            if (data.success) {
                const count = data.opportunities ? data.opportunities.length : 0;
                const marketType = filterNfl ? 'NFL' : 'market';
                statusDiv.textContent = `Found ${count} ${marketType} opportunities`;
                statusDiv.className = 'opportunities-status success';
                this.displayOpportunities(data.opportunities || [], listDiv);
                this.addLog('success', `Found ${count} ${marketType} opportunities from all markets`);
            } else {
                const errorMsg = data.error || 'Failed to find opportunities';
                statusDiv.textContent = `Error: ${errorMsg}`;
                statusDiv.className = 'opportunities-status error';
                this.addLog('error', `Failed to find opportunities: ${errorMsg}`);
            }
        })
        .catch(error => {
            // Re-enable buttons on error
            findBtn.disabled = false;
            findNflBtn.disabled = false;
            findBtn.textContent = originalBtnText;
            findNflBtn.textContent = originalNflBtnText;
            
            const errorMsg = error.message || 'Network error or server timeout';
            statusDiv.textContent = `Error: ${errorMsg}`;
            statusDiv.className = 'opportunities-status error';
            this.addLog('error', `Error finding opportunities: ${errorMsg}`);
            console.error('Find opportunities error:', error);
        });
    }
    
    startMarketMaking(marketId, bankroll, stopLoss, statusDiv) {
        // Show confirmation dialog
        const confirmed = confirm(
            `Are you sure you want to start market making?\n\n` +
            `Market: ${marketId}\n` +
            `Bankroll: $${bankroll.toFixed(2)}\n` +
            `Stop Loss: ${stopLoss} cents\n\n` +
            `This will place real orders using actual money.`
        );
        
        if (!confirmed) {
            statusDiv.textContent = 'Market making cancelled by user';
            statusDiv.className = 'opportunities-status info';
            this.addLog('info', 'Market making cancelled by user');
            return;
        }
        
        // Show loading status
        statusDiv.textContent = `Starting market making for ${marketId} with bankroll: $${bankroll.toFixed(2)} and stop loss: ${stopLoss} cents...`;
        statusDiv.className = 'opportunities-status info';
        
        this.addLog('info', `Starting market making for ${marketId} with bankroll: $${bankroll.toFixed(2)} and stop loss: ${stopLoss} cents`);
        
        // Call backend API to start market making
        fetch('/api/start-market-making', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                market_id: marketId,
                bankroll: bankroll,
                stop_loss: stopLoss
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                statusDiv.textContent = `Market making started for ${marketId} with bankroll: $${bankroll.toFixed(2)}`;
                statusDiv.className = 'opportunities-status success';
                this.addLog('success', `Market making started for ${marketId}: ${data.message || 'Orders placed successfully'}`);
                
                if (data.details) {
                    this.addLog('info', `Details: ${JSON.stringify(data.details)}`);
                }
            } else {
                statusDiv.textContent = `Error: ${data.error || 'Failed to start market making'}`;
                statusDiv.className = 'opportunities-status error';
                this.addLog('error', `Failed to start market making: ${data.error || 'Unknown error'}`);
            }
        })
        .catch(error => {
            statusDiv.textContent = `Error: ${error.message}`;
            statusDiv.className = 'opportunities-status error';
            this.addLog('error', `Error starting market making: ${error.message}`);
        });
    }
    
    displayOpportunities(opportunities, listDiv) {
        const contentDiv = document.getElementById('opportunities-content');
        if (!contentDiv) return;
        
        if (opportunities.length === 0) {
            contentDiv.innerHTML = '<div class="no-data">No opportunities found matching the criteria.</div>';
            listDiv.style.display = 'block';
            return;
        }
        
        contentDiv.innerHTML = opportunities.map((opp, index) => {
            const ticker = opp.ticker || opp.market_id || 'Unknown';
            const spread = opp.spread !== undefined ? (opp.spread * 100).toFixed(2) + '¢' : 'N/A';
            const volume = opp.volume ? opp.volume.toLocaleString() : 'N/A';
            const yesBid = opp.yes_bid !== undefined ? (opp.yes_bid > 1 ? opp.yes_bid.toFixed(2) + '¢' : (opp.yes_bid * 100).toFixed(2) + '¢') : 'N/A';
            const yesAsk = opp.yes_ask !== undefined ? (opp.yes_ask > 1 ? opp.yes_ask.toFixed(2) + '¢' : (opp.yes_ask * 100).toFixed(2) + '¢') : 'N/A';
            const title = opp.title || opp.question || 'No title available';
            
            return `
                <div class="opportunity-item">
                    <div class="opportunity-header">
                        <span class="opportunity-ticker">${ticker}</span>
                        <span class="opportunity-spread">Spread: ${spread}</span>
                    </div>
                    <div class="opportunity-title" style="color: #888; margin-bottom: 10px; font-size: 13px;">${title}</div>
                    <div class="opportunity-details">
                        <div class="opportunity-detail-item">
                            <span class="opportunity-detail-label">Volume</span>
                            <span class="opportunity-detail-value">${volume}</span>
                        </div>
                        <div class="opportunity-detail-item">
                            <span class="opportunity-detail-label">YES Bid</span>
                            <span class="opportunity-detail-value">${yesBid}</span>
                        </div>
                        <div class="opportunity-detail-item">
                            <span class="opportunity-detail-label">YES Ask</span>
                            <span class="opportunity-detail-value">${yesAsk}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        listDiv.style.display = 'block';
    }
}

// Initialize dashboard when page loads
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new KalshiDashboard();
});

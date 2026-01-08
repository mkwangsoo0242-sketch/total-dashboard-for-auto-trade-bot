// 🏆 바이비트 실거래 봇 - 프로 대시보드 JavaScript
let chart = null;
let candleSeries = null;
let currentTimeframe = '15m';
let updateIntervals = {};
let isInitialized = false;

// 초기화
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 대시보드 초기화...');
    init();
});

function init() {
    if (isInitialized) return;
    isInitialized = true;
    
    displaySampleData();
    setupButtons();
    loadData();
    loadSettings();
    startAutoUpdate();
}

function setupButtons() {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    if (startBtn) startBtn.onclick = startBot;
    if (stopBtn) stopBtn.onclick = stopBot;
}

// 차트 초기화
function initChart() {
    const container = document.getElementById('chartContainer');
    if (!container) {
        /* chartContainer 없음 */
        return;
    }
    
    if (typeof LightweightCharts === 'undefined') {
        /* LightweightCharts 라이브러리 없음 */
        container.innerHTML = '<div style="padding:50px;text-align:center;color:#da3633;">차트 라이브러리 로드 실패</div>';
        return;
    }
    
    try {
        console.log('📊 LightweightCharts:', typeof LightweightCharts);
        
        // 기존 차트 제거
        if (chart) {
            chart.remove();
            chart = null;
            candleSeries = null;
        }
        
        container.innerHTML = '';
        
        const chartOptions = {
            layout: { 
                backgroundColor: '#0d1117',
                textColor: '#c9d1d9' 
            },
            grid: { 
                vertLines: { color: '#30363d' }, 
                horzLines: { color: '#30363d' } 
            },
            width: container.clientWidth || 800,
            height: 450,
            timeScale: { 
                timeVisible: true, 
                secondsVisible: false,
                borderColor: '#30363d',
                rightOffset: 5,
                barSpacing: 10
            }
        };

        const newChart = LightweightCharts.createChart(container, chartOptions);
        console.log('✅ Chart created:', newChart);
        
        // v3/v4 호환성을 위해 메서드 확인
        let series = null;
        if (typeof newChart.addCandlestickSeries === 'function') {
            series = newChart.addCandlestickSeries({
                upColor: '#238636', 
                downColor: '#da3633',
                borderUpColor: '#238636', 
                borderDownColor: '#da3633',
                wickUpColor: '#238636', 
                wickDownColor: '#da3633'
            });
        } else {
            console.error('❌ addCandlestickSeries method not found. Available methods:', Object.keys(newChart));
            throw new Error('addCandlestickSeries not found');
        }
        
        chart = newChart;
        candleSeries = series;
        
        // 실시간 Bybit 데이터로 차트 표시
        loadRealTimeChart(currentTimeframe);
        
        // 10초마다 자동 업데이트
        if (updateIntervals.chart) clearInterval(updateIntervals.chart);
        updateIntervals.chart = setInterval(function() {
            loadRealTimeChart(currentTimeframe);
        }, 10000);
        
        // 리사이즈 핸들러
        window.addEventListener('resize', function() {
            if (chart && container) {
                chart.resize(container.clientWidth, 450);
            }
        });
        
        console.log('✅ 차트 초기화 완료');
    } catch (e) { 
        /* 차트 오류: */ 
        container.innerHTML = '<div style="padding:50px;text-align:center;color:#da3633;">차트 초기화 실패: ' + e.message + '</div>';
    }
}

function generateSampleData(timeframe) {
    const data = [];
    const now = Math.floor(Date.now() / 1000);
    let price = 94000 + Math.random() * 2000;
    
    const intervals = { 
        '1m': 60, 
        '5m': 300, 
        '15m': 900, 
        '1h': 3600, 
        '4h': 14400, 
        '1d': 86400 
    };
    const interval = intervals[timeframe] || 900;
    const count = timeframe === '1d' ? 60 : 100;
    
    for (let i = count; i >= 0; i--) {
        const time = now - i * interval;
        const open = price;
        const volatility = timeframe === '1d' ? 1500 : (timeframe === '4h' ? 800 : 300);
        const change = (Math.random() - 0.5) * volatility;
        const close = open + change;
        const high = Math.max(open, close) + Math.random() * volatility * 0.3;
        const low = Math.min(open, close) - Math.random() * volatility * 0.3;
        
        data.push({ 
            time: time, 
            open: parseFloat(open.toFixed(2)), 
            high: parseFloat(high.toFixed(2)), 
            low: parseFloat(low.toFixed(2)), 
            close: parseFloat(close.toFixed(2)) 
        });
        price = close;
    }
    return data;
}


function changeTimeframe(tf, btn) {
    currentTimeframe = tf;
    document.querySelectorAll('.chart-controls button').forEach(function(b) {
        if (b.textContent.indexOf('새로고침') === -1) {
            b.classList.remove('active');
        }
    });
    if (btn) btn.classList.add('active');
    
    loadRealTimeChart(tf);
    showAlert('타임프레임: ' + tf, 'info');
}

function refreshChart() {
    loadRealTimeChart(currentTimeframe);
    showAlert('차트 새로고침 완료', 'success');
}

// 실시간 Bybit 차트 데이터 로드
function loadRealTimeChart(timeframe) {
    if (!candleSeries) return;
    
    // Bybit Public API (인증 불필요)
    var intervalMap = {
        '1m': '1', '5m': '5', '15m': '15', 
        '1h': '60', '4h': '240', '1d': 'D'
    };
    var interval = intervalMap[timeframe] || '15';
    var symbol = 'BTCUSDT';
    
    var url = 'https://api.bybit.com/v5/market/kline?category=linear&symbol=' + symbol + '&interval=' + interval + '&limit=200';
    
    fetch(url)
        .then(function(res) { return res.json(); })
        .then(function(result) {
            if (result.retCode === 0 && result.result && result.result.list) {
                var klines = result.result.list;
                var data = [];
                
                // 한국 시간대 오프셋 (UTC+9)
                var koreaOffset = 9 * 60 * 60;
                
                // Bybit 데이터는 최신순이므로 역순으로 변환
                for (var i = klines.length - 1; i >= 0; i--) {
                    var k = klines[i];
                    // UTC timestamp를 한국 시간으로 변환
                    var utcTime = parseInt(k[0]) / 1000;
                    
                    data.push({
                        time: utcTime + koreaOffset,  // 한국 시간으로 변환
                        open: parseFloat(k[1]),
                        high: parseFloat(k[2]),
                        low: parseFloat(k[3]),
                        close: parseFloat(k[4])
                    });
                }
                
                candleSeries.setData(data);
                if (chart) chart.timeScale().fitContent();
                
                // 현재 가격 업데이트
                if (data.length > 0) {
                    var lastPrice = data[data.length - 1].close;
                    setElement('currentPrice', lastPrice.toLocaleString() + ' USDT');
                }
                
                console.log('✅ Bybit 실시간 데이터 로드:', data.length + '개 캔들');
            } else {
                /* Bybit API 오류 */
                useSampleData(timeframe);
            }
        })
        .catch(function(e) {
            useSampleData(timeframe);
        });
}

function useSampleData(timeframe) {
    var sampleData = generateSampleData(timeframe);
    if (candleSeries) {
        candleSeries.setData(sampleData);
        if (chart) chart.timeScale().fitContent();
    }
}

// 데이터 로드
function loadData() {
    updateStatus();
    updateDashboard();
}

function updateStatus() {
    fetch('/api/status')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            var badge = document.getElementById('status-badge');
            var startBtn = document.getElementById('startBtn');
            var stopBtn = document.getElementById('stopBtn');
            
            if (data.is_running) {
                if (badge) {
                    badge.textContent = '✅ 실행 중';
                    badge.className = 'badge running';
                }
                if (startBtn) startBtn.disabled = true;
                if (stopBtn) stopBtn.disabled = false;
            } else {
                if (badge) {
                    badge.textContent = '❌ 중지됨';
                    badge.className = 'badge stopped';
                }
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) stopBtn.disabled = true;
            }

            // 트레이딩 상태 업데이트
            if (data.trading) {
                updateTradingStatus(data.trading);
            }
        })
        .catch(function(e) { /* 조용히 실패 처리 */ });
}

function updateTradingStatus(t) {
    setElement('trading-status-msg', t.status_message || '대기 중');
    
    if (t.current_price) {
        setElement('currentPrice', t.current_price.toLocaleString() + ' USDT');
    }
    
    if (t.balance) {
        setElement('balance', t.balance.toLocaleString() + ' USDT');
    }

    const pos = t.position;
    const posDisplay = document.getElementById('current-position-display');
    const entryDisplay = document.getElementById('entry-price-display');
    const exitDisplay = document.getElementById('exit-price-display');
    const slDisplay = document.getElementById('sl-price-display');

    if (t.last_exit_price && exitDisplay) {
        exitDisplay.textContent = t.last_exit_price.toLocaleString() + ' USDT';
    }

    if (pos) {
        const sideText = pos.side === 'buy' ? 'LONG' : 'SHORT';
        const sideClass = pos.side === 'buy' ? 'value long' : 'value short';
        
        if (posDisplay) {
            posDisplay.textContent = sideText + ' (' + (pos.qty || 0) + ')';
            posDisplay.className = sideClass;
        }
        
        if (entryDisplay) entryDisplay.textContent = (pos.entry_price || 0).toLocaleString() + ' USDT';
        if (slDisplay) slDisplay.textContent = (pos.sl || 0).toLocaleString() + ' USDT';
    } else {
        if (posDisplay) {
            posDisplay.textContent = '없음';
            posDisplay.className = 'value';
        }
        if (entryDisplay) entryDisplay.textContent = '-';
        if (slDisplay) slDisplay.textContent = '-';
    }
}

function updateDashboard() {
    fetch('/api/dashboard')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.status && data.status.trading) updateTradingStatus(data.status.trading);
            if (data.trades) updateTradeStats(data.trades);
            if (data.compounds) updateCompoundStats(data.compounds);
            if (data.logs) updateLogs(data.logs);
            
            // 마지막 업데이트 시간 표시
            var now = new Date();
            var timeStr = now.getHours().toString().padStart(2, '0') + ':' + 
                          now.getMinutes().toString().padStart(2, '0') + ':' + 
                          now.getSeconds().toString().padStart(2, '0');
            var lastUpdated = document.getElementById('last-updated');
            if (lastUpdated) {
                lastUpdated.textContent = '최근 업데이트: ' + timeStr;
            }
        })
        .catch(function(e) { console.error('Dashboard update failed:', e); });
}

function updateTradeStats(s) {
    var pnl = s.total_pnl || 0;
    setElement('totalPnl', (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + ' USDT', 'value ' + (pnl >= 0 ? 'positive' : 'negative'));
    setElement('totalTrades', s.total_trades || 0);
    
    var wr = s.win_rate || 0;
    setElement('winRate', wr.toFixed(1) + '%', 'value ' + (wr >= 50 ? 'positive' : 'negative'));
    setElement('winLossRatio', '승/패: ' + (s.wins || 0) + '/' + (s.losses || 0));
    
    if (s.recent_trades && s.recent_trades.length > 0) {
        updateTrades(s.recent_trades);
    }
}

function updateTrades(trades) {
    var c = document.getElementById('tradesContainer');
    if (!c) return;
    
    if (!trades || trades.length === 0) {
        c.innerHTML = '<div class="no-data" style="padding: 20px; text-align: center; color: #8b949e;">아직 거래 내역이 없습니다.</div>';
        return;
    }
    
    var html = '';
    for (var i = 0; i < trades.length; i++) {
        var t = trades[i];
        var profit = (t.pnl_net || 0) > 0;
        var side = t.side === 'buy' ? '매수' : '매도';
        
        html += '<div class="trade-item" data-profit="' + profit + '">';
        html += '<div class="trade-header">';
        html += '<span class="trade-type ' + t.side + '">' + side + '</span>';
        html += '<span class="trade-pnl ' + (profit ? 'positive' : 'negative') + '">' + (profit ? '+' : '') + (t.pnl_net || 0).toFixed(2) + ' USDT</span>';
        html += '</div>';
        html += '<div class="trade-details">진입: ' + (t.entry_price || 0).toLocaleString() + ' | 청산: ' + (t.exit_price || 0).toLocaleString() + '</div>';
        html += '<div class="trade-details">' + (t.entry_time || '-') + ' ~ ' + (t.exit_time || '-') + '</div>';
        html += '</div>';
    }
    c.innerHTML = html;
}

function updateCompoundStats(s) {
    setElement('balance', (s.final_balance || 0).toLocaleString() + ' USDT');
    setElement('compoundCount', (s.total_compounds || 0) + '회');
    
    var cp = document.getElementById('compoundProfit');
    if (cp) { 
        cp.textContent = '재투자: ' + (s.total_profit || 0).toFixed(2) + ' USDT'; 
        cp.className = 'change ' + ((s.total_profit || 0) >= 0 ? 'positive' : 'negative'); 
    }
}

function updateLogs(logs) {
    var pre = document.getElementById('logsPre');
    if (!pre || !logs || logs.length === 0) return;
    
    var html = '';
    var recent = logs.slice(-100);
    
    for (var i = 0; i < recent.length; i++) {
        var log = recent[i];
        if (!log || log.trim() === '') continue;
        
        var formattedLog = formatLogLine(log);
        if (formattedLog) {
            html += formattedLog + '\n';
        }
    }
    
    pre.innerHTML = html || '<span style="color:#8b949e">로그가 없습니다.</span>';
    
    // 자동 스크롤
    var logsWindow = pre.parentElement;
    if (logsWindow) {
        logsWindow.scrollTop = logsWindow.scrollHeight;
    }
}

function formatLogLine(log) {
    // 1. 불필요한 시스템 로그 및 정보 메시지 제외 (사용자 요청: 거래로그만 나오게)
    const excludePatterns = [
        '===', '---', '🏆', '📊', '⏱️', '🚀', '🕒', '🌐', '📝', '✨',
        'Created PID file',
        'Dynamic config loaded',
        'Paper position synced',
        'Bot starting main loop',
        '봇 상태 확인 완료',
        '시장 분석 중',
        '상한선:',
        'Bybit 실시간 데이터 로드'
    ];

    for (let pattern of excludePatterns) {
        if (log.indexOf(pattern) > -1) return null;
    }

    // 2. 거래 관련 핵심 키워드가 포함된 로그만 허용
    const tradeKeywords = ['Price:', 'Balance:', 'Pos:', '[PAPER]', '[REAL]', 'Signal', '진입', '청산', 'Profit', 'Loss', 'PnL'];
    let isTradeLog = false;
    for (let kw of tradeKeywords) {
        if (log.indexOf(kw) > -1) {
            isTradeLog = true;
            break;
        }
    }

    if (!isTradeLog) return null; // 거래 관련 로그가 아니면 무시

    // 형식 1: 2025-12-22 19:06:22 | INFO | 메시지
    // 형식 2: [21:05:46] INFO: 메시지
    var match1 = log.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),?\d* \| (\w+) \| (.+)$/);
    var match2 = log.match(/^\[(\d{2}:\d{2}:\d{2})\] (\w+): (.+)$/);
    
    var timestamp, level, message;
    
    if (match1) {
        timestamp = match1[1];
        level = match1[2];
        message = match1[3];
    } else if (match2) {
        timestamp = match2[1];
        level = match2[2];
        message = match2[3];
    } else {
        return '<span style="color:#8b949e">' + log + '</span>';
    }
    
    // 레벨별 색상
    var levelColor = '#79c0ff'; // INFO
    if (level === 'ERROR') levelColor = '#ff7b72'; // Red
    else if (level === 'WARNING') levelColor = '#ffa657'; // Orange
    
    // 메시지 하이라이트
    message = highlightMessage(message);
    
    return '<span style="color:#8b949e">[' + timestamp + ']</span> ' +
           '<span style="color:' + levelColor + '; font-weight: bold;">' + level + '</span>: ' +
           message;
}

function highlightMessage(msg) {
    // [PAPER] / [REAL] 태그
    msg = msg.replace(/\[PAPER\]/g, '<span style="background-color:#3fb95033; color:#3fb950; border:1px solid #3fb95066; padding:0 4px; border-radius:3px; font-weight:bold; font-size:0.85em;">PAPER</span>');
    msg = msg.replace(/\[REAL\]/g, '<span style="background-color:#f0883e33; color:#f0883e; border:1px solid #f0883e66; padding:0 4px; border-radius:3px; font-weight:bold; font-size:0.85em;">REAL</span>');

    // 동적 설정 및 동기화 메시지 (HTML 태그가 포함되기 전에 먼저 처리)
    if (msg.includes('Paper position synced') || msg.includes('Dynamic config loaded')) {
        msg = msg.replace(/(['"]\w+['"]):/g, '<span style="color:#79c0ff">$1</span>:'); // Key highlight
        msg = msg.replace(/:\s?({|})|,\s?({|})/g, '<span style="color:#8b949e">$0</span>'); // Braces and commas
        msg = msg.replace(/(\b\d+\.?\d*\b)/g, '<span style="color:#d29922">$1</span>'); // Numbers (word boundary added)
        msg = msg.replace(/('buy'|'long')/g, '<span style="color:#3fb950">$1</span>'); // buy/long
        msg = msg.replace(/('sell'|'short')/g, '<span style="color:#f85149">$1</span>'); // sell/short
        return msg; // 이 메시지는 여기서 처리 종료
    }

    // 키워드 하이라이트 (Label: Value)
    msg = msg.replace(/(Price|현재가): ([\d,.]+)/g, '<span style="color:#8b949e">$1:</span> <span style="color:#f0883e; font-weight:bold;">$2</span>');
    msg = msg.replace(/(Balance|잔고): ([\d,.]+)(\s?USDT)?/g, '<span style="color:#8b949e">$1:</span> <span style="color:#d29922; font-weight:bold;">$2$3</span>');
    msg = msg.replace(/(Pos|포지션): ([\w\s]+)(\s?\([\d,.]+\))?/g, function(m, p1, side, qty) {
        var color = '#8b949e';
        if (side.includes('BUY') || side.includes('LONG')) color = '#3fb950';
        else if (side.includes('SELL') || side.includes('SHORT')) color = '#f85149';
        
        var html = '<span style="color:#8b949e">' + p1 + ':</span> <span style="color:' + color + '; font-weight:bold;">' + side + '</span>';
        if (qty) {
            html += ' <span style="color:#8b949e; font-size:0.9em;">' + qty + '</span>';
        }
        return html;
    });
    msg = msg.replace(/(ATR): ([\d,.]+)/g, '<span style="color:#8b949e">$1:</span> <span style="color:#a371f7;">$2</span>');

    // 화살표 및 구분선
    msg = msg.replace(/\|/g, '<span style="color:#30363d">|</span>');
    msg = msg.replace(/->/g, '<span style="color:#8b949e">→</span>');
    msg = msg.replace(/=>/g, '<span style="color:#8b949e">⇒</span>');

    // 수익률 및 PnL
    msg = msg.replace(/(수익률|PnL|Profit|Loss): ([\-\+\d.]+)%/g, function(m, p1, val) {
        var color = parseFloat(val) >= 0 ? '#3fb950' : '#f85149';
        return p1 + ': <span style="color:' + color + ';font-weight:bold;">' + val + '%</span>';
    });

    // 진입/청산 신호
    msg = msg.replace(/(ENTRY|EXIT) Signal/g, '<span style="color:#f0883e; font-weight:bold;">$1 Signal</span>');
    msg = msg.replace(/(LONG|BUY) 진입/g, '<span style="color:#3fb950; font-weight:bold;">$0</span>');
    msg = msg.replace(/(SHORT|SELL) 진입/g, '<span style="color:#f85149; font-weight:bold;">$0</span>');

    return msg;
}

function setElement(id, val, cls) { 
    var e = document.getElementById(id); 
    if (e) { 
        e.textContent = val; 
        if (cls) e.className = cls; 
    } 
}


// 봇 제어
function startBot() {
    if (!confirm('봇을 시작하시겠습니까?')) return;
    showAlert('봇 시작 요청 중...', 'info');
    
    fetch('/api/bot/start', { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            showAlert(data.success ? '✅ ' + data.message : '❌ ' + data.message, data.success ? 'success' : 'error');
            setTimeout(updateStatus, 1000);
        })
        .catch(function() { showAlert('❌ 봇 시작 실패', 'error'); });
}

function stopBot() {
    if (!confirm('봇을 정지하시겠습니까?')) return;
    showAlert('봇 정지 요청 중...', 'info');
    
    fetch('/api/bot/stop', { method: 'POST' })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            showAlert(data.success ? '✅ ' + data.message : '⚠️ ' + data.message, data.success ? 'success' : 'warning');
            setTimeout(updateStatus, 1000);
        })
        .catch(function() { showAlert('❌ 봇 정지 실패', 'error'); });
}

// 탭 전환
function switchTab(name, btn) {
    var tabs = document.querySelectorAll('.tab');
    var contents = document.querySelectorAll('.tab-content');
    
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove('active');
    }
    for (var i = 0; i < contents.length; i++) {
        contents[i].classList.remove('active');
    }
    
    if (btn) btn.classList.add('active');
    
    var tab = document.getElementById(name + '-tab');
    if (tab) tab.classList.add('active');
    
    // 차트 탭 선택시 차트 초기화
    if (name === 'chart') {
        setTimeout(function() {
            if (!chart) {
                initChart();
            } else {
                chart.timeScale().fitContent();
            }
        }, 100);
    }
}

// 필터
function filterLogs(level) {
    showAlert('로그 필터: ' + (level === 'all' ? '전체' : level), 'info');
}

function filterTrades(type) {
    var items = document.querySelectorAll('.trade-item');
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var profit = item.getAttribute('data-profit') === 'true';
        if (type === 'all') {
            item.style.display = 'block';
        } else if (type === 'profit') {
            item.style.display = profit ? 'block' : 'none';
        } else if (type === 'loss') {
            item.style.display = !profit ? 'block' : 'none';
        }
    }
}

function refreshLogs() {
    fetch('/api/logs?lines=100')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.logs) updateLogs(data.logs);
            showAlert('로그 새로고침 완료', 'success');
        })
        .catch(function() { showAlert('로그 새로고침 실패', 'error'); });
}

// 설정 불러오기
function loadSettings() {
    fetch('/api/config')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (document.getElementById('settingSymbol')) document.getElementById('settingSymbol').value = data.SYMBOL || 'BTCUSDT';
            if (document.getElementById('settingLeverage')) document.getElementById('settingLeverage').value = data.LEVERAGE || 2;
            if (document.getElementById('settingCompoundFreq')) document.getElementById('settingCompoundFreq').value = data.COMPOUND_FREQUENCY || 25;
            if (document.getElementById('settingReinvest')) document.getElementById('settingReinvest').value = (data.PROFIT_REINVESTMENT * 100) || 95;
        })
}

function startAutoUpdate() {
    console.log('⏱️ 자동 업데이트 시작 (10초 주기)');
    if (updateIntervals.main) clearInterval(updateIntervals.main);
    updateIntervals.main = setInterval(function() {
        console.log('🔄 자동 업데이트 실행 중...');
        loadData();
    }, 10000);
}

function showAlert(msg, type) {
    const container = document.getElementById('alert-container');
    if (!container) return;
    
    const div = document.createElement('div');
    div.className = 'alert alert-' + type;
    div.textContent = msg;
    container.appendChild(div);
    
    setTimeout(() => {
        div.style.opacity = '0';
        setTimeout(() => div.remove(), 300);
    }, 3000);
}

function displaySampleData() {
    // 초기 로딩시 샘플 데이터 표시
    updateTradeStats({
        total_trades: 0,
        wins: 0,
        losses: 0,
        win_rate: 0,
        total_pnl: 0,
        recent_trades: []
    });
}

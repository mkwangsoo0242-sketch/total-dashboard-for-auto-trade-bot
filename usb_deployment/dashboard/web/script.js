// script.js – 대시보드 프론트엔드 (최종 디자인 적용)

const DEMO_MODE = false; // 실전 배포 시 false로 변경
const API_BASE = '/api';

const bots = [
  { id: 'BTC_30m', name: '30분 하이브리드 봇' },
  { id: 'Bybit_1h', name: '1시간 초공격 봇' },
  { id: 'Deploy_15m', name: '15분 배포 봇' },
  { id: 'Real_5m', name: '5분 스캘핑 봇' },
  { id: 'Ultimate_100m', name: '1억 목표 최종 봇' }
];

const container = document.getElementById('botContainer');
const charts = {};

function safeParseFloat(val, fallback = 0) {
  if (typeof val === 'number') return val;
  if (!val) return fallback;
  const parsed = parseFloat(val.toString().replace(/,/g, ''));
  return isNaN(parsed) ? fallback : parsed;
}

// ---------- 1. 데이터 생성 (가짜 데이터) ----------
function generateChartData(basePrice) {
  const data = [];
  const now = Math.floor(Date.now() / 1000);
  let price = basePrice > 0 ? basePrice : 43500;

  for (let i = 80; i > 0; i--) {
    const time = now - (i * 60);
    const open = price;
    const volatility = price * 0.0015; // 변동성
    const change = (Math.random() - 0.5) * volatility * 2;
    const close = open + change;
    const high = Math.max(open, close) + Math.random() * volatility * 0.5;
    const low = Math.min(open, close) - Math.random() * volatility * 0.5;

    data.push({ time, open, high, low, close });
    price = close;
  }
  return data;
}

// ---------- 2. 차트 초기화 ----------
function initChart(id, info) {
  const chartEl = document.getElementById(`chart-${id}`);
  if (!chartEl || !window.LightweightCharts) return;

  if (charts[id]) {
    updateChartData(id, info);
    return;
  }

  if (chartEl.clientWidth === 0) {
    requestAnimationFrame(() => initChart(id, info));
    return;
  }

  // 차트 생성 (프리미엄 스타일)
  const chart = LightweightCharts.createChart(chartEl, {
    width: chartEl.clientWidth,
    height: 180,
    layout: {
      background: { color: 'transparent' },
      textColor: '#d1d4dc',
    },
    grid: {
      vertLines: { color: 'rgba(42, 46, 57, 0.2)' },
      horzLines: { color: 'rgba(42, 46, 57, 0.2)' }
    },
    rightPriceScale: {
      borderColor: 'rgba(197, 203, 206, 0.3)',
      scaleMargins: { top: 0.15, bottom: 0.15 },
    },
    timeScale: {
      visible: true,
      borderColor: 'rgba(197, 203, 206, 0.3)',
      timeVisible: true,
      secondsVisible: false,
    },
    handleScroll: false,
    handleScale: false,
  });

  const series = chart.addCandlestickSeries({
    upColor: '#00E396',
    downColor: '#FF4560',
    borderVisible: false,
    wickUpColor: '#00E396',
    wickDownColor: '#FF4560'
  });

  charts[id] = { chart, series, lines: {} };

  // 리사이즈 옵저버
  new ResizeObserver(entries => {
    if (entries[0] && entries[0].contentRect.width > 0) {
      chart.applyOptions({ width: entries[0].contentRect.width });
    }
  }).observe(chartEl);

  updateChartData(id, info);
}

// ---------- 3. 데이터 업데이트 ----------
function updateChartData(id, info) {
  const { chart, series, lines } = charts[id];
  const marketPrice = safeParseFloat(info.market_price, 43500);

  // 데이터 갱신 (데모용)
  series.setData(generateChartData(marketPrice));

  // 기존 선 제거
  if (lines.sl) series.removePriceLine(lines.sl);
  if (lines.tp) series.removePriceLine(lines.tp);
  if (lines.curr) series.removePriceLine(lines.curr);

  const sl = safeParseFloat(info.stop_loss);
  const tp = safeParseFloat(info.take_profit);
  const curr = safeParseFloat(info.market_price);

  // SL (손절) - 빨강
  if (sl > 0) {
    lines.sl = series.createPriceLine({
      price: sl, color: '#FF4560', lineWidth: 1, lineStyle: 0,
      axisLabelVisible: true, title: 'SL'
    });
  }
  // TP (익절) - 초록/파랑 계열
  if (tp > 0) {
    lines.tp = series.createPriceLine({
      price: tp, color: '#00E396', lineWidth: 1, lineStyle: 0,
      axisLabelVisible: true, title: 'TP'
    });
  }
  // 현재가 - 노랑
  if (curr > 0) {
    lines.curr = series.createPriceLine({
      price: curr, color: '#FFB74D', lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title: '현재'
    });
  }

  chart.timeScale().fitContent();
}

// ---------- UI 렌더링 ----------
function renderBots(data) {
  bots.forEach(b => {
    const info = data[b.id] || { status: 'Stopped', balance: '0', profit: '0%', market_price: '-' };
    let card = document.getElementById(`card-${b.id}`);

    // 카드 생성
    if (!card) {
      card = document.createElement('div');
      card.id = `card-${b.id}`;
      card.className = 'card';
      card.innerHTML = `
        <div class="status-row">
          <h2 style="font-size:1.1rem; margin:0;">${b.name}</h2>
          <span class="pos-badge pos-none">NONE</span>
        </div>
        <div class="market-price-text" style="font-size:1.1rem; color:#FFB74D; font-weight:600; font-family:'JetBrains Mono', monospace; margin:4px 0;">
          - USDT
        </div>
        
        <div id="chart-${b.id}" class="chart-container" style="
          width:100%; height:180px; 
          background: rgba(0,0,0,0.25); 
          border-radius: 8px;
          margin: 10px 0;
          overflow: hidden;
        "></div>

        <div class="metrics">
          <div class="metric-item"><span class="metric-label">현재 잔액</span><span class="metric-value balance">0</span></div>
          <div class="metric-item"><span class="metric-label">오늘 수익</span><span class="metric-value today-profit">0</span></div>
        </div>
        <div class="trading-info">
          <div class="info-item"><span class="info-label">진입가</span><span class="info-value entry-price">-</span></div>
          <div class="info-item"><span class="info-label">수익률</span><span class="info-value total-profit">0%</span></div>
          <div class="info-item"><span class="info-label">손절(SL)</span><span class="info-value sl" style="color:#FF4560;">-</span></div>
          <div class="info-item"><span class="info-label">익절(TP)</span><span class="info-value tp" style="color:#00E396;">-</span></div>
        </div>
        <div style="display: flex; gap: 6px; margin-top: 15px;">
          <button class="btn" data-id="${b.id}" data-action="start" style="flex:1;">▶ 시작</button>
          <button class="btn" data-id="${b.id}" data-action="stop" style="flex:1;">■ 중지</button>
          <button class="btn" data-id="${b.id}" data-action="logs" style="flex:1;">📜 로그</button>
        </div>
        <div class="log" id="log-${b.id}" hidden></div>
      `;
      container.appendChild(card);
    }

    // 값 업데이트
    const pos = (info.position || 'NONE').toUpperCase();
    const badge = card.querySelector('.pos-badge');
    badge.textContent = pos;
    badge.className = `pos-badge pos-${pos.toLowerCase()}`;

    card.querySelector('.market-price-text').textContent = `${info.market_price || '-'} USDT`;
    card.querySelector('.balance').textContent = info.balance;
    card.querySelector('.today-profit').textContent = info.today_profit || '0';
    card.querySelector('.entry-price').textContent = info.entry_price || '-';

    // 수익률 색상
    const profitVal = info.profit || '0%';
    const profitEl = card.querySelector('.total-profit');
    profitEl.textContent = profitVal;
    profitEl.className = `info-value total-profit ${profitVal.startsWith('+') ? 'profit-up' : (profitVal.startsWith('-') ? 'profit-down' : '')}`;

    card.querySelector('.sl').textContent = info.stop_loss || '-';
    card.querySelector('.tp').textContent = info.take_profit || '-';

    // 차트 그리기
    requestAnimationFrame(() => initChart(b.id, info));
  });
}

function refresh() {
  const url = DEMO_MODE ? `demo_data.json?t=${Date.now()}` : `${API_BASE}/status`;
  fetch(url).then(r => r.json()).then(renderBots).catch(console.error);
}

setInterval(refresh, 5000);
refresh();

container.addEventListener('click', e => {
  const btn = e.target.closest('.btn');
  if (!btn) return;
  const { id, action } = btn.dataset;
  if (action === 'logs') {
    const l = document.getElementById(`log-${id}`);
    l.hidden = !l.hidden;
    l.textContent = "(시스템) 실시간 로그 수신 중...";
  } else {
    if (!DEMO_MODE) fetch(`${API_BASE}/${action}/${id}`, { method: 'POST' });
    else alert(`${action} 명령 전송`);
  }
});

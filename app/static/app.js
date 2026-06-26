const health = document.querySelector('#health');
const version = document.querySelector('#version');
const routeWarehouse = document.querySelector('#routeWarehouse');
const forecastWarehouse = document.querySelector('#forecastWarehouse');
const routeStrategy = document.querySelector('#routeStrategy');
const forecastDays = document.querySelector('#forecastDays');
const forecastScenario = document.querySelector('#forecastScenario');
const routeMiniStats = document.querySelector('#routeMiniStats');
const routeTimeline = document.querySelector('#routeTimeline');
const forecastSummary = document.querySelector('#forecastSummary');
const forecastTable = document.querySelector('#forecastTable');
const dataList = document.querySelector('#dataList');
const alertsOutput = document.querySelector('#alertsOutput');
const historyOutput = document.querySelector('#historyOutput');
const metricsOutput = document.querySelector('#metricsOutput');

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Ошибка запроса');
  }

  return response.json();
}

function statusClass(status) {
  if (status === 'risk') return 'risk';
  if (status === 'warning') return 'warning';
  return 'ok';
}

function renderWarehouseOptions(warehouses) {
  const options = warehouses.map((warehouse) => (
    `<option value="${warehouse.id}">${warehouse.name} · ${warehouse.city}</option>`
  )).join('');
  routeWarehouse.innerHTML = options;
  forecastWarehouse.innerHTML = options;
}

async function checkHealth() {
  try {
    const data = await requestJson('/health');
    health.textContent = `Сервис работает: ${data.status}`;
    health.className = 'status ok';
    version.textContent = `Backend: ${data.service} v${data.version}`;
  } catch (error) {
    health.textContent = 'Сервис недоступен';
    health.className = 'status risk';
    version.textContent = 'Backend не отвечает';
  }
}

async function loadDashboard() {
  const data = await requestJson('/api/dashboard');
  document.querySelector('#statWarehouses').textContent = data.warehouses;
  document.querySelector('#statDeliveries').textContent = data.delivery_points;
  document.querySelector('#statPriority').textContent = data.high_priority_deliveries;
  document.querySelector('#statLoad').textContent = `${data.average_warehouse_load_percent}%`;
  renderHistory(data.recent_operations);
}

async function loadWarehouses() {
  const warehouses = await requestJson('/api/warehouses');
  renderWarehouseOptions(warehouses);
}

async function optimizeRoute() {
  routeTimeline.textContent = 'Строю маршрут...';
  routeMiniStats.innerHTML = '';

  try {
    const data = await requestJson('/api/optimize-route', {
      method: 'POST',
      body: JSON.stringify({
        warehouse_id: Number(routeWarehouse.value),
        strategy: routeStrategy.value,
      }),
    });

    routeMiniStats.innerHTML = `
      <div><span>Дистанция</span><strong>${data.total_distance_km} км</strong></div>
      <div><span>Время</span><strong>${data.estimated_time_hours} ч</strong></div>
      <div><span>Стоимость топлива</span><strong>${data.fuel_cost_rub} ₽</strong></div>
      <div><span>Оценка</span><strong>${data.service_score}/100</strong></div>
    `;

    routeTimeline.innerHTML = data.stops.map((stop) => `
      <div class="timeline-item">
        <div class="timeline-step">${stop.step}</div>
        <div>
          <strong>${stop.client}</strong>
          <p>${stop.address}</p>
          <small>Приоритет: ${stop.priority} · Окно: ${stop.time_window} · От предыдущей точки: ${stop.distance_from_previous_km} км</small>
        </div>
      </div>
    `).join('');

    await loadDashboard();
    await loadHistory();
  } catch (error) {
    routeTimeline.textContent = error.message;
  }
}

async function forecastInventory() {
  forecastSummary.textContent = 'Считаю прогноз...';
  forecastTable.innerHTML = '';

  try {
    const data = await requestJson('/api/inventory/forecast', {
      method: 'POST',
      body: JSON.stringify({
        warehouse_id: Number(forecastWarehouse.value),
        days: Number(forecastDays.value),
        scenario: forecastScenario.value,
      }),
    });

    forecastSummary.className = `summary-banner ${statusClass(data.summary.status)}`;
    forecastSummary.textContent = `Склад: ${data.warehouse}. Рискованных позиций: ${data.summary.risk_items}. Рекомендовано пополнить: ${data.summary.recommended_replenishment_units} ед.`;

    forecastTable.innerHTML = data.items.map((item) => `
      <tr>
        <td><strong>${item.sku}</strong><br><small>${item.recommendation}</small></td>
        <td>${item.current_stock}</td>
        <td>${item.predicted_demand}</td>
        <td>${item.remaining_after_period}</td>
        <td><span class="chip ${statusClass(item.status)}">${item.status}</span></td>
      </tr>
    `).join('');

    await loadDashboard();
    await loadHistory();
  } catch (error) {
    forecastSummary.textContent = error.message;
  }
}

async function loadData() {
  const [warehouses, deliveries] = await Promise.all([
    requestJson('/api/warehouses'),
    requestJson('/api/deliveries'),
  ]);

  const warehouseCards = warehouses.map((warehouse) => `
    <div class="data-item">
      <strong>${warehouse.name}</strong>
      <p>${warehouse.city}, ${warehouse.address}</p>
      <small>Загрузка: ${warehouse.load_percent}% · Вместимость: ${warehouse.capacity_units} ед.</small>
    </div>
  `).join('');

  const deliveryCards = deliveries.map((delivery) => `
    <div class="data-item">
      <strong>${delivery.client}</strong>
      <p>${delivery.address}</p>
      <small>Приоритет: ${delivery.priority} · Окно: ${delivery.time_window}</small>
    </div>
  `).join('');

  dataList.innerHTML = `
    <h3>Склады</h3>${warehouseCards}
    <h3>Точки доставки</h3>${deliveryCards}
  `;
}

async function loadAlerts() {
  alertsOutput.textContent = 'Проверяю риски...';
  const data = await requestJson('/api/alerts');
  if (data.count === 0) {
    alertsOutput.innerHTML = '<div class="alert ok">Критических рисков нет.</div>';
    return;
  }
  alertsOutput.innerHTML = data.alerts.map((alert) => `
    <div class="alert ${statusClass(alert.status)}">
      <strong>${alert.warehouse} · ${alert.sku}</strong>
      <p>${alert.message}</p>
    </div>
  `).join('');
}

function renderHistory(records) {
  if (!records || records.length === 0) {
    historyOutput.textContent = 'История пока пустая.';
    return;
  }
  historyOutput.innerHTML = records.map((record) => `
    <div class="history-item">
      <strong>${record.operation}</strong>
      <span>${record.time}</span>
      <p>${Object.entries(record)
        .filter(([key]) => !['time', 'operation'].includes(key))
        .map(([key, value]) => `${key}: ${value}`)
        .join(' · ')}</p>
    </div>
  `).join('');
}

async function loadHistory() {
  const data = await requestJson('/api/history');
  renderHistory(data);
}

async function loadMetrics() {
  metricsOutput.textContent = 'Загружаю метрики...';
  const data = await requestJson('/api/metrics');
  metricsOutput.innerHTML = Object.entries(data).map(([key, value]) => `
    <div class="metric"><span>${key}</span><strong>${value}</strong></div>
  `).join('');
}

async function refreshAll() {
  await checkHealth();
  await loadWarehouses();
  await loadDashboard();
  await loadHistory();
}

document.querySelector('#routeButton').addEventListener('click', optimizeRoute);
document.querySelector('#forecastButton').addEventListener('click', forecastInventory);
document.querySelector('#loadDataButton').addEventListener('click', loadData);
document.querySelector('#alertsButton').addEventListener('click', loadAlerts);
document.querySelector('#metricsButton').addEventListener('click', loadMetrics);
document.querySelector('#refreshAllButton').addEventListener('click', refreshAll);

refreshAll();

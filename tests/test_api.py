from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_dashboard():
    response = client.get('/api/dashboard')
    data = response.json()
    assert response.status_code == 200
    assert data['warehouses'] >= 2
    assert data['delivery_points'] >= 5


def test_route_optimization_priority_strategy():
    response = client.post('/api/optimize-route', json={'warehouse_id': 1, 'strategy': 'priority_balanced'})
    data = response.json()

    assert response.status_code == 200
    assert data['total_distance_km'] > 0
    assert len(data['stops']) >= 1
    assert data['fuel_cost_rub'] > 0
    assert data['generated_in_ms'] >= 0


def test_route_optimization_express_strategy():
    response = client.post('/api/optimize-route', json={'warehouse_id': 1, 'strategy': 'express_only'})
    data = response.json()

    assert response.status_code == 200
    assert all(stop['priority'] >= 3 for stop in data['stops'])


def test_inventory_forecast():
    response = client.post('/api/inventory/forecast', json={'warehouse_id': 1, 'days': 7, 'scenario': 'normal'})
    data = response.json()

    assert response.status_code == 200
    assert data['warehouse'] == 'Склад Север'
    assert len(data['items']) == 3
    assert 'summary' in data


def test_alerts():
    response = client.get('/api/alerts')
    data = response.json()
    assert response.status_code == 200
    assert 'alerts' in data
    assert 'count' in data


def test_unknown_warehouse():
    response = client.post('/api/optimize-route', json={'warehouse_id': 999})
    assert response.status_code == 404

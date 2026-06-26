from __future__ import annotations

from dataclasses import asdict, dataclass
from math import atan2, cos, radians, sin, sqrt
from time import perf_counter, strftime
from typing import Dict, List, Literal, Optional

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


app = FastAPI(
    title="TransLogix MVP",
    description="Интеллектуальная логистическая система для оптимизации маршрутов доставки, прогноза складских запасов и мониторинга прототипа.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@dataclass(frozen=True)
class Warehouse:
    id: int
    name: str
    city: str
    address: str
    lat: float
    lon: float
    capacity_units: int
    stock: Dict[str, int]


@dataclass(frozen=True)
class DeliveryPoint:
    id: int
    client: str
    address: str
    lat: float
    lon: float
    demand: Dict[str, int]
    priority: int = 1
    time_window: str = "10:00-18:00"
    service_minutes: int = 20


WAREHOUSES: List[Warehouse] = [
    Warehouse(
        id=1,
        name="Склад Север",
        city="Санкт-Петербург",
        address="Комендантский пр., 12",
        lat=59.985,
        lon=30.301,
        capacity_units=1600,
        stock={"phones": 240, "laptops": 70, "accessories": 900},
    ),
    Warehouse(
        id=2,
        name="Склад Юг",
        city="Москва",
        address="Варшавское ш., 95",
        lat=55.630,
        lon=37.615,
        capacity_units=1900,
        stock={"phones": 310, "laptops": 120, "accessories": 700},
    ),
]

DELIVERIES: List[DeliveryPoint] = [
    DeliveryPoint(
        id=101,
        client="Retail Point A",
        address="Невский проспект, 40",
        lat=59.934,
        lon=30.335,
        demand={"phones": 20, "accessories": 60},
        priority=3,
        time_window="09:00-12:00",
    ),
    DeliveryPoint(
        id=102,
        client="Retail Point B",
        address="Пулковское шоссе, 25",
        lat=59.800,
        lon=30.320,
        demand={"laptops": 8, "accessories": 30},
        priority=2,
        time_window="12:00-16:00",
    ),
    DeliveryPoint(
        id=103,
        client="Retail Point C",
        address="Выборгское шоссе, 13",
        lat=60.050,
        lon=30.315,
        demand={"phones": 15, "laptops": 3},
        priority=1,
        time_window="14:00-18:00",
    ),
    DeliveryPoint(
        id=104,
        client="Retail Point D",
        address="Ленинский проспект, 90",
        lat=59.851,
        lon=30.268,
        demand={"phones": 12, "accessories": 45},
        priority=2,
        time_window="10:00-15:00",
    ),
    DeliveryPoint(
        id=105,
        client="Express Client E",
        address="Лиговский проспект, 10",
        lat=59.927,
        lon=30.360,
        demand={"phones": 30, "laptops": 5, "accessories": 80},
        priority=3,
        time_window="08:00-11:00",
        service_minutes=25,
    ),
]

OPERATION_HISTORY: List[Dict[str, str | float | int]] = []


RouteStrategy = Literal["priority_balanced", "nearest_first", "express_only"]
DemandScenario = Literal["normal", "promo", "low_demand"]


class RouteRequest(BaseModel):
    warehouse_id: int = Field(default=1, description="ID склада, от которого строится маршрут")
    delivery_ids: Optional[List[int]] = Field(default=None, description="Список точек доставки")
    strategy: RouteStrategy = Field(default="priority_balanced", description="Стратегия оптимизации")


class ForecastRequest(BaseModel):
    warehouse_id: int = 1
    days: int = Field(default=7, ge=1, le=60)
    scenario: DemandScenario = "normal"


class RouteStop(BaseModel):
    step: int
    delivery_id: int
    client: str
    address: str
    distance_from_previous_km: float
    priority: int
    time_window: str
    demand_units: int


class RouteInsight(BaseModel):
    label: str
    value: str


class RouteResponse(BaseModel):
    warehouse: str
    strategy: RouteStrategy
    stops: List[RouteStop]
    total_distance_km: float
    estimated_time_hours: float
    fuel_cost_rub: int
    co2_kg: float
    service_score: float
    generated_in_ms: float
    insights: List[RouteInsight]


class ForecastItem(BaseModel):
    sku: str
    current_stock: int
    predicted_demand: int
    remaining_after_period: int
    status: str
    recommendation: str


class ForecastResponse(BaseModel):
    warehouse: str
    days: int
    scenario: DemandScenario
    items: List[ForecastItem]
    summary: Dict[str, int | str]


class MetricsResponse(BaseModel):
    status: str
    warehouses: int
    delivery_points: int
    history_records: int
    memory_mb: float
    cpu_percent: float


def remember(operation: str, details: Dict[str, str | float | int]) -> None:
    OPERATION_HISTORY.insert(
        0,
        {
            "time": strftime("%H:%M:%S"),
            "operation": operation,
            **details,
        },
    )
    del OPERATION_HISTORY[15:]


def find_warehouse(warehouse_id: int) -> Warehouse:
    for warehouse in WAREHOUSES:
        if warehouse.id == warehouse_id:
            return warehouse
    raise HTTPException(status_code=404, detail="Склад не найден")


def select_deliveries(delivery_ids: Optional[List[int]], strategy: RouteStrategy) -> List[DeliveryPoint]:
    deliveries = list(DELIVERIES)
    if delivery_ids is not None:
        selected = [delivery for delivery in deliveries if delivery.id in delivery_ids]
        if len(selected) != len(set(delivery_ids)):
            raise HTTPException(status_code=404, detail="Одна или несколько точек доставки не найдены")
        deliveries = selected

    if strategy == "express_only":
        deliveries = [delivery for delivery in deliveries if delivery.priority >= 3]

    return deliveries


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между точками по формуле гаверсинуса."""
    radius = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius * c


def total_demand_units(delivery: DeliveryPoint) -> int:
    return sum(delivery.demand.values())


def build_route(warehouse: Warehouse, deliveries: List[DeliveryPoint], strategy: RouteStrategy) -> tuple[List[RouteStop], float]:
    """
    Эвристическая оптимизация маршрута.
    priority_balanced: сначала высокий приоритет, затем ближайшая точка.
    nearest_first: всегда ближайшая точка.
    express_only: только срочные точки, далее приоритет + расстояние.
    """
    current_lat, current_lon = warehouse.lat, warehouse.lon
    remaining = deliveries[:]
    route: List[RouteStop] = []
    total_distance = 0.0

    while remaining:
        if strategy == "nearest_first":
            candidates = remaining
        else:
            max_priority = max(item.priority for item in remaining)
            candidates = [item for item in remaining if item.priority == max_priority]

        next_delivery = min(
            candidates,
            key=lambda item: distance_km(current_lat, current_lon, item.lat, item.lon),
        )
        leg = distance_km(current_lat, current_lon, next_delivery.lat, next_delivery.lon)
        total_distance += leg
        route.append(
            RouteStop(
                step=len(route) + 1,
                delivery_id=next_delivery.id,
                client=next_delivery.client,
                address=next_delivery.address,
                distance_from_previous_km=round(leg, 2),
                priority=next_delivery.priority,
                time_window=next_delivery.time_window,
                demand_units=total_demand_units(next_delivery),
            )
        )
        current_lat, current_lon = next_delivery.lat, next_delivery.lon
        remaining.remove(next_delivery)

    total_distance += distance_km(current_lat, current_lon, warehouse.lat, warehouse.lon)
    return route, total_distance


def scenario_multiplier(scenario: DemandScenario) -> float:
    if scenario == "promo":
        return 1.45
    if scenario == "low_demand":
        return 0.75
    return 1.12


def demand_forecast(warehouse: Warehouse, days: int, scenario: DemandScenario) -> List[ForecastItem]:
    """
    Упрощённый прогноз спроса. В реальном проекте здесь может быть ML-модель.
    Для прототипа используется средний дневной спрос и сценарный коэффициент.
    """
    daily_average = {
        "phones": 18,
        "laptops": 6,
        "accessories": 55,
    }
    multiplier = scenario_multiplier(scenario)
    items: List[ForecastItem] = []

    for sku, stock in warehouse.stock.items():
        predicted = int(daily_average.get(sku, 5) * days * multiplier)
        remaining = stock - predicted
        if remaining < 0:
            status = "risk"
            recommendation = f"Пополнить склад минимум на {abs(remaining)} ед."
        elif stock < predicted * 1.3:
            status = "warning"
            recommendation = "Запас близок к минимальному, стоит подготовить поставку."
        else:
            status = "ok"
            recommendation = "Запаса достаточно."
        items.append(
            ForecastItem(
                sku=sku,
                current_stock=stock,
                predicted_demand=predicted,
                remaining_after_period=remaining,
                status=status,
                recommendation=recommendation,
            )
        )
    return items


def warehouse_load_percent(warehouse: Warehouse) -> float:
    return round(sum(warehouse.stock.values()) / warehouse.capacity_units * 100, 1)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "TransLogix", "version": app.version}


@app.get("/api/warehouses")
def get_warehouses() -> List[Dict[str, object]]:
    return [
        {
            **asdict(warehouse),
            "load_percent": warehouse_load_percent(warehouse),
        }
        for warehouse in WAREHOUSES
    ]


@app.get("/api/deliveries")
def get_deliveries() -> List[DeliveryPoint]:
    return DELIVERIES


@app.get("/api/dashboard")
def dashboard() -> Dict[str, object]:
    stock_units = sum(sum(warehouse.stock.values()) for warehouse in WAREHOUSES)
    high_priority = sum(1 for delivery in DELIVERIES if delivery.priority >= 3)
    return {
        "warehouses": len(WAREHOUSES),
        "delivery_points": len(DELIVERIES),
        "high_priority_deliveries": high_priority,
        "stock_units": stock_units,
        "average_warehouse_load_percent": round(
            sum(warehouse_load_percent(warehouse) for warehouse in WAREHOUSES) / len(WAREHOUSES), 1
        ),
        "recent_operations": OPERATION_HISTORY[:5],
    }


@app.post("/api/optimize-route", response_model=RouteResponse)
def optimize_route(request: RouteRequest) -> RouteResponse:
    start = perf_counter()
    warehouse = find_warehouse(request.warehouse_id)
    deliveries = select_deliveries(request.delivery_ids, request.strategy)

    if not deliveries:
        raise HTTPException(status_code=400, detail="Не выбраны точки доставки")

    route, total_distance = build_route(warehouse, deliveries, request.strategy)
    service_time_hours = sum(stop.demand_units for stop in route) / 240 + sum(
        delivery.service_minutes for delivery in deliveries
    ) / 60
    estimated_time = total_distance / 45 + service_time_hours
    fuel_cost = int(total_distance * 19.5)
    co2 = total_distance * 0.21
    priority_bonus = sum(stop.priority for stop in route) / (len(route) * 3)
    service_score = max(0.0, min(100.0, 100 - total_distance * 0.22 + priority_bonus * 9))

    result = RouteResponse(
        warehouse=warehouse.name,
        strategy=request.strategy,
        stops=route,
        total_distance_km=round(total_distance, 2),
        estimated_time_hours=round(estimated_time, 2),
        fuel_cost_rub=fuel_cost,
        co2_kg=round(co2, 2),
        service_score=round(service_score, 1),
        generated_in_ms=round((perf_counter() - start) * 1000, 2),
        insights=[
            RouteInsight(label="Главный критерий", value="приоритет + расстояние" if request.strategy != "nearest_first" else "минимальная дистанция"),
            RouteInsight(label="Срочных доставок", value=str(sum(1 for stop in route if stop.priority >= 3))),
            RouteInsight(label="Оценка маршрута", value="хорошая" if service_score >= 85 else "требует проверки"),
        ],
    )
    remember(
        "route_optimization",
        {
            "warehouse": warehouse.name,
            "strategy": request.strategy,
            "distance_km": result.total_distance_km,
            "stops": len(result.stops),
        },
    )
    return result


@app.post("/api/inventory/forecast", response_model=ForecastResponse)
def forecast_inventory(request: ForecastRequest) -> ForecastResponse:
    warehouse = find_warehouse(request.warehouse_id)
    items = demand_forecast(warehouse, request.days, request.scenario)
    risk_items = sum(1 for item in items if item.status == "risk")
    warning_items = sum(1 for item in items if item.status == "warning")
    replenish_units = sum(max(0, -item.remaining_after_period) for item in items)
    status = "risk" if risk_items else "warning" if warning_items else "ok"

    result = ForecastResponse(
        warehouse=warehouse.name,
        days=request.days,
        scenario=request.scenario,
        items=items,
        summary={
            "status": status,
            "risk_items": risk_items,
            "warning_items": warning_items,
            "recommended_replenishment_units": replenish_units,
        },
    )
    remember(
        "inventory_forecast",
        {
            "warehouse": warehouse.name,
            "days": request.days,
            "scenario": request.scenario,
            "status": status,
        },
    )
    return result


@app.get("/api/alerts")
def alerts() -> Dict[str, object]:
    result = []
    for warehouse in WAREHOUSES:
        forecast_items = demand_forecast(warehouse, 14, "normal")
        for item in forecast_items:
            if item.status in {"warning", "risk"}:
                result.append(
                    {
                        "warehouse": warehouse.name,
                        "sku": item.sku,
                        "status": item.status,
                        "message": item.recommendation,
                    }
                )
    return {"alerts": result, "count": len(result)}


@app.get("/api/history")
def history() -> List[Dict[str, str | float | int]]:
    return OPERATION_HISTORY


@app.get("/api/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    return MetricsResponse(
        status="ok",
        warehouses=len(WAREHOUSES),
        delivery_points=len(DELIVERIES),
        history_records=len(OPERATION_HISTORY),
        memory_mb=round(memory_mb, 2),
        cpu_percent=psutil.cpu_percent(interval=0.05),
    )

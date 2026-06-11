from pathlib import Path

from fastapi import Query
from fastapi_pagination import Page
from fastapi_pagination.customization import CustomizedPage, UseParamsFields, UseFieldsAliases
from pydantic import BaseModel

from app.rpc_client.gen.python.calculator.v1 import calculator_pb2
from app.rpc_client.gen.python.calculator.v1.calculator_pb2 import City

BASE_DIR = Path(__file__).resolve().parent.parent.parent



def get_transportation_options(calculator) -> dict[str, City]:
    """Index transportation options by name, keeping only valid prices."""
    return {
        entry.name: entry
        for entry in getattr(calculator, "transportation_price", [])
        if entry.name and entry.price > 0
    }


def get_ocean_options(calculator) -> dict[str, City]:
    """Index ocean shipping options by name, keeping only valid prices."""
    return {
        entry.name: entry
        for entry in getattr(calculator, "ocean_ship", [])
        if entry.name and entry.price > 0
    }


def get_cheapest_terminal_prices(calculator: calculator_pb2.DefaultCalculator) -> tuple[City, City] | None:
    """
    Returns (transportation_city, ocean_city) for the cheapest transportation + ocean combo.
    Ignores entries that miss either component.
    """
    transportation_options = get_transportation_options(calculator)
    ocean_options = get_ocean_options(calculator)

    cheapest_pair: tuple[City, City] | None = None
    cheapest_total: float | None = None

    for name, transportation_city in transportation_options.items():
        ocean_city = ocean_options.get(name)
        if ocean_city is None:
            continue

        total = transportation_city.price + ocean_city.price
        if cheapest_total is None or total < cheapest_total:
            cheapest_pair = (transportation_city, ocean_city)
            cheapest_total = total

    return cheapest_pair


def get_calculator(
    response: calculator_pb2.GetCalculatorWithDataResponse,
    currency: str = "USD",
) -> calculator_pb2.CalculatorOut | None:

    currency = currency.upper()

    if not response.HasField("data"):
        return None

    if currency == "USD":
        return response.data.calculator_in_dollars

    if not response.data.calculators_in_currencies:
        return None

    for calculator in response.data.calculators_in_currencies:
        if calculator.currency == currency:
            return calculator

    return None


def round_calculator_amount(value: float) -> int:
    return int(round(value))


def create_pagination_page(pydantic_model: type[BaseModel])-> type[Page[BaseModel]]:
    return CustomizedPage[
        Page[pydantic_model],
        UseParamsFields(size=Query(5, ge=1, le=1000)),
        UseFieldsAliases(
            items="data",
            total='count'
        )
    ]

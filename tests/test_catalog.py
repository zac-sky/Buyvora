from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.catalog_seed import demo_catalog
from app.domain.catalog import Money, Product, Sku
from app.main import app
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.catalog_service import CatalogQuery, CatalogService

client = TestClient(app)


def test_search_combines_keyword_budget_and_stock() -> None:
    response = client.get("/commerce/products", params={"q": "耳机", "max_price": "300"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "demo"
    assert body["total"] == 2
    assert [p["id"] for p in body["items"]] == ["demo-headphones-02", "demo-headphones-01"]
    assert {sku["id"] for p in body["items"] for sku in p["skus"]} == {"hp01-black", "hp02-white"}


def test_price_boundary_uses_exact_minor_units() -> None:
    below = client.get("/commerce/products", params={"q": "耳机", "max_price": "159.89"})
    exact = client.get("/commerce/products", params={"q": "耳机", "min_price": "159.90", "max_price": "159.90"})
    assert below.json()["total"] == 0
    assert exact.json()["total"] == 1
    assert exact.json()["items"][0]["skus"][0]["price"] == {"amount_minor": 15990, "currency": "CNY"}


def test_search_supports_all_terms_and_casefold() -> None:
    response = client.get("/commerce/products", params={"q": "  HEADPHONES 黑色  "})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [sku["id"] for sku in response.json()["items"][0]["skus"]] == ["hp01-black"]


def test_category_and_stock_filters() -> None:
    hidden = client.get("/commerce/products", params={"category": "hubs"})
    visible = client.get("/commerce/products", params={"category": "hubs", "in_stock": "false"})
    assert hidden.json()["total"] == 0
    assert visible.json()["total"] == 1
    assert visible.json()["items"][0]["skus"][0]["stock"] == 0


def test_search_does_not_mutate_full_catalog() -> None:
    filtered = client.get("/commerce/products", params={"q": "降噪", "max_price": "300"})
    detail = client.get("/commerce/products/demo-headphones-01")
    assert len(filtered.json()["items"][0]["skus"]) == 1
    assert detail.status_code == 200
    assert len(detail.json()["skus"]) == 2
    assert detail.json()["skus"][1]["stock"] == 0


def test_unknown_product_and_no_matches_are_distinct() -> None:
    assert client.get("/commerce/products/missing").status_code == 404
    response = client.get("/commerce/products", params={"q": "火星飞船"})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_pagination_has_stable_order_and_total() -> None:
    all_items = client.get("/commerce/products").json()
    first = client.get("/commerce/products", params={"limit": 2}).json()
    second = client.get("/commerce/products", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"] == all_items["total"] == 5
    assert first["items"] + second["items"] == all_items["items"][:4]
    assert client.get("/commerce/products", params={"offset": 100}).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"min_price": "-1"}, {"max_price": "-1"}, {"max_price": "1.001"},
    {"max_price": "NaN"}, {"max_price": "Infinity"}, {"max_price": "oops"},
    {"min_price": "300", "max_price": "100"}, {"max_price": "100000000"},
    {"limit": 0}, {"limit": 51}, {"offset": -1}, {"offset": 10001},
    {"category": "unknown"}, {"q": "a" * 201}, {"in_stock": "maybe"},
    {"unexpected": "value"},
])
def test_invalid_filters_return_422(params: dict) -> None:
    assert client.get("/commerce/products", params=params).status_code == 422


def test_whitespace_query_browses_catalog() -> None:
    assert client.get("/commerce/products", params={"q": "   "}).json()["total"] == 5


def test_filters_must_match_the_same_sku() -> None:
    product = Product(id="test", name="测试耳机", brand="Test", category="headphones",
                      description="", skus=(
        Sku(id="cheap", name="黑色", price=Money(amount_minor=10000), stock=0),
        Sku(id="costly", name="白色", price=Money(amount_minor=30000), stock=2),
    ))
    service = CatalogService(InMemoryCatalogRepository([product]))
    assert service.search(CatalogQuery(max_price=Decimal("200"))).total == 0
    assert service.search(CatalogQuery(q="黑色")).total == 0
    assert service.search(CatalogQuery(q="黑色", in_stock=False)).total == 1
    assert len(service.repository.get("test").skus) == 2


@pytest.mark.parametrize("amount", [-1, 1.5, True, "1990"])
def test_money_rejects_invalid_minor_units(amount: object) -> None:
    with pytest.raises(ValidationError):
        Money(amount_minor=amount)


def test_catalog_objects_are_immutable() -> None:
    product = demo_catalog()[0]
    with pytest.raises(ValidationError):
        product.skus[0].stock = 0
    with pytest.raises(ValidationError):
        product.skus[0].price.amount_minor = 1


def test_product_requires_unique_skus_and_nonnegative_stock() -> None:
    sku = Sku(id="sku", name="黑色", price=Money(amount_minor=100), stock=1)
    with pytest.raises(ValidationError):
        Product(id="p", name="耳机", brand="Test", category="headphones", description="", skus=(sku, sku))
    with pytest.raises(ValidationError):
        Sku(id="sku", name="黑色", price=Money(amount_minor=100), stock=-1)
    with pytest.raises(ValidationError):
        Product(id="p", name="耳机", brand="Test", category="headphones", description="", skus=())


def test_repository_rejects_duplicate_product_and_global_sku_ids() -> None:
    product = demo_catalog()[0]
    with pytest.raises(ValueError, match="Duplicate product ID"):
        InMemoryCatalogRepository([product, product])
    with pytest.raises(ValueError, match="Duplicate SKU ID"):
        InMemoryCatalogRepository([product, product.model_copy(update={"id": "different"})])

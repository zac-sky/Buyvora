import pytest

from app.agent.tools import ShoppingTools
from app.catalog_seed import demo_catalog
from app.repositories.catalog import InMemoryCatalogRepository
from app.services.catalog_service import CatalogService
from tests.fakes import tool_reply


def execute(name="search_products", arguments="{}"):
    tools = ShoppingTools(CatalogService(InMemoryCatalogRepository(demo_catalog())))
    return tools.execute(tool_reply(name=name, arguments=arguments).tool_calls[0])


@pytest.mark.parametrize("arguments", ['not json', '[]', 'null', '{"max_price":-1}',
    '{"limit":11}', '{"category":"invalid"}', '{"min_price":300,"max_price":100}', '{"extra":"field"}'])
def test_tool_arguments_are_validated(arguments):
    result = execute(arguments=arguments)
    assert not result.ok
    assert result.result["error"]["code"] == "invalid_arguments"


def test_unknown_tools_are_not_executed():
    result = execute(name="place_order", arguments='{"sku_id":"hp01-black"}')
    assert not result.ok
    assert result.result["error"]["code"] == "unknown_tool"


def test_get_product_uses_catalog_and_reports_missing():
    known = execute("get_product", '{"product_id":"demo-headphones-01"}')
    missing = execute("get_product", '{"product_id":"missing"}')
    assert known.ok
    assert len(known.result["product"]["skus"]) == 2
    assert not missing.ok
    assert missing.result["error"]["code"] == "product_not_found"


def test_deeply_nested_arguments_return_controlled_error():
    result = execute(arguments='[' * 1100 + '0' + ']' * 1100)
    assert not result.ok
    assert result.result["error"]["code"] == "invalid_arguments"


def test_tool_schema_and_executor_agree_on_result_limit():
    tools = ShoppingTools(CatalogService(InMemoryCatalogRepository(demo_catalog())))
    assert tools.definitions()[0]["function"]["parameters"]["properties"]["limit"]["maximum"] == 10

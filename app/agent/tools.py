"""An explicit read-only allowlist; generated arguments are untrusted input."""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.model import ToolCall
from app.services.catalog_service import CatalogQuery, CatalogService


class ProductQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str = Field(min_length=1, max_length=100)


class ToolTrace(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    result: dict[str, Any]


class ShoppingTools:
    def __init__(self, catalog: CatalogService) -> None:
        self.catalog = catalog

    def definitions(self) -> list[dict]:
        search_schema = CatalogQuery.model_json_schema()
        search_schema["properties"]["limit"]["maximum"] = 10
        return [
            {"type": "function", "function": {
                "name": "search_products",
                "description": "搜索虚构演示商品。q 用短关键词而非完整句子；max_price/min_price 为人民币元，"
                               "最多两位小数；默认只含现货。必须保留用户的预算和品类约束。",
                "parameters": search_schema,
            }},
            {"type": "function", "function": {
                "name": "get_product",
                "description": "用搜索返回的 product_id 查询虚构商品的全部 SKU、价格和库存。",
                "parameters": ProductQuery.model_json_schema(),
            }},
        ]

    def execute(self, call: ToolCall) -> ToolTrace:
        name = call.function.name
        arguments: dict = {}
        ok = False
        if name not in {"search_products", "get_product"}:
            result = {"error": {"code": "unknown_tool", "message": "该工具不可用，请使用已提供的只读商品工具。"}}
        else:
            try:
                raw = json.loads(call.function.arguments)
                if name == "search_products":
                    query = CatalogQuery.model_validate(raw)
                    if query.limit > 10:
                        raise ValueError("Tool search permits at most 10 products")
                    arguments = query.model_dump(mode="json", exclude_defaults=True)
                    result = self.catalog.search(query).model_dump(mode="json")
                    ok = True
                else:
                    query = ProductQuery.model_validate(raw)
                    arguments = query.model_dump()
                    product = self.catalog.repository.get(query.product_id)
                    if product is None:
                        result = {"error": {"code": "product_not_found", "message": "商品不存在，请重新搜索。"}}
                    else:
                        result = {"product": product.model_dump(mode="json"), "source": "demo"}
                        ok = True
            except (ValueError, TypeError, RecursionError, ValidationError):
                result = {"error": {"code": "invalid_arguments", "message":
                    "参数无效：请检查 JSON 对象、预算范围、品类和 limit（最多 10）。仅使用工具定义中的字段。"}}
        return ToolTrace(call_id=call.id, name=name, arguments=arguments, ok=ok, result=result)

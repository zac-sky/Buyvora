"""Commerce types independent of HTTP and model providers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["headphones", "keyboards", "mice", "hubs", "monitors"]


class Money(BaseModel):
    """Store CNY in integer minor units: 12990 means 129.90 yuan."""

    model_config = ConfigDict(frozen=True)
    amount_minor: int = Field(ge=0, strict=True)
    currency: Literal["CNY"] = "CNY"


class Sku(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: Money
    stock: int = Field(ge=0, strict=True)


class Product(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    category: Category
    description: str
    tags: tuple[str, ...] = ()
    skus: tuple[Sku, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sku_ids(self) -> "Product":
        ids = [sku.id for sku in self.skus]
        if len(ids) != len(set(ids)):
            raise ValueError("SKU IDs must be unique within a product")
        return self

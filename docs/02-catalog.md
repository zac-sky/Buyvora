# 第 2 课：商品、SKU、仓储与搜索

本阶段让系统能够查询具体的商品数据。所有商品、价格和库存都是本项目编写的虚构演示数据；还没有对接真实商家，也没有接入大模型。

## 先理解四个组件

| 组件 | 作用 | 代码入口 |
| --- | --- | --- |
| 领域模型 | 规定商品、规格、金额和库存长什么样 | `app/domain/catalog.py` |
| 仓储 | 负责取出商品，不负责理解用户意图 | `app/repositories/catalog.py` |
| 搜索服务 | 同时应用关键词、品类、预算、库存条件 | `app/services/catalog_service.py` |
| API 路由 | 将 HTTP 参数转换成模型，再调用服务 | `app/routes/catalog.py` |

**Product 与 SKU**：一款耳机是商品；同款耳机的黑色版和白色版是两个 SKU，它们可以有不同价格和库存。下单最终要选具体 SKU。

**Money**：内部使用整数“分”，例如 `15990` 表示人民币 `159.90` 元。请求中的价格上限用“元”，通过 Decimal 精确换算。当前仅支持 CNY，后续汇率功能另行实现。

**Repository**：仓储隐藏数据放在哪里。当前是内存列表；后续可以实现数据库仓储，只要继续提供 `list_all()` 和 `get()`。`Protocol` 描述这个约定，搜索服务只依赖约定。

**Service**：搜索规则独立于 FastAPI。今后 Agent 的 `search_products` 工具可以调用同一服务，不必再实现一套预算和库存逻辑。

## 用接口亲自验证

启动服务后打开 http://127.0.0.1:8000/docs，在 `GET /commerce/products` 中设置：

- `q`：`耳机`
- `max_price`：`300`
- `in_stock`：`true`

结果应该包含“轻听 Air 无线耳机”和“静听 Pro 降噪耳机”的黑色 SKU。前者 159.90 元，后者 299 元。

也可以直接打开：

http://127.0.0.1:8000/commerce/products?q=耳机&max_price=300

返回值含 `source: "demo"`；`total` 是分页前符合条件的商品数。搜索结果中的 `skus` **只包含符合本次条件的规格**。访问 `/commerce/products/demo-headphones-01` 可查看完整规格，包括已售罄的白色版。

## 当前搜索规则

- 关键词匹配名称、品牌、描述、标签、品类和 SKU 名称；英文忽略大小写。
- 空格分隔的多个关键词必须全部匹配，例如 `HEADPHONES 黑色`。
- `q` 留空或只有空白时浏览目录；不会解析整句自然语言，意图理解留给下一阶段的模型。
- `category` 可选 `headphones`、`keyboards`、`mice`、`hubs`、`monitors`。
- `min_price` 和 `max_price` 都是元，包含边界，最多两位小数。
- 默认只返回有库存的 SKU；`in_stock=false` 包含售罄规格。
- 关键词、价格和库存必须由同一个 SKU 同时满足。
- 按符合条件的最低 SKU 价格升序，价格相同时按商品 ID 排序。
- `limit` 为 1–50，`offset` 为 0–10000；搜索无结果返回空列表，详情 ID 不存在返回 404。

## 为什么要有这些测试

`tests/test_catalog.py` 检查 159.89 元预算不能买到 159.90 元商品、售罄的低价规格不能使高价现货通过筛选，以及一次搜索不能改变完整商品目录。

这是 Agent 项目的基础：模型负责决定调用什么工具，确定性的业务代码负责金额、库存等规则。

运行全部测试：

```powershell
uv run pytest -q
```

## 你的练习

在 `app/catalog_seed.py` 中新增一款虚构商品，给它两个 SKU，设置一个售罄。然后使用 API 验证关键词、预算和库存筛选。

提交自己的练习：

```powershell
git status
git diff
uv run pytest -q
git add app/catalog_seed.py
git diff --cached
git commit -m "feat: add my first demo product"
git push
```

这样 GitHub 会留下你亲自理解并修改商品组件的独立提交。下一阶段学习：模型如何将购物需求转成工具参数，以及如何根据工具结果组织推荐。

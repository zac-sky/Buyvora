# Buyvora Agent

Buyvora 是一个由个人独立开发的电商 Agent 项目。它的目标是让用户用自然语言表达购物需求，Agent 逐步完成需求理解、商品搜索、比较推荐，并在后续阶段扩展到价格计算、用户偏好记忆和订单操作。

## 当前进度

当前已实现工程基础、商品搜索与模型工具调用，真实模型联调待配置后验证：

- Python 项目依赖配置
- FastAPI 服务入口
- 健康检查接口 `GET /health`
- 购物对话接口 `POST /commerce/chat`，接入可配置的 Chat Completions 兼容模型
- 商品搜索 / 详情工具、调用限制、可查看的工具记录与内存多轮会话
- 商品 / SKU / 金额模型与 6 款虚构演示商品
- 商品搜索与详情接口（关键词、预算、库存、分页）
- 请求校验和自动化测试
- 面向学习的迭代路线

## 本地运行

```powershell
uv sync --locked
# 购物对话需要先复制 .env.example 为 .env，填入模型配置
uv run uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/health>，应看到：

```json
{"status":"ok","service":"buyvora-agent"}
```

运行测试：

```powershell
uv run pytest
```

## 商品搜索

打开 http://127.0.0.1:8000/docs 可交互调用接口：

- `GET /commerce/products?q=耳机&max_price=300`：搜索 300 元以内有库存的耳机。
- `GET /commerce/products/demo-headphones-01`：查看商品的全部规格。
- `POST /commerce/chat`：模型根据需求调用商品工具并组织回复；首次请求不传 session_id。
- `GET /ready`：查看模型配置是否齐全（不代表已经连通模型服务）。

商品、价格和库存均为虚构演示数据。搜索返回 `source: "demo"`，金额以整数分表示，搜索预算参数以元表示。当前没有真实商家或订单执行。模型调用需要本地配置，未配置时明确返回 503。会话仅在单进程内存中保存，尚未提供账号鉴权，不宜直接公开部署。

学习笔记：[第 1 课：对话与 Git](docs/01-chat-and-git.md) · [第 2 课：商品与搜索](docs/02-catalog.md) · [第 3 课：Agent 与工具](docs/03-agent-and-tools.md)。

验证：`uv run pytest -q`；协议闭环：`uv run python scripts/smoke_agent.py`；配置真实模型后：`uv run python scripts/smoke_agent.py --live`。后者会消耗模型额度。[实际验证记录](docs/verification.md)。

## 项目路线

详细的学习和开发步骤见 [docs/learning-roadmap.md](docs/learning-roadmap.md)。每完成一个小阶段，就进行一次独立提交，让项目进展和学习成果都能在 GitHub 中清晰呈现。

## GitHub 提交方式

仓库已关联 [zac-sky/Buyvora](https://github.com/zac-sky/Buyvora)，无需重复初始化。

每次修改后先检查，再选择文件提交：

```powershell
git status
git diff
git add app tests docs README.md .gitignore uv.lock
git diff --cached
git commit -m "feat: describe the completed change"
git push
```

`commit` 记录本地版本，`push` 上传 GitHub。逐步讲解和练习见 [第 1 课：对话接口与 Git](docs/01-chat-and-git.md)。

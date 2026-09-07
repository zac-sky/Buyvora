# 第 1 课：从一次请求理解后端

本阶段完成 `POST /commerce/chat`，使用明确的固定回复验证请求流程。它还没有接入大模型，也没有保存对话；`session_id` 目前只是原样返回的会话标识。

## 请求经过了什么

浏览器或 API 客户端 → FastAPI 路由 → Pydantic 请求模型 → service 业务函数 → 响应模型 → JSON。

- `app/main.py`：路由负责接收 HTTP 请求并调用业务函数。
- `app/schemas.py`：约定输入输出格式。`Field` 限制长度；`field_validator` 在长度检查前去掉首尾空白，所以空格也会被判为无效输入。
- `app/services/chat_service.py`：业务逻辑单独存放，以后可以替换成 Agent 调用。
- `tests/test_chat.py`：自动模拟请求，检查正常回复、空白输入、长度上限和会话标识。

`422` 表示请求内容未通过校验；`200` 表示本次请求成功。校验失败时，业务函数不会执行。

## 动手运行

在项目目录打开 PowerShell：

```powershell
uv sync --locked
uv run uvicorn app.main:app --reload
```

打开 http://127.0.0.1:8000/docs，展开 `POST /commerce/chat`，点击 Try it out，输入：

```json
{"session_id": "my-first-session", "message": "我想买一副降噪耳机"}
```

点击 Execute 观察回复，再将 message 改成两个空格，观察 422 响应。试着解释：为什么 `min_length=1` 本身不能阻止空格输入？

另开终端运行测试：

```powershell
uv run pytest -q
```

## Git 与 GitHub 的区别

Git 管理电脑里的版本；GitHub 保存远程副本。修改文件并不会自动上传。

1. `git status` 查看哪些文件改了。
2. `git diff` 阅读尚未暂存的改动。
3. `git add <文件路径>` 选择本次要记录的文件，放进暂存区。
4. `git diff --cached` 检查即将提交的内容。
5. `git commit -m "feat: add validated shopping chat endpoint"` 创建本地提交。
6. `git push` 将本地提交上传到已关联的 GitHub 仓库。

本项目已经初始化，并且 origin 已指向 `https://github.com/zac-sky/Buyvora.git`，无需重复执行 `git init` 或 `git remote add origin`。用 `git log --oneline -5` 查看最近的提交。

`uv.lock` 应随依赖配置提交，方便复现环境。`.venv`、`.uv-cache` 和含密钥的 `.env` 不应提交。不要把示例里的 `<文件路径>` 原样执行，应换成实际路径。

## 面试表达

这个阶段可解释“请求校验和业务逻辑分离”，还不能声称实现了智能购物推荐。后面的阶段会为 Agent 增加真实商品数据和工具调用。

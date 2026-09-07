# Buyvora Agent

Buyvora 是一个由个人独立开发的电商 Agent 项目。它的目标是让用户用自然语言表达购物需求，Agent 逐步完成需求理解、商品搜索、比较推荐，并在后续阶段扩展到价格计算、用户偏好记忆和订单操作。

## 当前进度

当前已完成工程基础和购物对话接口，已经包含：

- Python 项目依赖配置
- FastAPI 服务入口
- 健康检查接口 `GET /health`
- 购物对话接口 `POST /commerce/chat`（固定回复，尚未接入大模型）
- 请求校验和自动化测试
- 面向学习的迭代路线

## 本地运行

```powershell
uv sync
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

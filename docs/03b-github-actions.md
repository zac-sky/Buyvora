# 补充课：GitHub 自动检查你的提交

Git 保存每一步改动，GitHub Actions 则在推送后自动运行检查。这样你能判断：新改动有没有破坏之前完成的功能。

## 当前自动检查做什么

配置文件是 `.github/workflows/tests.yml`。每次推送到 main、创建 Pull Request，或者在网页手动运行时，会：

1. 取出本次提交的代码。
2. 安装固定版本的 uv 和指定 Python。
3. 使用 `uv.lock` 安装依赖，锁文件不一致时失败。
4. 运行全部自动化测试。
5. 启动应用和本地协议测试服务，验证两轮 HTTP 购物对话。

运行环境是 Linux 的 Python 3.11、3.12，以及 Windows 的 Python 3.13。这样既覆盖项目声明的 Python 范围，也检查你本地 Windows 与常见 Linux 部署环境的差异。

Actions 只使用协议测试服务，**没有配置真实模型 Key，也不会请求付费模型**。绿色结果证明代码、依赖和测试链路通过，不证明真实模型推荐质量。

## 如何看结果

打开仓库 https://github.com/zac-sky/Buyvora ，点击 Actions，再点对应提交的 Tests。

- 绿色：该提交的所有任务通过。
- 红色：进入失败任务，找到失败步骤，阅读具体错误。
- 黄色或正在转圈：仍在执行，不能提前当作通过。

注意核对提交号：旧提交通过不代表新提交也通过。

## 失败后怎样修复

先在本地复现：

```powershell
uv run pytest -q
uv run python scripts/smoke_agent.py
```

理解错误并修改后，创建一次新的修复提交：

```powershell
git status
git diff
git add 修改的文件路径
git diff --cached
git commit -m "fix: correct the failing behavior"
git push
```

把“修改的文件路径”替换成实际文件。GitHub 会自动检查新提交。不要仅为了出现绿色而删除发现真实问题的测试。

## 设计取舍

第三方 Actions 固定到具体提交，uv 固定到已经验证的版本，Python 与包依赖通过配置和锁文件确定。升级时也应形成独立提交并重新检查。

这是持续集成（CI），还没有自动部署（CD）。自动发布服务会在前端、账号边界和部署阶段完成后再加入。

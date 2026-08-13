# Browser Use 集成说明

Browser Use 作为可选的自治浏览器 Agent 运行时，不与 QuestRAG 主 Python 环境混装。当前项目的 `deepagents` 与 Browser Use 的 Anthropic 版本约束冲突，生产部署应使用独立 worker 环境。

## Worker 环境

```powershell
uv venv .browser-use-venv --python 3.12
.\.browser-use-venv\Scripts\Activate.ps1
uv pip install "browser-use[core]"
uv run playwright install chromium
```

Worker 接收 `{session_id, url, task, max_steps}`，使用 Browser Use 的 Agent API 执行任务，并回传 `{status, result, events}`。QuestRAG 通过 `browser_use_runtime` 作为适配层调用它；未配置 worker 或模型凭证时，系统继续使用 Playwright 模式。

## 选择原则

- 固定业务表单：优先 Playwright 结构化操作。
- 页面变化大、需要自治规划：使用 Browser Use worker。
- 登录、验证码、承诺和最终提交：必须保留人工接管。

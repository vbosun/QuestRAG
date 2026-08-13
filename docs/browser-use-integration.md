# Browser Use 集成说明

Browser Use 作为可选的自治浏览器 Agent 运行时，不与 QuestRAG 主 Python 环境混装。当前项目的 `deepagents` 与 Browser Use 的 Anthropic 版本约束冲突，生产部署应使用独立 worker 环境。

## Worker 环境

```powershell
Set-Location browser_use_worker
uv venv .browser-use-venv --python 3.12
.\.browser-use-venv\Scripts\Activate.ps1
uv pip install -e .
$env:OPENAI_API_KEY="你的模型密钥"
uvicorn app:app --host 127.0.0.1 --port 8090
```

然后以 `BROWSER_USE_WORKER_URL=http://127.0.0.1:8090` 启动 QuestRAG 主服务，并在“检索配置 → 申请页面执行模式”选择 Browser Use。

Worker 接收 `{session_id, url, task, max_steps}` 后立即返回任务标识。通过 `GET /tasks/{task_id}` 查询
`queued/running/completed/failed/cancelled` 和事件记录，`DELETE /tasks/{task_id}` 可取消。QuestRAG 通过
`browser_use_runtime` 作为适配层调用它；未配置 worker 或模型凭证时会返回明确的不可用原因，嵌入页面仍可供用户继续操作。

## 选择原则

- 固定业务表单：优先嵌入页面 + 表单 schema 映射。
- 页面变化大、需要自治规划：使用 Browser Use worker。
- 登录、验证码、承诺和最终提交：必须保留人工接管。

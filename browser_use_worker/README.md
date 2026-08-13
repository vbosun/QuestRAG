# Browser Use Worker

独立运行 Browser Use，避免和 QuestRAG 主环境的 LangChain/Anthropic 依赖冲突。

```powershell
uv venv .browser-use-venv --python 3.12
.\.browser-use-venv\Scripts\Activate.ps1
uv pip install -e .
$env:OPENAI_API_KEY="你的模型密钥"
uvicorn app:app --host 127.0.0.1 --port 8090
```

新版 Browser Use 由自身的浏览器运行时启动本机 Chrome；不需要、也不应执行
`playwright install chromium`。首次任务会完成所需的浏览器连接准备。

健康检查：`GET http://127.0.0.1:8090/health`

任务接口：`POST http://127.0.0.1:8090/tasks`

创建任务立即返回 `202`；随后通过 `GET /tasks/{task_id}` 获取
`queued`、`running`、`completed`、`failed` 或 `cancelled` 状态。使用
`DELETE /tasks/{task_id}` 可停止尚未完成的任务。

```json
{
  "session_id": "demo-1",
  "url": "http://127.0.0.1:8020/employment-registration/apply",
  "task": "填写联系电话 18733333333，选择单位就业，不要提交",
  "max_steps": 20
}
```

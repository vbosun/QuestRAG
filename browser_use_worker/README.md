# Browser Use Worker

独立运行 Browser Use，避免和 QuestRAG 主环境的 LangChain/Anthropic 依赖冲突。

```powershell
uv venv .browser-use-venv --python 3.12
.\.browser-use-venv\Scripts\Activate.ps1
uv pip install "browser-use[core]" fastapi uvicorn
uv run playwright install chromium
$env:OPENAI_API_KEY="你的模型密钥"
uv run uvicorn browser_use_worker.app:app --host 127.0.0.1 --port 8090
```

健康检查：`GET http://127.0.0.1:8090/health`

任务接口：`POST http://127.0.0.1:8090/tasks`

```json
{
  "session_id": "demo-1",
  "url": "http://127.0.0.1:8020/employment-registration/apply",
  "task": "填写联系电话 18733333333，选择单位就业，不要提交",
  "max_steps": 20
}
```

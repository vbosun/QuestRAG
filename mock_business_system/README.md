# 模拟业务系统

这是独立于 QuestRAG 的外部业务系统，用来验证 Agent 的 GUI 浏览器能力。

启动：

```powershell
uv run uvicorn mock_business_system.app:app --host 127.0.0.1 --port 8020
```

浏览器入口：`http://127.0.0.1:8020/employment-registration/apply`

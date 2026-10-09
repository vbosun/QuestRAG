# Browser Use Worker

独立运行 Browser Use，避免和 QuestRAG 主环境的 LangChain/Anthropic 依赖冲突。

```powershell
uv venv .browser-use-venv --python 3.12
.\.browser-use-venv\Scripts\Activate.ps1
uv pip install -r browser_use_worker/pyproject.toml
$env:OPENAI_API_KEY="你的模型密钥"
uvicorn browser_use_worker.app:app --host 127.0.0.1 --port 8090
```

以上命令在项目根目录执行。Playwright 仅通过本机 CDP 连接 Browser Use 已启动的
Chromium，负责画面采集和人工接管；不会另开第二个浏览器，也不下载另一套 Chromium。

新版 Browser Use 由自身的浏览器运行时启动本机 Chrome；不需要、也不应执行
`playwright install chromium`。首次任务会完成所需的浏览器连接准备。

健康检查：`GET http://127.0.0.1:8090/health`

任务接口：`POST http://127.0.0.1:8090/tasks`

创建任务立即返回 `202`；随后通过 `GET /tasks/{task_id}` 获取
`queued`、`running`、`completed`、`failed` 或 `cancelled` 状态。使用
`DELETE /tasks/{task_id}` 可停止尚未完成的任务。

任务画面随状态返回 `live_frame`（JPEG、实际视口尺寸、操作目标和 AI 指针位置）。
高亮来自真实页面的 focus/input/change/click 事件，指针位置按实际字段坐标显示。
`DELETE /tasks/{task_id}` 等待 Agent 停止后将 `control` 交给用户，保留同一个页面。
`POST /tasks/{task_id}/action` 支持点击、文本、按键和滚动；运行中的任务拒绝人工操作。
点击业务页面文件按钮后，用 `POST /tasks/{task_id}/upload` 将不超过 10MB 的材料
传入原页面的 file chooser。worker 只在内部网络开放，外部请求须经后端申请归属和权限检查。

同一 session 重开复用页面。最多保留两个浏览器；空闲会话默认 15 分钟释放
（`BROWSER_SESSION_TTL_SECONDS`），新任务满额时释放已停止的旧会话。进程重启、
过期或被回收会丢失未提交页面状态，不能当作持久草稿。最终提交仍由用户决定。

```json
{
  "session_id": "demo-1",
  "url": "http://127.0.0.1:8020/employment-registration/apply",
  "task": "填写联系电话 18733333333，选择单位就业，不要提交",
  "max_steps": 20
}
```

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
Chromium，负责字段回读、操作目标事件，以及 live 模式的画面采集和人工接管；不会另开第二个后台浏览器。

新版 Browser Use 由自身的浏览器运行时启动本机 Chrome；不需要、也不应执行
`playwright install chromium`。首次任务会完成所需的浏览器连接准备。

健康检查：`GET http://127.0.0.1:8090/health`

任务接口：`POST http://127.0.0.1:8090/tasks`

创建任务立即返回 `202`；随后通过 `GET /tasks/{task_id}` 获取
`queued`、`running`、`completed`、`failed` 或 `cancelled` 状态。使用
`DELETE /tasks/{task_id}` 可停止尚未完成的任务。

任务支持 `presentation`：通用任务默认 `live`；办事弹窗使用 `iframe`。

`iframe` 模式的前台是用户浏览器中的原生业务表单，后台 Chromium 是另一页面。
状态返回有序 `operation_events`（sequence、action_id、phase、field_key、label）和
成功操作后的 `form_fields` 回读值；失败或取消不发布未确认值。字段按 name/id 定位，
不使用后台截图坐标。状态查询和接管不截图，结束/停止后释放后台 Chromium，
同 session 重开返回原任务确认值，避免再次运行 Agent。前台通过可信表单桥接回传文本值和
字段手动修改版本，有效的变化值保存到申请草稿；清空/未通过校验的编辑保留在后端内存快照。
重开可恢复当前后端进程缓存的文本，文件选择不保存。需要目标页面配合，不能直接用于任意第三方 iframe。

聊天 `fill_application_form(case_id, fields)` 一次提交最多 12 个明确字段。worker 请求带独立
`command_id`、`page_id`、`requested_fields`、`initial_fields`、`field_revisions`：相同 command_id
重试复用原任务，不同命令在旧任务结束后创建新任务，正在执行时返回 409。新浏览器在导航后
恢复当前前台基准值，恢复不算 AI 填写事件；模型只允许 input/select_dropdown 修改本次指定字段，
禁止其他写操作和跳离当前申请页面。前台持续订阅最新任务，序列去重及已退役任务隔离。
明确要求修改的字段仅在手动版本仍等于命令基准时接收真实回读，任务启动后新的人工修改优先，
并回报冲突。主聊天只报告启动；后台 completed 与实际 iframe 回执都匹配后才能报告填写成功。
页面关闭、已提交或超过 5 秒未收到心跳时拒绝聊天新任务；关闭会尝试停止当前任务。

办事 iframe 每轮允许最多 12 个动作，提示模型统一规划当前页的已知可编辑字段，再按页面顺序
逐项执行和回读；每个动作只操作一个字段，禁止脚本一次改完所有字段。动作间隔仍为 0.8 秒，
用于逐项展示真实操作，不包含模型等待。导航、页面切换或动作失败时 Browser Use 会中断
剩余动作并重新观察规划；联动字段和最后完成核对仍可能需要额外模型调用，不保证整项任务
只调用一次模型。通用 live 任务保持每轮一个动作。
每项成功后，真实回读值也附在工具结果及模型记忆中，便于模型直接完成核对，避免重新查找
已经成功填写的字段；失败动作不提供确认值。`evaluate` 在当前版本会终止队列，普通字段应优先
使用 `input`/`select_dropdown`，必须脚本处理的字段单独规划。

`live` 模式画面随状态返回 `live_frame`（JPEG、实际视口尺寸、操作目标和 AI 指针位置）。
高亮来自真实页面的 focus/input/change/click 事件，指针位置按实际字段坐标显示。
`DELETE /tasks/{task_id}` 等待 Agent 停止后将 `control` 交给用户，保留同一个页面。
`POST /tasks/{task_id}/action` 支持点击、文本、按键和滚动；运行中的任务拒绝人工操作。
点击业务页面文件按钮后，用 `POST /tasks/{task_id}/upload` 将不超过 10MB 的材料
传入原页面的 file chooser。worker 只在内部网络开放，外部请求须经后端申请归属和权限检查。

`live` 模式同一 session 重开复用页面。最多保留两个浏览器；空闲会话默认 15 分钟释放
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

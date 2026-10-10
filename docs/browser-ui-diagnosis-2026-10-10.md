# 浏览器办事清晰度与速度排查

2026 年 10 月 10 日，针对业务弹窗文字模糊、AI 填写等待时间长、人工接管输入和滚动迟钝进行排查。当前执行和展示链路都有可定位的开销：逐步模型规划拖慢填写，JPEG 截图和串行请求拖慢人工操作。优先优化现有链路，再按是否需要本地部署、是否必须嵌入聊天窗口选择浏览器组件。

## 当前部署证据

通过 SSH 只读检查局域网 Linux 部署。运行中的 worker 的 `app.py`、`live_browser.py`、`deepseek_llm.py` 与本地源码 SHA256 相同。四个应用容器正在运行，backend、worker、web 的健康检查通过。健康检查不能证明交互性能。

worker 实际使用官方 `api.deepseek.com`，配置模型名为 `deepseek-v4-flash`，视觉模式关闭，结构化兼容配置为 JSON Object；最大并发为 1，任务容量为 4，任务超时为 300 秒。

最近一组日志记录了 9 个步骤的开始时间，前 8 个相邻步骤间隔为 3.97、9.62、7.15、13.40、4.55、4.59、3.47、4.79 秒，合计约 51.5 秒。这是从第 1 步开始到第 9 步开始的时间，包含页面观察、模型请求和动作执行，不是纯模型延迟或完整任务耗时，也不能认定就是用户截图对应的任务。

对已有 completed 会话，间隔约 500ms 读取 worker 状态 5 次。请求耗时为 94.0、128.5、142.7、121.9、138.7ms，中位数 128.5ms；画面均为 1280×900，Base64 图像约 76036 字节，无画面错误。测量包含 worker 获取页面、采集截图和序列化，不包括用户端网络、QuestRAG 后端转发和图像解码。未操作或提交该会话的表单。

## 模糊的来源

`browser_use_worker/live_browser.py` 的 `capture` 使用 `page.screenshot(type="jpeg", quality=70)`；`BrowserUseSurface.tsx` 将图像放在 `<img>` 中，CSS 将宽度设置为容器的 100%。用户看到的是远端页面的压缩位图。

JPEG 压缩会损伤文字和细线边缘；1280 像素画面随弹窗宽度进行非整数缩放，又会重新采样。截图没有按用户设备像素比协商分辨率，在高 DPI 屏幕上也可能显得偏软。用户设备 DPI 和实际显示缩放未测量，因此后两项的具体影响仍需对照验证。

短期可用 PNG 或无损 WebP 验证清晰度，并让远端视口适配展示容器，提供原始比例或全屏显示。高质量 JPEG 只能减轻压缩问题；无损截图仍不能解决低帧率和人工事件排队。

## AI 填写慢的来源

`browser_use_worker/app.py` 将 `max_actions_per_step` 固定为 1，并设置 `wait_between_actions=.8`。多个已确认字段也只能逐步规划和执行，每轮重新处理页面状态。日志中的数秒步骤间隔与这种链路一致；0.8 秒间隔只是其中一部分，不能用它解释全部等待。

`DeepSeekJSONChat.ainvoke` 的结构化请求没有传入 `thinking.type=disabled`。官方文档说明思考模式默认开启，默认努力程度为 high。因此，按供应商默认行为推断，当前请求会使用思考模式；尚未采集该任务的 reasoning token 或做开关对照测试，不能量化它占多少耗时。[DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)

固定的就业和失业登记表已有字段定义，不需要每个字段都重新规划。建议先根据对话和档案产生经过校验的字段映射，再让确定的浏览器动作执行填写；读回字段、选择项和校验结果后才确认完成。遇到未知页面或控件变化再调用自治 Agent。真实动作可以逐字段显示高亮和进度，不必逐字段请求模型，也不应用长延时模拟操作过程。

并发为 1 会让其他任务排队，但最近日志没有证明用户这次等待由排队造成。应分别统计排队、浏览器启动、页面观察、模型请求、执行和校验时间。

## 人工接管慢的来源

`BrowserUseSurface.send` 使用 Promise 串行队列，点击、文本、按键和每个 wheel 事件都等待前一个请求完成。worker 的 `live_action` 执行动作后调用 `get_task` 获取完整画面，`act` 又使截图缓存失效。因此用户连续输入或滚动时，会把截图获取和回传的时间反复加在队列里。

`ApplicationFormDialog` 另以 500ms 周期轮询完整状态，理想情况下约 2 次每秒，慢请求会进一步降低更新频率。动作请求和轮询还会竞争截图锁。当前帧缓存窗口为 350ms，不能消除每次人工动作后的新截图需求。

应将动作确认、任务状态、页面画面分开：输入通道只返回轻量确认和序号，画面持续推送；合并滚轮增量，适当合并文本输入，同时保持点击、输入、按键的顺序和中文输入法边界。保留停止 Agent 完全结束后才交给用户的控制约束。

已有 Playwright WebRTC 模式属于另一个浏览器运行时，不能直接切换来展示 Browser Use 的同一页面。它自身仍用截图生成视频帧，且人工动作会调用包含截图的 `observe`，所以仅启用已有 WebRTC 分支也不等于解决了采集和输入开销。

## 可选方案

以下能力来自截至本次查询的官方资料，匹配度是针对本项目的判断；候选组件尚未在本项目做清晰度、中文输入和延迟对照测试。

| 方案 | 用户看到和操作的页面 | 适用条件与判断 |
| --- | --- | --- |
| 自有页面的 DOM 或表单桥接 | 用户浏览器中的真实表单，文字原生渲染 | 当前模拟系统可采用，或目标业务系统愿意接入桥接协议。AI 生成映射，前端执行和回执，人工本地操作。不能直接读写任意第三方跨域页面。 |
| 浏览器扩展连接已有标签页 | 用户自己的 Chrome 或 Edge 标签页 | 清晰度和人工响应最接近正常浏览器；需要扩展或本地连接程序，主要体验在业务标签页。Microsoft Playwright MCP 支持扩展连接已有标签页和登录状态。[官方说明](https://github.com/microsoft/playwright-mcp#browser-extension) |
| 本地 Chromium 加实时展示组件 | 与 Agent 相同的远端浏览器，可嵌入 | 保留本地部署，替换轮询截图传输，已知页面优先确定的 Playwright 动作。noVNC 是可嵌入的 VNC 客户端，需要服务端显示和 VNC；其文字效果和输入法仍需验收。[noVNC](https://github.com/novnc/noVNC) |
| Steel 加 Playwright 或 Browser Use | 可嵌入实时会话和人工接管 | Steel 的托管 headful 文档描述 WebRTC H.264 25fps；开源版本支持自部署，但不能把云版能力自动当成自部署能力。自部署 viewer 有会话路由问题报告，采用前须验证用户与会话隔离。[实时会话](https://docs.steel.dev/overview/sessions-api/embed-sessions/live-sessions)、[开源部署](https://github.com/steel-dev/steel-browser)、[问题 333](https://github.com/steel-dev/steel-browser/issues/333) |
| Browserbase 加 Stagehand | iframe 内看和操作同一远端会话 | 适合希望少维护浏览器展示基础设施且允许云浏览器的情况。Live View 支持点击、输入、滚动和接管；Stagehand 支持动作缓存，页面改变时可能未命中缓存。具体版本 API 需固定后对接。[Live View](https://docs.browserbase.com/platform/browser/observability/session-live-view)、[Stagehand 缓存](https://docs.stagehand.dev/v3/best-practices/caching) |
| Browser Use Cloud | iframe 内实时预览并接管，继续同一会话 | 与现有 Agent 概念接近，但本地 Python worker 和 Cloud API 是不同接口。现行 V4 文档支持 live view 和人工介入，不是修改一个 worker 地址即可迁移。[实时预览](https://docs.browser-use.com/cloud/browser/live-preview)、[人工介入](https://docs.browser-use.com/cloud/agent/human-in-the-loop) |

浏览器查看链接需要纳入用户会话权限；云端会话会把业务页面和登录状态带到相应服务。对于受限制的内网业务，需要在可访问该内网的环境运行浏览器。这些部署条件会直接影响方案选择。

## 建议实施顺序

1. 在现有 worker 做 DeepSeek 思考模式开关的耗时和成功率对照；固定表单使用已确认字段映射和确定的动作执行，未知页面保留 Agent。批量动作不能跨越导航或继续使用已失效的控件索引。
2. 以无损截图和匹配视口验证模糊来源；拆分动作确认与截图获取，合并滚轮，减少队列积压。记录性能后再决定是否替换整个展示层。
3. 若必须维持本地部署和聊天内嵌，优先验证同一 Chromium 的实时展示方案，比较 noVNC 或经过验收的 Steel 自部署版本；若接受云浏览器，优先比较 Browserbase 加 Stagehand 和 Browser Use Cloud。

验收必须同时覆盖真实字段回读、人工接管后中文输入和滚动、材料选择、关闭重开以及最终提交仍由用户完成。分别记录冷启动和复用会话的填写耗时、模型调用次数、人工输入到可见变化的中位数和 P95，并做等比例文字截图对比。界面还应统一内外步骤表达、减少嵌套滚动，检查字号、对比度、布局和面向用户的文案。

上述排查阶段仅增加诊断文档和项目约定，未修改运行代码。

## 用户选定后的实现

用户选择恢复 Browser Use 原生 iframe，并同步高亮目标。办事任务现发送 `presentation=iframe`：
后台仍执行真实 Browser Use 工具，工具执行前定位字段或接收真实焦点事件，成功后回读字段，
通过有序操作事件及确认值同步到前台原生表单。失败/取消不发布未确认值；前台校验来源域和窗口、
任务 ID 与事件序号，保留人工修改及主动清空，执行中阻止提交，停止后由用户补材料及提交。
草稿刷新只提前带入只读身份字段，不把尚未执行的可编辑草稿值当成 Agent 填写结果。

这条展示链路不再生成/传输 JPEG；500ms 轮询只在 queued/running 阶段读取状态和事件。
任务结束释放后台浏览器，重开返回原任务确认值。前台人工修改尚未持久化；iframe 和后台 Chromium
是不同页面，接管指停止后台并继续填写前台，不是接管后台登录会话。目标页必须提供表单桥接，
不将该方案宣称为任意外站的通用自动操作。通用 live 模式及 Playwright WebRTC 分支继续保留。

验收：19 项 Python、8 项 Node 测试及前端构建通过；真实 React + 模拟业务页面验证原生高亮、
成功结果同步、人工修改/清空、材料选择、停止接管，未提交。已安装 Browser Use 与 Chromium 的 Linux
worker 环境中，以固定动作代替模型规划的隔离测试通过，验证真实工具接入、失败值不镜像和浏览器释放，
未调用模型。截图见 `output/browser-iframe-feedback.png`。

后续已按用户“更新”指令构建并切换 Linux 四个应用服务，全部健康，PostgreSQL/Redis readiness 通过。
生产前端资源和实际同源表单验证高亮、成功值同步、人工修改/清空、材料选择及停止接管；
该 UI 验证使用隔离的鉴权、聊天和任务 API 响应。新 worker 镜像内真实工具与 Chromium 的固定动作测试通过，
未调用模型或提交业务。部署截图见 `output/linux-iframe-feedback.png`，记录见 `docs/linux-docker-deployment.md`；
未重新测量模型推理耗时。

## 后续多字段规划优化

用户后续选择“一次对话规划多个字段”。办事 iframe 每轮动作上限由 1 改为 12，提示模型按页面顺序
在一轮返回多个独立字段动作，优先 input/select_dropdown，不允许脚本同时填写多个字段。
每项成功后把执行器实际回读的 key/value 附在工具结果和模型记忆中，减少完成时重复查找字段。
真实填写、逐项高亮和取消继续走原有链路；0.8 秒动作间隔保留，没有前端动画回放。

已检查安装的 browser-use 0.13.0 `Agent.multi_act`：evaluate 和导航等动作会终止队列，失败或
URL/浏览器目标改变也会中断剩余动作。保留这些保护，联动或失败后重新观察规划。

在 Linux worker 的隔离进程使用现有 DeepSeek 模型和合成数据测试：首次模型回复含 6 个动作
（input、select_dropdown、4 个 input），全部字段真实回读匹配，逐项执行区间为 4.91 秒。
含浏览器启动、页面准备、规划、done 和评估共 37.03 秒；3 次模型请求耗时分别为 4.93、8.46、
4.79 秒。测试阻断提交请求且没有提交尝试。该单次观测不是稳定性能保证，也不是与旧版的同条件
速度对照；页面启动和最后核对仍有等待，不能声称整项业务只调用一次模型。

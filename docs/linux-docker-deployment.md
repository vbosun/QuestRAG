# Linux 本地构建与部署

本部署复用 Linux 宿主机已有的 PostgreSQL、Redis、Milvus 和 Ollama Embedding，不重复创建数据库或 GPU 模型容器。新增 `backend`、`mock-business`、`browser-worker`、`web` 四个服务。网页、API、模拟业务表单共用一个入口；只有 web 发布宿主机端口，worker 不对外发布。

## 1. 获取代码

需要 Docker Engine 与 Docker Compose 插件。首次获取仓库，使用包含容器化文件的分支：

```bash
git clone --branch codex/linux-container-deployment git@github.com:vbosun/QuestRAG.git
cd QuestRAG
```

已有 checkout 应先检查 `git status --short` 并保存本机改动，再切到目标分支并 `git pull --ff-only`。不要覆盖旧版 checkout、其他项目或现有数据卷。

## 2. 配置

```bash
cp deploy/compose.env.example .env.compose
chmod 600 .env.compose
```

在 Linux 本机编辑 `.env.compose`，不要把凭证粘贴进日志或提交。默认仅监听 `127.0.0.1:18080`；局域网演示时将 `QUESTRAG_BIND_ADDRESS` 设置为该主机的局域网 IP。已有服务需向 Docker bridge 开放对应监听地址，并允许该网段访问。

`host.docker.internal` 通过 Compose 的 `host-gateway` 映射到宿主机；容器中的 `localhost` 指向容器自身。这里数据库示例端口为 5433、Milvus 为 19530、Redis 为 6379、Ollama 为 11434，应按已有服务修改。

模型使用 Ollama 的 OpenAI 兼容入口 `http://host.docker.internal:11434/v1`，模型名 `bge-m3:latest`。验证返回维度 1024；不要混用不兼容的历史向量。`EMBEDDING_API_KEY` 独立于生成模型密钥。

复用现有 QuestRAG 数据库时保留 `AUTH_ID_NUMBER_PEPPER`，否则账号摘要无法匹配；保留 JWT 配置以避免两个部署互相影响。生成并保存独立的 64 位十六进制 `SM2_PRIVATE_KEY`，前端通过公钥接口获取对应公钥。不要更换现有登录密码。

数据库需要 **pgvector 与 zhparser，并创建名为 chinese 的文本检索配置**。普通 PostgreSQL/pgvector 镜像不会自动提供 chinese；本 Compose 刻意不重复部署 PostgreSQL。当前岗位表维度固定为 1024。启动会进行已有的幂等建表和演示规则初始化；新数据库不会自动生成演示账号、岗位或知识文档，需要导入。

Milvus 集合使用现有的 QuestRAG 集合，与 TapTap 等其他业务集合分开。已有数据不迁移、不删除。

## 3. 构建与启动

```bash
bash deploy/up.sh
```

也可以分别执行：

```bash
docker compose --env-file .env.compose config -q
docker compose --env-file .env.compose build backend browser-worker web
docker compose --env-file .env.compose up -d --wait --wait-timeout 180
docker compose --env-file .env.compose ps
```

模型与数据库凭证仅在运行时注入，不进入镜像。镜像构建使用根目录 uv.lock 与前端 package-lock.json；worker 固定 browser-use 0.13.0，和主后端依赖隔离。部署目录中的模板提供可覆盖的国内镜像和包源，镜像源或上游不通时换源重试，不关闭 TLS 校验。

uv 默认从官方 `ghcr.io/astral-sh/uv:0.9.26` 镜像复制二进制。本次主机访问 GHCR 较慢，使用已验证后端镜像中的同版本 uv 创建本地 `questrag-uv-bootstrap:0.9.26`，并在 `.env.compose` 中设置 `UV_IMAGE=questrag-uv-bootstrap:0.9.26`。此覆盖只用于构建工具，不包含模型和运行凭证；新主机优先使用官方默认值。

## 4. 验收

把下面地址替换为实际绑定地址。`live` 仅表示 API 进程运行，不能代替依赖验收：

```bash
curl --fail http://127.0.0.1:18080/health/live
curl --fail http://127.0.0.1:18080/health/ready
curl --fail http://127.0.0.1:18080/auth/public-key
docker compose --env-file .env.compose exec -T browser-worker python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8090/health').read().decode())"
```

登录后逐项验证：政策问答能检索并显示正确引用；岗位检索；创建就业/失业登记草稿；人工修改不会被轮询覆盖。模拟表单不自动提交。

Browser Use 还需在系统配置中选择相应执行模式。worker 默认单任务执行、最多 4 个待执行/执行中任务、单任务最长 300 秒；容量满时返回 429。`BROWSER_USE_MODEL`、`BROWSER_USE_BASE_URL`、`BROWSER_USE_API_KEY` 未填写时继承生成模型配置。文本模型应设置 `BROWSER_USE_USE_VISION=false`；不支持 JSON Schema 的供应商可使用模板中的结构化输出兼容配置。模型供应商是否能完成浏览器任务必须实际验证。

浏览器使用容器内安装的 Chromium，不需要占用 GPU。按用户 2026-10-10 的选择，Browser Use 办事弹窗使用原生 iframe，后台 Chromium 继续执行，通过同源鉴权状态 API 同步真实操作目标和成功回读值。前台原生高亮对应字段；人工修改及清空优先保留，点击“停止并接管”后停止后台执行，用户继续填写前台表单并选择材料。前后台是两个页面，不能称为同页会话接管；目标页必须配合表单桥接。通用浏览器 live 模式仍使用实际远端页面及 JPEG 画面；独立 Playwright 视频模式的跨网/NAT 仍需另行验证。worker 完成不能当作真实政务提交成功。

通用 live 模式保留会话最多两个，空闲默认 15 分钟释放，worker 重启或回收后未提交页面内容会丢失。办事 iframe 任务结束即释放后台浏览器，重开只重放内存中的确认值，前台人工修改尚未持久化。多用户并发、画面带宽和长期保留策略尚需容量验证。

## 5. 更新、数据与回滚

```bash
git pull --ff-only
bash deploy/up.sh
```

Compose 项目名为 `questrag`。日志轮转保留每容器最多 3 个 10MB 文件；后端评测日志及 data 目录使用命名卷。业务页面配置保存到 `PAGE_CONNECTOR_DIR=/app/data/page_connectors`，本地生成的 JSON 不进入 Git 或新构建的镜像。旧部署迁移时应另外复制这些文件到数据卷。数据库、Milvus 与 Ollama 的现有数据由原服务管理，更新应用镜像不应清理它们。回滚到已验证的代码版本后重新构建即可；数据库结构变更需单独评估。

本次主机的长期部署 checkout 为 `/home/adminzb/questrag-deploy`，分支 `codex/linux-container-deployment`，运行环境文件为该目录下权限 600 的 `.env.compose`。后续在此目录执行上述更新命令。旧 `/home/adminzb/QuestRAG` 保留，首次构建目录 `/home/adminzb/questrag-container-20261009` 也保留；不要混用两个目录的环境配置。

## 6. 2026-10-09 实机验收记录

宿主机 `192.168.1.43` 为 Ubuntu、i5-9400、16GB 内存、GTX 1050 Ti 4GB。已有 Ollama `bge-m3:latest` 返回 1024 维，现有 Milvus `questrag_chunks_v2` 同为 1024 维、528 条记录；复用 QuestRAG 的 `vector_db`，未重建数据库。生成回答仍调用配置的 DeepSeek API；Chromium 在 CPU 上运行，不能描述为全部模型都在 1050 Ti 上推理。

前端、后端、模拟业务系统和 Browser Use worker 在该 Linux 主机实际构建并启动。入口为 `http://192.168.1.43:18080/app/chat`，仅用于当前局域网访问。`/health/live`、`/health/ready`、公钥接口和模拟业务表单均通过同源代理。

使用授权测试账号完成 SM2 登录、真实模型政策检索（单次约 14.3 秒，11 条 sources，无 SSE error）和就业登记草稿（约 17.7 秒，7 项字段，未提交）；实际页面确认人工修改不会被后续轮询覆盖。来源可检索不代表历史政策仍有效，不将旧材料作为最新政策结论。

真实 Browser Use 任务在独立 Chromium 页面完成填写与核对，修复模型 JSON 输出兼容及导航 URL 后单次约 64 秒，最终 completed、无 error，未执行提交。此处字段核对来自 Agent 执行记录；另用 Playwright 直接读取实际页面的 7 项字段并验证值，身份字段不进入 URL。两种模式均不能等同于用户正在查看的 iframe 或真实业务提交。

59 项相关 Python 单元测试、5 项 Node 表单测试通过；本地前端构建及 Linux 前端镜像构建通过。未做压力测试，WebRTC 跨网视频及真实政务平台尚未验证。浏览器任务清理后四个应用容器约占 535MB 内存，是一次静态观测，不能用于推断峰值或并发容量。

### 2026-10-10 同一浏览器页面与接管更新

28 项浏览器/办事相关 Python 测试和前端构建通过。LAN 页面验证了真实自动填写、字段高亮和 AI 指针、中途停止后接管、中文输入、原页面 file chooser 带入临时材料，以及关闭后重开保留人工内容；未点击提交。初始化姓名在导航后的首个步骤带入，只读字段不交给模型修改。画面约每 500ms 更新，指针在两次真实字段坐标之间平滑移动；不代表完整桌面远程控制或高帧率视频。

### 2026-10-10 原生 iframe 更新部署

用户随后选择恢复原生 iframe。已在 `/home/adminzb/questrag-deploy` 构建并更新 backend、mock-business、browser-worker、web 四个服务；Compose `up --wait` 通过，LAN `/health/live`、`/health/ready`、公钥及模拟表单接口均返回 200，PostgreSQL/Redis 检查为 true。`.env.compose` 内容和权限 600 经哈希核对保持不变，命名数据卷及原有账号配置保留，未执行数据库迁移或清理。

同步部署时发现已有后端文件引用的 `quest_rag/rag/model_options.py` 在部署目录漏失，首次切换后后端启动失败；补齐模块并同步已有 llm/generator 修复后重新构建，全部服务恢复健康。完整运行源码与本地版本比较仅存在换行差异，worker/backend/mock 的关键文件在运行容器内再次核对哈希。18 项模型配置与聊天流式输出测试通过。

生产前端资源配合实际同源模拟表单，通过字段高亮、仅同步成功值、人工修改与清空保护、原生材料选择、停止接管验证，无页面脚本错误且未提交。该 UI 测试的鉴权、聊天和任务 API 使用隔离响应，未使用真实账号；截图为 `output/linux-iframe-feedback.png`。新 worker 镜像内真实 Browser Use 工具与 Chromium 的固定动作测试通过，覆盖目标事件、失败值排除、成功回读、零实时截图及浏览器释放；未调用模型，模型耗时未重测。

切换前源文件备份为 `/tmp/questrag-iframe-rollback-20261010T011953Z.tar.gz`，已有 llm/generator 源文件另备份为 `/tmp/iframe-baseline-source-backup.tar.gz`。四个旧镜像保存为 `questrag-rollback-<service>:iframe-20261010t011953z`（service 为 backend、mock-business、browser-worker、web）；旧 web 镜像已被清理，其回退镜像从当时实际提供的静态文件与 nginx 配置重建。部署清单和回退标签保存在 `/tmp/iframe-deployment-report.json`。后续回退须同时使用匹配的源文件和四个镜像，保留现有环境文件与数据卷；不要只回退某一个服务。

### 2026-10-10 一轮规划多个字段

按用户后续选择，办事 iframe 每轮动作上限由 1 改为 12；模型一次给出多个独立字段动作，执行器逐项操作、高亮并回读。真实确认值同时写入模型工具结果，避免对已成功填写的字段重复核对；失败不发布确认值。通用 live 保持每轮一个动作，0.8 秒动作间隔及导航/页面变化/失败的队列中断保护保留。

19 项相关 Python、8 项 Node 测试和前端构建通过；实际 `Agent.multi_act` + Chromium 验证多动作顺序执行、失败停止后续动作、保留已成功结果、逐项回读及资源清理。使用现有 DeepSeek 模型的合成表单实测：一轮规划 6 项，真实填写约 4.91 秒，全部确认值匹配；含启动、规划、done 和评估共 37.03 秒，3 次模型调用。未使用真实账号、未提交，不能称为全流程只调用一次模型或稳定耗时保证。

此次只重建并更新 browser-worker，环境文件和数据保留；回退源文件为 `/tmp/questrag-browser-batch-rollback-20261010T013946Z.tar.gz`，回退镜像为 `questrag-rollback-browser-worker:batch-20261010t013946z`，部署清单为 `/tmp/browser-batch-deployment-report.json`。仅回退本次规划变更可使用此 worker 镜像和对应源文件，保留上一节已部署的 iframe 版本。

### 2026-10-10 申请窗口移动、缩放和开关按钮

申请页面默认悬浮显示，聊天区域仍可操作；聊天按钮随实际状态切换“打开申请页面”/“关闭申请页面”，点击为开关。左上角点状手柄和标题栏用于移动，右下角点状手柄用于调整宽高，两者支持方向键微调。拖动使用 Pointer Capture，跨 iframe 时仍连续响应；大小和位置限制在视口内，窄屏及浏览器窗口变化时重新约束。缩放调整原生表单可用空间，不缩放文字、截取图像或重载 iframe，人工输入和选中材料保持。

实际 React + 模拟表单验证按钮开关、右上角关闭同步、移动、放大/缩小、视口边界、键盘操作、人工输入和材料保留；原有高亮、成功值同步、停止接管验证通过，未提交。相关19项 Python测试及前端构建通过。测试仅对鉴权、聊天和任务 API 使用合成响应，业务页面与前端资源真实加载。截图为 `output/application-window-controls.png` 和 `output/application-window-narrow.png`。

此次只重建 web；环境文件及数据保留，回退源文件为 `/tmp/questrag-application-window-rollback-20261010T015731Z.tar.gz`，回退镜像为 `questrag-rollback-web:window-20261010t015731z`，部署清单为 `/tmp/application-window-deployment-report.json`。回退本次窗口变更可仅切换此 web 镜像和对应源码，保留已部署的批量规划 worker。


### 2026-10-10 聊天继续填写申请弹窗

新增 `fill_application_form(case_id, fields)` 并注册到当前聊天 Agent，复用已有表单写权限。先读取当前页面，按用户明确提供的信息一次传入最多 12 个字段，由 Browser Use 逐项执行及回读，原生 iframe 根据真实事件高亮并展示成功值。旧单字段工具在 Browser Use 模式也走同一执行入口，避免仅写后台草稿却回复已填好。主聊天只报告任务启动；后台完成、字段实际回读和前台页面回执匹配后才能报告填写成功。

续填采用独立 command_id，重试复用任务，不同命令创建新任务，同申请仍在执行时返回 409。新任务导航后恢复当前前台基准值（包含手动修改和清空），恢复不作为 AI 填写动画；仅允许指定字段的 input/select_dropdown 修改，禁止其他写操作、提交、离开或重载表单。前台在任务结束后仍监听后续任务；page_id、任务序列、退役任务集合防止旧结果回写。按字段的手动修改版本决定是否同步：用户明确要求修改时可以更新既有人工值，任务启动后又手动改过的值则保留并回报冲突。

页面通过可信 origin/window 消息回传文本值、版本及回执；每秒心跳，关闭/已提交/超过 5 秒没有心跳时拒绝聊天续填。有效的实际变化值写入草稿，未通过校验的输入和清空保留在后端单进程内存快照；关闭重开可恢复缓存文本，材料文件需要重选。进程重启会丢失内存编辑和任务映射。前台和后台仍是两个页面，运行中人工编辑由前台版本保护，下一批任务恢复最新基准，不宣称同页接管或通用第三方 iframe 支持。

验证：62 项相关 Python、10 项 Node 桥接测试及前端构建通过；真实 React/独立模拟表单验证多个字段依次高亮、终态后发现新任务、人工修改/清空冲突、停止后再填写、关闭拒绝续填和重开恢复文本。鉴权/worker响应使用合成夹具，但调用了实际聊天工具和页面状态服务。真实 Chromium + Browser Use multi_act 的固定规划测试执行两个独立续填任务，验证基准恢复、回读、未请求字段保留及资源释放。另以隔离合成申请调用真实聊天模型与 worker 模型，聊天一次调用批量工具填写电话和职业，约 29.58 秒，实际值匹配且人工地址保留；该模型测试没有真实前台回执，不称为真实账号全链路验收，不与之前六字段任务直接比较。全部测试未提交业务。截图 `output/chat-followup-filling.png`。

Linux 已重建 backend/browser-worker/web，mock-business 复用 backend 镜像并重建容器；服务健康，运行环境文件内容及权限、已有数据卷保留。回退源包 `/tmp/questrag-chat-filling-rollback-20261010T022356Z.tar.gz`，镜像为 `questrag-rollback-<backend|mock-business|browser-worker|web>:chatfill-20261010t022356z`，清单 `/tmp/chat-filling-deployment-report.json`。源码回退时还应移除清单 added_files 指定的本次新增文件；仅在部署根目录内按准确路径操作，不删除数据或配置。

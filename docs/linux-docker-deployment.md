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

浏览器使用容器内安装的 Chromium，不需要占用 GPU。Browser Use worker 的执行页面与前端 iframe 是独立页面，当前不共享人工修改或登录态；worker 完成不能当作真实政务提交成功。Playwright 的视频模式在跨网/NAT 环境还需要 ICE/TURN 配置验证，不能凭网页加载成功宣称远程视频可用。

## 5. 更新、数据与回滚

```bash
git pull --ff-only
bash deploy/up.sh
```

Compose 项目名为 `questrag`。日志轮转保留每容器最多 3 个 10MB 文件；后端评测日志及 data 目录使用命名卷。业务页面配置保存到 `PAGE_CONNECTOR_DIR=/app/data/page_connectors`，本地生成的 JSON 不进入 Git 或新构建的镜像。旧部署迁移时应另外复制这些文件到数据卷。数据库、Milvus 与 Ollama 的现有数据由原服务管理，更新应用镜像不应清理它们。回滚到已验证的代码版本后重新构建即可；数据库结构变更需单独评估。

## 6. 2026-10-09 实机验收记录

宿主机 `192.168.1.43` 为 Ubuntu、i5-9400、16GB 内存、GTX 1050 Ti 4GB。已有 Ollama `bge-m3:latest` 返回 1024 维，现有 Milvus `questrag_chunks_v2` 同为 1024 维、528 条记录；复用 QuestRAG 的 `vector_db`，未重建数据库。生成回答仍调用配置的 DeepSeek API；Chromium 在 CPU 上运行，不能描述为全部模型都在 1050 Ti 上推理。

前端、后端、模拟业务系统镜像在该 Linux 主机实际构建并启动。入口为 `http://192.168.1.43:18080/app/chat`，仅用于当前局域网访问。`/health/live`、`/health/ready`、公钥接口和模拟业务表单均通过同源代理。

使用授权测试账号完成 SM2 登录、真实模型政策检索（单次约 14.3 秒，11 条 sources，无 SSE error）和就业登记草稿（约 17.7 秒，7 项字段，未提交）；实际页面确认人工修改不会被后续轮询覆盖。来源可检索不代表历史政策仍有效，不将旧材料作为最新政策结论。

57 项相关 Python 单元测试、5 项 Node 表单测试通过；本地前端构建及 Linux 前端镜像构建通过。未做压力测试，WebRTC 跨网视频及真实政务平台尚未验证。启动后三个应用容器约占 300MB 内存，是当时静态观测，浏览器执行时另行测量。

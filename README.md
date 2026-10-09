# QuestRAG

面向就业公共服务场景的 RAG 与业务助手原型：政策问答、岗位检索、社保演示查询、规则式补贴测算，以及就业/失业登记草稿和表单辅助填写。

后端为 **Python 3.12 / FastAPI / LangChain**，前端为 **React / TypeScript / Ant Design**。当前仓库没有 Java 服务。办事页面属于独立模拟系统，不能用于真实政务申报。

## 已实现与边界

- PostgreSQL：文档及版本、评测记录、权限、会话、申请草稿与审计等业务数据；岗位检索使用 PostgreSQL。
- Redis：登录会话和登录失败控制。
- Milvus：当前本地环境的政策文档向量检索；代码还提供 Elasticsearch 和内存适配器。
- 大模型：通过 OpenAI 兼容协议调用配置的供应商；变量名前缀不代表实际供应商。
- 检索：向量与关键词结果通过 RRF 融合。Milvus 当前关键词分支是文本匹配，不应描述成已经实现 BM25 排名。
- 办事：支持 embedded、Playwright、Browser Use 三种模式。配置 Browser Use 但没有 worker URL 时，申请页面会明确回退为嵌入表单辅助填写。
- 嵌入表单收到填写回执后才显示已带入；人工修改不会被后续轮询覆盖。人工修改目前只保留在当前业务页面，刷新后不会自动写回 QuestRAG 草稿。
- 模拟业务系统的提交回执与 QuestRAG 申请状态尚未实现持久化一致同步；多角色审批、并发修改和任务恢复仍需完善。

## 本地启动（Windows PowerShell）

Linux/Docker 本地构建与部署见 [部署说明](docs/linux-docker-deployment.md)。根目录 Compose 复用已有数据库、Milvus 和 Ollama，新增应用及独立浏览器 worker，支持同源访问表单。

这是使用已配置依赖的启动步骤，尚不是从空机器一键部署。需要预先准备 PostgreSQL、Redis、Milvus、Embedding 服务及可用模型账号。不要将本地 `.env`、账号或密钥提交到仓库。

根目录安装依赖：

```powershell
uv sync
```

在根目录的不同终端分别启动：

```powershell
uv run python -m quest_rag.main
```

```powershell
uv run uvicorn mock_business_system.app:app --host 127.0.0.1 --port 8020
```

```powershell
Set-Location web
npm ci
npm run dev
```

前端：`http://127.0.0.1:5173`；后端 API：`http://127.0.0.1:8010/docs`；模拟业务系统：`http://127.0.0.1:8020`。项目已有进程时先确认端口，不重复启动。

配置项定义见 [config.py](quest_rag/core/config.py)。核心变量包括 `DATABASE_URL`、`REDIS_URL`、`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`、`EMBEDDING_BASE_URL`、`OPENAI_EMBEDDING_MODEL`、`VECTOR_BACKEND`、`MILVUS_HOST`、`MILVUS_PORT`。认证还需要 `JWT_SECRET_KEY`、`AUTH_ID_NUMBER_PEPPER`、`SM2_PRIVATE_KEY` 等本地配置。模型和检索参数、申请执行模式还会从数据库系统配置加载。

Browser Use 为可选独立 worker，具体安装见 [集成说明](docs/browser-use-integration.md)。明天演示可以使用已经验证的嵌入表单模式，无需临时安装 worker。

## 验证

以下测试使用模拟依赖验证权限、SSE、草稿、错误分类、评测统计及表单消息边界：

```powershell
uv run python -m pytest tests/test_applications.py tests/test_browser_use_runtime.py tests/test_permissions.py tests/test_chat_stream.py tests/test_model_errors.py tests/test_evaluation_metrics.py -q
uv run python -m pytest tests/test_citation_isolation.py -q
node --test tests/test_form_bridge.mjs
```

```powershell
Set-Location web
npm run build
```

`tests/test_rag.py` 中部分测试会访问实际 Embedding/Milvus 并写入集合，运行前应配置隔离的测试环境。上面的验证不等于全系统集成、压力或故障恢复测试。

## 审查和演示准备

[2026-10-09 项目审查与 Java 面试准备](docs/20261009-项目审查与Java面试准备.md)包含本次修复、生产差距、历史评测解释、岗位匹配、演示脚本和后续路线。

早期技术方案属于阶段性设计记录，当前实现以代码和本次审查为准。

2026-10-09 实测提示：模型充值后申请草稿链路可用，但当时本地 Embedding 地址 `http://localhost:5001/v1` 未监听，政策向量检索未能完成。生成模型额度与本地 Embedding 服务是两个独立依赖，演示前必须分别检查。

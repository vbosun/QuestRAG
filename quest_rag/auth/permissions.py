"""
权限常量定义与默认数据 seed。

权限 code 全局唯一，类型分为:
  ROUTE    - 前端路由权限
  MENU     - 菜单显示权限
  API      - 后端接口权限
  ACTION   - 页面按钮/操作权限
  LLM_TOOL - 大模型工具权限
"""

PERMISSIONS: dict[str, dict] = {
    # ── 工作台页面 ──
    "chat.view": {
        "name": "助手聊天", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "knowledge.view": {
        "name": "知识库管理", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "evaluation.view": {
        "name": "评测工作", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "system.retrieval_config.view": {
        "name": "查看检索配置", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "profile.view": {
        "name": "个人管理", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "permission.manage": {
        "name": "权限管理", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "CRITICAL",
    },
    "public_services.view": {
        "name": "政务工具", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "public_services.social_security.view": {
        "name": "社保查询", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "application.workspace.view": {
        "name": "智能办事", "type": "ROUTE", "group_code": "workspace",
        "risk_level": "LOW",
    },
    "application.case.create": {
        "name": "发起办事申请", "type": "API", "group_code": "application",
        "risk_level": "LOW",
    },
    "application.case.read_self": {
        "name": "查看本人申请", "type": "API", "group_code": "application",
        "risk_level": "LOW",
    },
    "application.case.edit_self": {
        "name": "编辑本人申请草稿", "type": "API", "group_code": "application",
        "risk_level": "MEDIUM",
    },
    "application.browser.connect": {
        "name": "连接本机办事浏览器", "type": "API", "group_code": "application",
        "risk_level": "MEDIUM",
    },

    # ── 知识库操作 ──
    "knowledge.document.read": {
        "name": "查看文档", "type": "API", "group_code": "knowledge",
        "risk_level": "LOW",
    },
    "knowledge.document.upload": {
        "name": "上传文档", "type": "API", "group_code": "knowledge",
        "risk_level": "HIGH",
    },
    "knowledge.document.commit": {
        "name": "文档入库", "type": "API", "group_code": "knowledge",
        "risk_level": "HIGH",
    },
    "knowledge.document.delete": {
        "name": "删除文档", "type": "API", "group_code": "knowledge",
        "risk_level": "HIGH",
    },

    # ── 评测操作 ──
    "evaluation.run.read": {
        "name": "查看评测记录", "type": "API", "group_code": "evaluation",
        "risk_level": "LOW",
    },
    "evaluation.run.create": {
        "name": "新建评测", "type": "API", "group_code": "evaluation",
        "risk_level": "MEDIUM",
    },
    "evaluation.run.delete": {
        "name": "删除评测", "type": "API", "group_code": "evaluation",
        "risk_level": "HIGH",
    },
    "evaluation.document.manage": {
        "name": "管理评测文档", "type": "API", "group_code": "evaluation",
        "risk_level": "MEDIUM",
    },
    "evaluation.dataset.manage": {
        "name": "管理评测集", "type": "API", "group_code": "evaluation",
        "risk_level": "MEDIUM",
    },

    # ── 系统配置 ──
    "system.retrieval_config.update": {
        "name": "修改检索配置", "type": "API", "group_code": "system",
        "risk_level": "HIGH",
    },

    # ── 权限管理 ──
    "permission.role.view": {
        "name": "查看角色", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.role.create": {
        "name": "新建角色", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.role.update": {
        "name": "编辑角色", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.role.delete": {
        "name": "删除角色", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.role.assign": {
        "name": "配置角色权限", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.view": {
        "name": "查看用户", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.create": {
        "name": "新建用户", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.update": {
        "name": "编辑用户", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.assign_role": {
        "name": "分配角色", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.lock": {
        "name": "锁定用户", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.unlock": {
        "name": "解锁用户", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.reset_password": {
        "name": "重置密码", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },
    "permission.user.kick": {
        "name": "强制下线", "type": "API", "group_code": "permission",
        "risk_level": "CRITICAL",
    },

    # ── 大模型工具 ──
    "llm.tool.knowledge_search": {
        "name": "知识库检索工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.job_search": {
        "name": "岗位检索工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.social_security_search": {
        "name": "社保查询工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.subsidy_match": {
        "name": "补贴匹配工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.subsidy_calculate": {
        "name": "补贴测算工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.application_workflow_read": {
        "name": "办事流程查询工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.application_form_read": {
        "name": "读取当前申请页面工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.application_workflow_start": {
        "name": "发起办事申请工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
    "llm.tool.application_workflow_guide": {
        "name": "办事条件与表单查询工具", "type": "LLM_TOOL", "group_code": "llm_tool",
        "risk_level": "LOW",
    },
}

OBSOLETE_PERMISSION_CODES = {
    "knowledge.document.acl.manage",
    "llm.tool.evaluation_read",
    "llm.tool.evaluation_run",
    "llm.tool.document_ingest",
    "llm.tool.document_delete",
    "llm.tool.system_config_read",
    "llm.tool.system_config_write",
    "llm.tool.user_permission_manage",
}

RAG_SCOPES: dict[str, dict] = {
    "public_policy": {"name": "公开政策库", "description": "普通知识库政策文档"},
    "jobs": {"name": "岗位库", "description": "岗位数据"},
    "evaluation_docs": {"name": "评测文档", "description": "评测工作台专用文档"},
    "internal_policy": {"name": "内部政策库", "description": "内部口径文档"},
    "department_docs": {"name": "部门文档", "description": "部门范围文档"},
    "private_docs": {"name": "个人文档", "description": "个人私有文档"},
    "social_security_mock": {"name": "模拟社保库", "description": "本人模拟社保数据"},
    "subsidy_policy": {"name": "补贴政策库", "description": "补贴规则及政策原文"},
}

PERMISSION_DEPENDENCIES: dict[str, str] = {
    "knowledge.document.read": "knowledge.view",
    "knowledge.document.upload": "knowledge.view",
    "knowledge.document.commit": "knowledge.view",
    "knowledge.document.delete": "knowledge.view",
    "evaluation.run.read": "evaluation.view",
    "evaluation.run.create": "evaluation.view",
    "evaluation.run.delete": "evaluation.view",
    "evaluation.document.manage": "evaluation.view",
    "evaluation.dataset.manage": "evaluation.view",
    "system.retrieval_config.update": "system.retrieval_config.view",
    "permission.role.view": "permission.manage",
    "permission.role.create": "permission.manage",
    "permission.role.update": "permission.manage",
    "permission.role.delete": "permission.manage",
    "permission.role.assign": "permission.manage",
    "permission.user.view": "permission.manage",
    "permission.user.create": "permission.manage",
    "permission.user.update": "permission.manage",
    "permission.user.assign_role": "permission.manage",
    "permission.user.lock": "permission.manage",
    "permission.user.unlock": "permission.manage",
    "permission.user.reset_password": "permission.manage",
    "permission.user.kick": "permission.manage",
    "public_services.social_security.view": "public_services.view",
    "application.case.create": "application.workspace.view",
    "application.case.read_self": "application.workspace.view",
    "application.case.edit_self": "application.workspace.view",
    "application.browser.connect": "application.workspace.view",
}

RAG_SCOPE_DEPENDENCIES: dict[str, list[str]] = {
    "public_policy": ["llm.tool.knowledge_search"],
    "evaluation_docs": ["llm.tool.knowledge_search"],
    "internal_policy": ["llm.tool.knowledge_search"],
    "department_docs": ["llm.tool.knowledge_search"],
    "private_docs": ["llm.tool.knowledge_search"],
    "jobs": ["llm.tool.job_search"],
    "social_security_mock": [
        "llm.tool.social_security_search",
        "llm.tool.subsidy_match",
        "llm.tool.subsidy_calculate",
    ],
    "subsidy_policy": [
        "llm.tool.subsidy_match",
        "llm.tool.subsidy_calculate",
    ],
}

DOCUMENT_RAG_SCOPE_CODES = {
    "public_policy",
    "evaluation_docs",
    "internal_policy",
    "department_docs",
    "private_docs",
}

DEFAULT_ROLES: dict[str, dict] = {
    "ADMIN": {
        "name": "系统管理员",
        "description": "拥有全部系统功能权限、角色/用户管理权限、全部 RAG scope",
        "system_builtin": True,
        "permissions": [
            "chat.view", "profile.view",
            "knowledge.view", "knowledge.document.read", "knowledge.document.upload",
            "knowledge.document.commit", "knowledge.document.delete",
            "evaluation.view", "evaluation.run.read", "evaluation.run.create",
            "evaluation.run.delete", "evaluation.document.manage", "evaluation.dataset.manage",
            "system.retrieval_config.view", "system.retrieval_config.update",
            "permission.manage",
            "permission.role.view", "permission.role.create", "permission.role.update",
            "permission.role.delete", "permission.role.assign",
            "permission.user.view", "permission.user.create", "permission.user.update",
            "permission.user.assign_role", "permission.user.lock", "permission.user.unlock",
            "permission.user.reset_password", "permission.user.kick",
            "public_services.view", "public_services.social_security.view",
            "application.workspace.view", "application.case.create", "application.case.read_self",
            "application.case.edit_self", "application.browser.connect",
            "llm.tool.knowledge_search", "llm.tool.job_search",
            "llm.tool.social_security_search", "llm.tool.subsidy_match", "llm.tool.subsidy_calculate",
            "llm.tool.application_workflow_read",
            "llm.tool.application_form_read",
            "llm.tool.application_workflow_start",
            "llm.tool.application_workflow_guide",
        ],
        "rag_scopes": ["public_policy", "jobs", "evaluation_docs", "social_security_mock", "subsidy_policy"],
    },
    "OPERATOR": {
        "name": "业务经办员",
        "description": "可查看和上传知识库文档、管理评测、查看检索配置",
        "system_builtin": True,
        "permissions": [
            "chat.view", "profile.view",
            "knowledge.view", "knowledge.document.read", "knowledge.document.upload",
            "knowledge.document.commit",
            "evaluation.view", "evaluation.run.read", "evaluation.run.create",
            "evaluation.document.manage", "evaluation.dataset.manage",
            "system.retrieval_config.view",
            "public_services.view", "public_services.social_security.view",
            "application.workspace.view", "application.case.create", "application.case.read_self",
            "application.case.edit_self", "application.browser.connect",
            "llm.tool.knowledge_search", "llm.tool.job_search",
            "llm.tool.social_security_search", "llm.tool.subsidy_match", "llm.tool.subsidy_calculate",
            "llm.tool.application_workflow_read",
            "llm.tool.application_form_read",
            "llm.tool.application_workflow_start",
            "llm.tool.application_workflow_guide",
        ],
        "rag_scopes": ["public_policy", "jobs", "evaluation_docs", "social_security_mock", "subsidy_policy"],
    },
    "REVIEWER": {
        "name": "审阅人员",
        "description": "可查看评测记录和知识库，不做高风险改动",
        "system_builtin": True,
        "permissions": [
            "chat.view", "profile.view",
            "evaluation.view", "evaluation.run.read",
            "llm.tool.knowledge_search", "llm.tool.job_search",
        ],
        "rag_scopes": ["public_policy", "jobs", "evaluation_docs"],
    },
    "USER": {
        "name": "普通用户",
        "description": "默认角色，只能聊天和使用知识库/岗位检索",
        "system_builtin": True,
        "permissions": [
            "chat.view", "profile.view",
            "public_services.view", "public_services.social_security.view",
            "application.workspace.view", "application.case.create", "application.case.read_self",
            "application.case.edit_self", "application.browser.connect",
            "llm.tool.knowledge_search", "llm.tool.job_search",
            "llm.tool.social_security_search", "llm.tool.subsidy_match", "llm.tool.subsidy_calculate",
            "llm.tool.application_workflow_read",
            "llm.tool.application_form_read",
            "llm.tool.application_workflow_start",
            "llm.tool.application_workflow_guide",
        ],
        "rag_scopes": ["public_policy", "jobs", "social_security_mock", "subsidy_policy"],
    },
}


def seed_default_permissions():
    """幂等写入默认权限、RAG scope、角色及关联。"""
    from quest_rag.auth.permission_store import (
        get_conn,
        ensure_permission,
        ensure_rag_scope,
        ensure_role,
        set_role_permissions,
        set_role_rag_scopes,
    )

    with get_conn() as conn:
        for code in OBSOLETE_PERMISSION_CODES:
            conn.execute("DELETE FROM auth_permission WHERE code = %s", (code,))

        # 1. 写入权限
        perm_ids: dict[str, int] = {}
        for code, info in PERMISSIONS.items():
            pid = ensure_permission(
                conn,
                code=code,
                name=info["name"],
                type=info["type"],
                group_code=info.get("group_code", ""),
                risk_level=info.get("risk_level", "LOW"),
            )
            perm_ids[code] = pid

        # 2. 写入 RAG scope
        scope_ids: dict[str, int] = {}
        for code, info in RAG_SCOPES.items():
            sid = ensure_rag_scope(
                conn,
                code=code,
                name=info["name"],
                description=info.get("description", ""),
            )
            scope_ids[code] = sid

        # 3. 写入角色及其权限/scope关联。
        # 已存在角色可能已由管理员在页面中调整，seed 不能把被移除的权限或 scope 自动补回。
        for role_code, info in DEFAULT_ROLES.items():
            role = ensure_role(
                conn,
                code=role_code,
                name=info["name"],
                description=info.get("description", ""),
                system_builtin=info.get("system_builtin", False),
            )
            role_id = role["id"]
            is_new = role["is_new"]

            if is_new:
                scope_id_list = [scope_ids[s] for s in info.get("rag_scopes", []) if s in scope_ids]
                perm_id_list = [perm_ids[p] for p in info.get("permissions", []) if p in perm_ids]
                conn.execute("DELETE FROM auth_role_permission WHERE role_id = %s", (role_id,))
                conn.execute("DELETE FROM auth_role_rag_scope WHERE role_id = %s", (role_id,))
                for pid in perm_id_list:
                    conn.execute(
                        "INSERT INTO auth_role_permission (role_id, permission_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (role_id, pid),
                    )
                for sid in scope_id_list:
                    conn.execute(
                        "INSERT INTO auth_role_rag_scope (role_id, scope_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (role_id, sid),
                    )

"""给指定身份证号分配 ADMIN 角色"""
from quest_rag.auth.security import normalize_id_number, compute_id_number_digest
from quest_rag.auth.store import get_account_by_id_number_digest
from quest_rag.auth.permission_store import get_conn

normalized = normalize_id_number("110101199001010001")
digest = compute_id_number_digest(normalized)

account = get_account_by_id_number_digest(digest)
if account is None:
    print("用户不存在，需要先创建账号")
else:
    print(f"找到用户: id={account['id']}, name={account['full_name']}")
    with get_conn() as conn:
        role = conn.execute("SELECT id FROM auth_role WHERE code = 'ADMIN'").fetchone()
        if role is None:
            print("ADMIN 角色不存在，请先启动应用初始化权限表")
        else:
            conn.execute(
                "INSERT INTO auth_account_role (account_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (account["id"], role["id"]),
            )
            print(f"已为用户 {account['full_name']} 分配 ADMIN 角色")

        roles = conn.execute(
            """SELECT r.code FROM auth_role r
               JOIN auth_account_role ar ON r.id = ar.role_id
               WHERE ar.account_id = %s""",
            (account["id"],),
        ).fetchall()
        print(f"当前角色: {[r['code'] for r in roles]}")

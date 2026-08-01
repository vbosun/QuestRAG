"""直接操作数据库给指定身份证号分配 ADMIN 角色"""
from quest_rag.auth.security import compute_id_number_digest, normalize_id_number
from quest_rag.auth.store import get_account_by_id_number_digest
from quest_rag.auth.permission_store import get_conn

digest = compute_id_number_digest(normalize_id_number("110101199001010001"))
account = get_account_by_id_number_digest(digest)

if not account:
    print("用户不存在")
else:
    print(f"用户: id={account['id']} name={account['full_name']}")

    with get_conn() as conn:
        role = conn.execute("SELECT id FROM auth_role WHERE code = 'ADMIN'").fetchone()
        conn.execute(
            "INSERT INTO auth_account_role (account_id, role_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (account["id"], role["id"]),
        )
        roles = conn.execute(
            """SELECT r.code FROM auth_role r
               JOIN auth_account_role ar ON r.id = ar.role_id
               WHERE ar.account_id = %s""",
            (account["id"],),
        ).fetchall()
        print(f"roles: {[r['code'] for r in roles]}")

print("done")

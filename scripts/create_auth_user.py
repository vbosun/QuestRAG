"""Create an initial admin or user account for QuestRAG."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from quest_rag.auth.security import (
    normalize_id_number,
    compute_id_number_digest,
    hash_password,
)
from quest_rag.auth.store import create_personal_info, create_auth_account


def main():
    parser = argparse.ArgumentParser(description="Create an auth user for QuestRAG")
    parser.add_argument("--id-number", required=True, help="18-digit ID number")
    parser.add_argument("--full-name", required=True, help="Full name")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--role", default="ADMIN", choices=["USER", "ADMIN", "SYSTEM"], help="Role (default: ADMIN)")
    args = parser.parse_args()

    try:
        normalized = normalize_id_number(args.id_number)
    except ValueError as e:
        print(f"Invalid ID number: {e}")
        sys.exit(1)

    digest = compute_id_number_digest(normalized)
    password_hash = hash_password(args.password)

    personal_info_id = create_personal_info(
        id_number_digest=digest,
        full_name=args.full_name,
        id_number=normalized,
    )
    account_id = create_auth_account(
        personal_info_id=personal_info_id,
        id_number_digest=digest,
        password_hash=password_hash,
        role=args.role,
    )

    print(f"User created successfully.")
    print(f"  Account ID: {account_id}")
    print(f"  Personal Info ID: {personal_info_id}")
    print(f"  Role: {args.role}")
    print(f"  Name: {args.full_name}")


if __name__ == "__main__":
    main()

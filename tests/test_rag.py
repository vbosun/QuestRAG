import pytest

from quest_rag.rag.embedding import add_documents
from quest_rag.rag.generator import generate
from quest_rag.rag.loader import load_file


def test_load_file(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("姓名:张三, 性别:男, 职业:程序员, 年龄:99")

    docs = load_file(str(txt_file))
    assert len(docs) == 1
    assert "姓名" in docs[0].page_content

def test_add_documents(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("姓名:张三, 性别:男, 职业:程序员, 年龄:99")
    # todo


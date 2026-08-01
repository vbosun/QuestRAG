from math import floor

import pytest

from quest_rag.rag.document_embedding import add_documents
from quest_rag.rag.generator import generate
from quest_rag.rag.loader import load_file
from quest_rag.rag.document_retriever import search
from quest_rag.rag.document_splitter import split_docs


def test_load_file(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("姓名:张三, 性别:男, 职业:程序员, 年龄:99")

    docs = load_file(str(txt_file))
    assert len(docs) == 1
    assert "姓名" in docs[0].page_content

def test_splitter(tmp_path):
    txt_file = tmp_path / "sample.txt"
    stra = "姓名:张三, 性别:男, 职业:程序员, 年龄:99"
    txt_file.write_text(stra)

    docs = load_file(str(txt_file))
    docs1 = split_docs(docs, len(stra) *2, floor(len(stra)/2))
    assert len(docs1) == 1
    assert "姓名" in docs1[0].page_content
    docs1 = split_docs(docs, floor(len(stra)/2), floor(len(stra)/3))
    assert len(docs1) >= 2
    assert "姓名" in docs1[0].page_content


def test_add_documents(tmp_path):
    txt_file = tmp_path / "sample.txt"
    stra = "姓名:张三, 性别:男, 职业:程序员, 年龄:99"
    txt_file.write_text(stra)
    docs = load_file(str(txt_file))
    docs1 = split_docs(docs, len(stra) *2, floor(len(stra)/2))
    ids = add_documents(docs1)
    assert len(ids) == 1

def test_search(tmp_path):
    txt_file = tmp_path / "sample.txt"
    stra = """
姓名:张三, 性别:男, 职业:程序员, 年龄:99
姓名:李四, 性别:女, 职业:医生, 年龄:88
姓名:王五, 性别:未知, 职业:随机, 年龄:随机
"""
    txt_file.write_text(stra)
    docs = load_file(str(txt_file))
    docs1 = split_docs(docs, floor(len(stra)/2), floor(len(stra)/3))
    add_documents(docs1)
    results = search("姓名")
    assert len(results) >= 1
    assert any("姓名" in result.page_content for result in results)




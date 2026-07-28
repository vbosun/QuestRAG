import math
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:5001/v1/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-r1")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "bge-m3")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    # 绕过本地代理,避免访问本地服务失败(502)
    http_client=httpx.Client(trust_env=False),
)


def read_text_file(file_path: str) -> str:
    """ # 读取文本 """
    return Path(file_path).read_text("UTF-8")


def clean_text(text: str) -> str:
    """ 清洗文文本 """

    if not text:
        return ""

    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去掉不可见的控制字符
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 去掉行首行尾空格
    lines = [line.strip() for line in text.split("\n")]

    # 合并行内多个空格
    lines = [re.sub(r"[ \t]+", " ", line) for line in lines]

    # 合并多个空行
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 80) -> list[str]:
    """ 文本分块 """
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

        if start < 0:
            start = 0

    return chunks


def get_embedding(text: str) -> list[float]:
    """ 调用embedding 模型, 把文本变成向量 """
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text,
    )

    return response.data[0].embedding


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """
    手写余弦相似度
    计算两个向量方向的相似度, 等同于两个向量的夹角大小
    为啥是余弦, 因为在向量点积的计算中包含cosine, 与夹角等同
    比如 点积 dot = |A| * (|B| * cos θ ), θ 就是向量A,B的夹角,
    点积就是A的长度* B在A上的投影长度
    最后点积除掉AB的长度, 就是余弦值, 这样只保留了方向相似度, 剔除了长度的影响
    """
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def build_index(chunks: list[str]) -> list[dict]:
    """ 构建最小向量数据库 """
    index = []

    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk)
        index.append(
            {
                "id": f"chunk_{i}",
                "text": chunk,
                "embedding": embedding,
                "metadata": {
                    "chunk_index": i,
                }
            }
        )
    return index


def retrieve(query: str, index: list[dict], top_k: int) -> list[dict]:
    """ 根据问题检索top_k个相关的chunk """
    query_embedding = get_embedding(query)
    scored_results = []

    for item in index:
        score = cosine_similarity(query_embedding, item["embedding"])
        scored_results.append({
            "score": score,
            "text": item["text"],
            "metadata": item["metadata"],
        })

    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:top_k]


def extract_keywords(query: str) -> list[str]:
    """ 提取问题的关键词 """

    tokens = re.findall(r"[a-zA-Z_/\-.0-9]+|[\u4e00-\u9fff]+", query)

    keywords = []

    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            # 中文长句做简单 2 字滑窗
            if len(token) <= 2:
                keywords.append(token)
            else:
                for i in range(len(token) - 1):
                    keywords.append(token[i:i + 2])
        else:
            keywords.append(token)

    # 去重，保留顺序
    return list(dict.fromkeys(keywords))

def keyword_search(query: str, chunks: list[str], top_k: int = 3) -> list[dict]:
    """ 关键词匹配检索 """
    keywords = extract_keywords(query)
    results = []

    for i, chunk in enumerate(chunks):
        score = 0

        # 完整query命中
        if query in chunk:
            score += 20

        for kw in keywords:
            count = chunk.count(kw)
            if count > 0:
                score += count * 3

        if score > 0:
            results.append({
                "chunk_index": i,
                "score": score,
                "text": chunk,
                "matched_keywords": [kw for kw in keywords if kw in chunk],
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def merge_search_result(vector_results: list[dict], keyword_results: list[dict], top_k:int=3) -> list[dict]:
    """ 简单的向量检索和关键词检索结果合并"""
    merged = {}
    for item in vector_results:
        idx = item["metadata"]["chunk_index"]
        merged[idx] = {
            "text": item["text"],
            "vector_score": item["score"],
            "keyword_score": 0,
            "final_score": 0,
        }

    for item in keyword_results:
        idx = item["chunk_index"]
        if idx not in merged:
            merged[idx] = {
                "text": item["text"],
                "vector_score": 0,
                "keyword_score": item["score"],
                "final_score": 0,
            }

        merged[idx]["keyword_score"] = item["score"]

    for item in merged.values():
        item["final_score"] = (
                item["vector_score"] * 1.0
                + item["keyword_score"] * 0.1
        )

    final_results = sorted(
        merged.values(),
        key=lambda x: x["final_score"],
        reverse=True,
    )

    return final_results[:top_k]


def build_prompt(question: str, contexts: list[dict]) -> str:
    """ 构建RAG Prompt"""
    context_text = "\n\n".join(
        f"[片段:{i + 1} | score={ctx['final_score']:.4f}]\n{ctx['text']}"
        for i, ctx in enumerate(contexts)
    )

    return f"""
你是一个知识库问答助手. 
请值根据下面的资料回答用户问题.
如果资料中没有答案, 请回答: 资料中没有相关信息.

资料:
{context_text}

用户问题:
{question}

请给出回答: 
""".strip()


def ask_llm(prompt: str) -> str:
    """ 调用大模型生成答案"""
    user_msg: ChatCompletionUserMessageParam = {
        "role": "user",
        "content": prompt,
    }
    messages: list[ChatCompletionMessageParam] = [
        user_msg
    ]

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2
    )

    return response.choices[0].message.content


def main():
    file_path = "D:/MyDownload/111.txt"

    raw_text = read_text_file(file_path)
    cleaned_text = clean_text(raw_text)
    chunks = split_text(cleaned_text, chunk_size=500, chunk_overlap=80)

    print(f"原始文本长度: {len(raw_text)}")
    print(f"清理后文本长度: {len(cleaned_text)}")
    print(f"分块数量: {len(chunks)}")

    index = build_index(chunks)

    while True:
        question = input("\n请输入问题, 输入 q 退出: ").strip()
        if question.lower() == "q":
            break

        contexts = retrieve(question, index, top_k=3)
        print(f"\n检索结果:")
        for i, ctx in enumerate(contexts):
            print(f"\n[{i}] score=[{ctx['score']:.4f}]:")
            print(ctx['text'][:200])

        prompt = build_prompt(question, contexts)
        answer = ask_llm(prompt)

        print("\n回答: ")
        print(answer)


def main2():
    """对比文档不分块和分块"""
    file_path = "D:/MyDownload/111.txt"

    raw_text = read_text_file(file_path)
    cleaned_text = clean_text(raw_text)
    chunks = [cleaned_text]

    print(f"原始文本长度: {len(raw_text)}")
    print(f"清理后文本长度: {len(cleaned_text)}")
    print(f"分块数量: {len(chunks)}")

    index = build_index(chunks)

    while True:
        question = input("\n请输入问题, 输入 q 退出: ").strip()
        if question.lower() == "q":
            break

        contexts = retrieve(question, index, top_k=3)
        print(f"\n检索结果:")
        for i, ctx in enumerate(contexts):
            print(f"\n[{i}] score=[{ctx['score']:.4f}]:")
            print(ctx['text'][:200])

        prompt = build_prompt(question, contexts)
        answer = ask_llm(prompt)

        print("\n回答: ")
        print(answer)

def main3():
    """使用混合检索"""
    file_path = "D:/MyDownload/111.txt"

    raw_text = read_text_file(file_path)
    cleaned_text = clean_text(raw_text)
    chunks = split_text(cleaned_text, chunk_size=500, chunk_overlap=80)

    print(f"原始文本长度: {len(raw_text)}")
    print(f"清理后文本长度: {len(cleaned_text)}")
    print(f"分块数量: {len(chunks)}")

    index = build_index(chunks)

    while True:
        question = input("\n请输入问题, 输入 q 退出: ").strip()
        if question.lower() == "q":
            break

        vector_results = retrieve(question, index, top_k=3)
        keyword_results = keyword_search(question, chunks=chunks, top_k=3)

        contexts = merge_search_result(vector_results=vector_results, keyword_results=keyword_results, top_k=3)


        print(f"\n检索结果:")
        for i, ctx in enumerate(contexts):
            print(f"\n[{i}] score=[{ctx['final_score']:.4f}]:")
            print(ctx['text'][:200])

        prompt = build_prompt(question, contexts)
        answer = ask_llm(prompt)

        print("\n回答: ")
        print(answer)


if __name__ == '__main__':
    main3()

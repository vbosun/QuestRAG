import math
import re

from langchain_core.documents import Document

from quest_rag.rag.document_embedding import vector_store, get_embedding


def search(query: str, top_k=3) -> list[Document]:
    """向量相似度检索"""

    # 用户查询转为嵌入向量
    query_vector = get_embedding(query)

    # 向量检索
    vector_results = vector_search(query_vector, vector_store, top_k)

    # 关键词检索
    keywords_results = keyword_search(query, vector_store, top_k)

    # 合并两个检索的结果
    return [
        Document(
            page_content=result["text"],
            metadata={
                **result["metadata"],
                "score": result["score"],
                "vector_score": result["vector_score"],
                "keyword_score": result["keyword_score"],
            },
        )
        for result in merge_results(vector_results, keywords_results, top_k)
    ]


def vector_search(query_vector: list[float], chunks: list[dict], top_k=3) -> list[dict]:
    # 混合检索: 向量检索,关键词检索,合并两个结果,并排序
    # 向量检索: 余弦相似度排序
    vector_results = []
    for chunk in chunks:
        new_chunk = chunk.copy()
        new_chunk["score"] = cosine_similarity(query_vector, chunk["embedding"])
        vector_results.append(new_chunk)

    vector_results = sorted(
        vector_results,
        key=lambda x: x["score"],
        reverse=True
    )[:top_k]
    return vector_results


def keyword_search(query: str, chunks: list[dict], top_k=3) -> list[dict]:
    if not query:
        return []
    results = []

    # 对于每个chunk,如果匹配的关键词越多,分数越高
    keywords = extract_keywords(query)
    # 最大可能分
    max_score = 50 + len(keywords) * 35
    for chunk in chunks:
        score = 0
        text: str = chunk["text"]

        # 完整query命中
        if query in text:
            score += 50

        matched_keywords = []
        for kw in keywords:
            count = text.count(kw)
            if count > 0:
                matched_keywords.append(kw)
                score += 20
                score += min(count, 3) * 5

        if score > 0:
            new_chunk = chunk.copy()
            new_chunk["score"] = score / max_score  # 归一化
            new_chunk["matched_keywords"] = matched_keywords
            results.append(new_chunk)
    results = sorted(
        results,
        key=lambda x: x["score"],
        reverse=True
    )[:top_k]

    return results


def merge_results(vector_results, keywords_results, top_k) -> list[dict]:
    """合并向量检索和关键词检索的结果
    统一到一个最终分数=向量*0.6+关键词*0.4
    """
    final_results = {}
    for vr in vector_results:
        idx: str = vr["id"]
        final_results[idx] = {
            "text": vr["text"],
            "vector_score": vr["score"],
            "keyword_score": 0,
            "score": 0,
            "metadata":vr["metadata"]
        }

    for kr in keywords_results:
        idx: str = kr["id"]
        if idx not in final_results:
            final_results[idx] = {
                "text": kr["text"],
                "vector_score": 0,
                "keyword_score": kr["score"],
                "score": 0,
                "metadata": kr["metadata"]
            }
        else:
            final_results[idx]["keyword_score"] = kr["score"]

    # 统一计算最终分数
    results = []

    for item in final_results.values():
        item["score"] = (
                item["vector_score"] * 0.6
                +
                item["keyword_score"] * 0.4
        )

        results.append(item)

    candidates = final_results.values()
    # 优先关键词设置,放置关键词得分过低导致被过滤
    # if keywords_results:
    #     candidates = [
    #         result
    #         for result in candidates
    #         if result["keyword_score"] > 0
    #     ]

    # 排序取top_k
    results = sorted(candidates,
                     key=lambda x: x["score"],
                     reverse=True)[:top_k]

    return results


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


def extract_keywords(query: str) -> list[str]:
    """
    一个简单的提取问题的关键词的实现,
    提取英文,数字,至于汉字,按两个取为关键词
    """

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

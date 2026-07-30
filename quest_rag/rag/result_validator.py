from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from quest_rag.rag.llm import llm
from quest_rag.schemas.schemas import ValidationResult


def validate_search_result(results: list[Document]) -> list[Document]:
    if not results:
        return []

    ## 校验空文本
    results = [result
               for result in results
               if result.page_content.strip()]

    ## 校验重复chunk
    new_results = []
    text_set = set()
    for result in results:
        text: str = result.page_content.strip()
        if text in text_set:
            continue

        text_set.add(text.strip())
        new_results.append(result)

    return new_results


validator_llm = llm
# 使用结构化输出
validator_llm = validator_llm.with_structured_output(
    ValidationResult
)

# Prompt
validator_prompt = ChatPromptTemplate.from_template(
    """
    你是一个LLM回复结果校验助手。
    
    你的任务：
    根据用户问题、参考资料，判断AI生成回复是否正确。
    
    校验规则：
    
    1. 回复必须回答用户问题。
    2. 回复中的事实必须能被参考资料支持。
    3. 不允许使用参考资料之外的信息进行推测。
    4. 如果存在无法被资料支持的内容，则校验失败。
    
    
    ## 用户问题：
    
    {query}
    
    
    ## 参考资料：
    
    {context}
    
    
    ## AI生成回复：
    
    {answer}
    
    
    请进行判断。
    """
)

# Chain
validator_chain = (
        validator_prompt
        |
        validator_llm
)


# 调用接口
def validate_answer(
        query: str,
        context: str,
        answer: str
) -> ValidationResult:
    result = validator_chain.invoke(
        {
            "query": query,
            "context": context,
            "answer": answer
        }
    )

    return result

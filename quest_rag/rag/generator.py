"""
生成回复
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from quest_rag.config.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from quest_rag.rag.tools import tools

SYSTEM_PROMPT = """
你是一个好用的助手.帮助用户解决问题.
"""

checkpointer = InMemorySaver()
llm = ChatOpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=SecretStr(OPENAI_API_KEY),
    model=OPENAI_MODEL,
    temperature=0.5,
    max_completion_tokens=25000,
)


_agent = create_agent(
    model=llm, system_prompt=SYSTEM_PROMPT, tools=tools, checkpointer=checkpointer
)


def generate(question: str) -> str:
    result = _agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        {"configurable": {"thread_id": "1"}},
    )

    return result["messages"][-1].content

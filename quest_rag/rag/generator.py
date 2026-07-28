"""
生成回复
"""

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from quest_rag.rag.llm import llm
from quest_rag.rag.tools import tools

SYSTEM_PROMPT = """
你是一个好用的助手.帮助用户解决问题.
"""

checkpointer = InMemorySaver()

_agent = create_agent(
    model=llm, system_prompt=SYSTEM_PROMPT, tools=tools, checkpointer=checkpointer
)


def generate(question: str, thread_id: str = '1') -> str:
    result = _agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        {"configurable": {"thread_id": thread_id}},
    )

    return result["messages"][-1].content


def history(thread_id: str):
    state_snapshot = _agent.get_state({"configurable": {"thread_id": thread_id}})
    formatted_messages = [
        f"[{msg.type}]: {msg.content}" for msg in state_snapshot.values["messages"]
    ]
    return formatted_messages

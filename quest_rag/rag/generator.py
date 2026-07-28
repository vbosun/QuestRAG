"""
生成回复
"""

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from quest_rag.rag.llm import llm
from quest_rag.rag.tools import tools

SYSTEM_PROMPT = """
你是一个政务助手.帮助用户解决就业登记业务,失业登记业务问题,或者其他的可以从文档中获取到相关业务知识的问题.如果没有符合条件的资料,则拒绝回答,不要编造.
回复格式使用普通格式即可,不要使用markdown或者其他代码格式
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

from rag.embedding import add_documents
from rag.generator import generate
from rag.loader import load_file
from rag.splitter import split_docs


def chat_loop():
    """ 持续对话循环"""
    print("正在加载文档...")
    docs = load_file("D:/MyDownload/流动人员人事档案调函20260326144941.pdf")
    docs = split_docs(docs)
    add_documents(docs)

    print("🤖 QuestRAG 助手已启动！（输入 'quit' 退出）")
    while True:
        question = input("\n👤 你: ").strip()
        answer = generate(question)

        print(f"\n🤖 助手: {answer}")

if __name__ == "__main__":
    chat_loop()


import re


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
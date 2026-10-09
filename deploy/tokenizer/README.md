# 构建时缓存分词器

默认后端镜像构建会下载 DeepSeek-V3 分词器并存入 `/opt/questrag-tokenizer`，不下载生成模型权重。

若 Linux 无法访问 Hugging Face，可在联网机器使用同一锁定版本的 transformers：

```python
from transformers import AutoTokenizer
AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-V3", trust_remote_code=False).save_pretrained("deploy/tokenizer")
```

然后将生成的 tokenizer.json、tokenizer_config.json、special_tokens_map.json、chat_template.jinja 复制到部署机器的本目录，重新构建后端镜像。镜像构建将验证本地分词器可加载；运行时从 TOKENIZER_PATH 读取，不再下载。生成文件不提交 Git，不能复制任何密钥或模型权重。

统计沿用 DeepSeek-V3 分词器口径，供文档展示使用，不作为供应商账单依据。

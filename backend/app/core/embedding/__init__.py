"""向量化能力：独立接口 + 按配置选择的工厂。

实现：stub（无 Key 底线）/ hash（本地确定性兜底）/ openai_compat（任何 OpenAI
兼容 /embeddings 服务商）。调用方只 `get_embedder()`，不 import 对话 provider。
"""

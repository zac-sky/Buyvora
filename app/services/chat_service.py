"""Application logic for the first, deterministic shopping conversation flow."""


def build_shopping_reply(message: str) -> str:
    """Return a transparent placeholder reply until the LLM agent is introduced."""
    cleaned_message = message.strip()
    return f"我收到了你的购物需求：{cleaned_message}。下一步我会帮你分析商品类型和筛选条件。"

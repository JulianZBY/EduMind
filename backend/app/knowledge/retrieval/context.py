"""生成上下文组装：预算内命中分块优先完整保留，图谱知识点内容按剩余空间截断。"""

# 生成上下文总预算（字符）：命中片段优先，图谱节点内容在剩余空间内截断。
# 与生成 prompt 的知识窗口（knowledge[:6000]）对齐，保证图谱段不被下游二次截断。
CONTEXT_BUDGET_CHARS = 6000
_CHUNKS_HEADER = "=== 知识片段 ===\n"
_NODES_HEADER = "=== 图谱关联知识点（按知识递进） ===\n"


def chunks_only_context(chunks: list[str]) -> str:
    """仅命中分块的上下文（无图谱段）：纯向量档与图谱段降级时的形态。"""
    return "\n\n".join(c for c in chunks if c)


def assemble_context(
    chunks: list[str], nodes: list[dict], budget: int = CONTEXT_BUDGET_CHARS
) -> str:
    """预算内组装：命中片段优先完整保留，图谱节点内容按剩余空间截断。"""
    parts: list[str] = []
    used = 0

    chunk_block = "\n\n".join(c for c in chunks if c)
    if chunk_block:
        piece = (_CHUNKS_HEADER + chunk_block)[: budget - used]
        if piece:
            parts.append(piece)
            used += len(piece)

    if nodes and used < budget:
        # 预留段头与分段符（"\n\n".join），避免拼接后总量超出预算
        room = budget - used - len(_NODES_HEADER) - (2 if parts else 0)
        lines: list[str] = []
        used_lines = 0
        for n in nodes:
            sep = 2 if lines else 0
            line_room = room - used_lines - sep
            if line_room <= 0:
                break
            line = f"【{n['title']}】{n.get('content') or ''}"[:line_room]
            lines.append(line)
            used_lines += sep + len(line)
        if lines:
            parts.append(_NODES_HEADER + "\n\n".join(lines))
    return "\n\n".join(parts)

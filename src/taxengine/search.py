"""Full-text search over the knowledge base (offline SQLite FTS5)."""

from __future__ import annotations


def search(conn, query: str, entity_type: str | None = None, limit: int = 50) -> list:
    """Search rules, risks, legislation, evidence and procedures.

    Returns [{entity_type, entity_code, title, snippet}]. Empty query -> [].
    """
    query = (query or "").strip()
    if not query:
        return []
    sql = """SELECT entity_type, entity_code, title,
                    snippet(kb_fts, 3, '<b>', '</b>', '…', 24) AS snippet
             FROM kb_fts WHERE kb_fts MATCH ?"""
    params = [query]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]

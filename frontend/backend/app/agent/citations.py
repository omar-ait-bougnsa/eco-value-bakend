"""Provenance: the passages an answer cites become `citation` events, one per provenance chip in the chat."""
import re
from typing import Any
from uuid import uuid4

from .types import AgentEvent

MARKER = re.compile(r'[\[【]\s*(K\d+)\s*[\]】]')  # [K1], and 【K1】 as some models write it
EXCERPT_CHARS = 700


def cited(text: str, results: dict[str, dict[str, Any]]) -> tuple[str, list[AgentEvent]]:
    """The text with its `[K3]` markers renumbered `[1]`, `[2]`… in order of first use, and a `citation` event for each.

    `results` maps a ref to the search result it stands for. A marker with no result is dropped from the text.
    """
    order: list[str] = []
    for ref in MARKER.findall(text):
        if ref in results and ref not in order:
            order.append(ref)
    text = MARKER.sub(lambda m: f'[{order.index(m[1]) + 1}]' if m[1] in order else '', text)
    events = [
        AgentEvent(
            id=f'citation_{uuid4().hex[:8]}',
            type='citation',
            payload={
                'index': i,
                'label': r['label'],
                'source': r['source'],
                'date': r['date'],
                'page': r['page'],
                'section': r['section'],
                'passage': r['passage'],
                'relevanceScore': r['relevance_score'],
                'documentId': r['documentId'],
                'chunkId': r['chunkId'],
            },
        )
        for i, r in enumerate((results[ref] for ref in order), 1)
    ]
    return text, events


def knowledge_answer(results: list[dict[str, Any]]) -> str:
    """An answer made of the passages themselves, each behind its marker: no model, so nothing can be misquoted.

    The marker comes first: after a passage that ends in a table, Markdown would read it as one more cell.
    """
    if not results:
        return 'I found nothing about that in the indexed documents.'
    excerpt = lambda p: p if len(p) <= EXCERPT_CHARS else p[:EXCERPT_CHARS].rsplit(' ', 1)[0] + ' …'
    return 'Here is what the indexed documents say:\n\n' + '\n\n'.join(f'[{r["ref"]}] {excerpt(r["passage"])}' for r in results)

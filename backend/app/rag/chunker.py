"""Parsed blocks to chunks of 500–800 tokens with a 100-token overlap (RAG.md §4.2)."""
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .parser import Block, Parsed

MIN, TARGET, LIMIT, OVERLAP = 500, 650, 800, 100

# Words and punctuation marks: close to what an embedding model counts, the same on every machine, and no
# vocabulary file to download (tiktoken fetches its own on first use, which fails offline).
_TOKEN = re.compile(r'\w+|[^\w\s]')
# A line or a sentence, with the white space that follows it: joining the units gives the text back.
_UNIT = re.compile(r'.+?(?:\n\s*\n|\n|(?<=[.!?])\s+|\Z)', re.S)


def tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


@dataclass
class Chunk:
    content: str
    kind: str  # text | table
    page: Optional[int] = None
    page_end: Optional[int] = None  # when the chunk runs over several pages
    section: Optional[str] = None


def _units(text: str) -> list[str]:
    """Lines and sentences. One that is over the limit by itself is cut into runs of words."""
    out: list[str] = []
    for unit in _UNIT.findall(text.strip()):
        if tokens(unit) <= LIMIT:
            out.append(unit)
            continue
        run = ''
        for word in re.findall(r'\S+\s*', unit):
            if run and tokens(run + word) > LIMIT:
                out.append(run)
                run = ''
            run += word
        out.append(run)
    return out


def _text_chunks(blocks: list[Block]) -> list[Chunk]:
    """Chunks over the consecutive text blocks of one section (several pages of a PDF, for instance).

    A chunk ends at a paragraph once it has MIN tokens, at a sentence once it has TARGET, and always before LIMIT.
    The next one starts with the last sentences of the one before (up to OVERLAP tokens).
    """
    units: list[tuple[str, Optional[int]]] = []
    for block in blocks:
        for i, unit in enumerate(parts := _units(block.text)):
            units.append((unit.rstrip() + '\n\n' if i == len(parts) - 1 else unit, block.page))

    chunks: list[Chunk] = []
    current: list[tuple[str, Optional[int]]] = []
    carried = 0  # units at the start of `current` repeated from the chunk before

    def close() -> None:
        nonlocal current, carried
        chunks.append(Chunk(''.join(u for u, _ in current).strip(), 'text', page=current[carried][1], page_end=current[-1][1], section=blocks[0].section))
        tail: list[tuple[str, Optional[int]]] = []
        for unit in reversed(current[carried:]):
            if tokens(''.join(u for u, _ in [unit, *tail])) > OVERLAP:
                break
            tail.insert(0, unit)
        current, carried = tail, len(tail)

    for unit in units:
        size = tokens(''.join(u for u, _ in current))
        fresh = len(current) > carried
        if fresh and (size + tokens(unit[0]) > LIMIT or size >= TARGET or (size >= MIN and current[-1][0].endswith('\n\n'))):
            close()
        current.append(unit)
    if len(current) > carried:
        close()
    return chunks


def _markdown_table(header: list[str], rows: list[list[str]]) -> str:
    line = lambda cells: '| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ') for c in cells) + ' |'
    return '\n'.join([line(header), line(['---'] * len(header)), *map(line, rows)])


def _table_chunks(block: Block, preamble: str) -> list[Chunk]:
    """A table as Markdown under a sentence that says where it comes from. A long one is cut by rows, the header repeated."""
    header, body = block.rows[0], block.rows[1:]
    room = LIMIT - tokens(preamble) - tokens(_markdown_table(header, [])) - 10
    groups: list[list[list[str]]] = [[]]
    for row in body:
        if groups[-1] and tokens(_markdown_table([], [*groups[-1], row])) > room:
            groups.append([])
        groups[-1].append(row)
    chunks, start = [], 1
    for group in groups:
        rows = f' Rows {start}–{start + len(group) - 1} of {len(body)}.' if len(groups) > 1 else ''
        chunks.append(Chunk(f'{preamble}{rows}\n\n{_markdown_table(header, group)}', 'table', page=block.page, section=block.section))
        start += len(group)
    return chunks


def chunk_document(parsed: Parsed, *, title: str, doc_type: str, doc_date: Optional[date]) -> list[Chunk]:
    origin = f'{title} ({doc_type.replace("_", " ")}' + (f', dated {doc_date.isoformat()})' if doc_date else ')')
    chunks: list[Chunk] = []
    run: list[Block] = []  # consecutive text blocks of the same section

    def flush() -> None:
        if run:
            chunks.extend(_text_chunks(run))
            run.clear()

    for block in parsed.blocks:
        if block.rows:
            flush()
            where = f', “{block.section}”' if block.section else ''
            chunks.extend(_table_chunks(block, f'Table from {origin}{where}.'))
        else:
            if run and run[-1].section != block.section:
                flush()
            run.append(block)
    flush()
    return chunks

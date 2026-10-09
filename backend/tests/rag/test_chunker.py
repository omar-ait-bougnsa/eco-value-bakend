"""Chunking: 500–800 tokens, 100-token overlap, sections and pages kept, tables as Markdown."""
from datetime import date

from app.rag.chunker import LIMIT, MIN, OVERLAP, chunk_document, tokens
from app.rag.parser import Block, Parsed

sentence = lambda i, words=12: ' '.join([f'S{i}'] + ['word'] * (words - 2) + ['end.'])
paragraph = lambda start, n: ' '.join(sentence(i) for i in range(start, start + n))
chunked = lambda blocks: chunk_document(Parsed(blocks), title='Report', doc_type='market_report', doc_date=date(2026, 9, 24))


def test_text_chunks_are_500_to_800_tokens_and_overlap():
    text = '\n\n'.join(paragraph(i * 10, 10) for i in range(30))  # 300 sentences of 13 tokens
    chunks = chunked([Block(text=text, section='Outlook')])
    sizes = [tokens(c.content) for c in chunks]
    assert len(chunks) > 4
    assert max(sizes) <= LIMIT
    assert min(sizes[:-1]) >= MIN  # the last one holds what is left
    assert all(c.kind == 'text' and c.section == 'Outlook' for c in chunks)
    for before, after in zip(chunks, chunks[1:]):
        # The next chunk opens with the last sentences of the one before: whole sentences, at most OVERLAP tokens.
        shared = next(n for n in range(len(after.content), 0, -1) if before.content.endswith(after.content[:n]))
        repeated = after.content[:shared]
        assert repeated.startswith('S') and repeated.rstrip().endswith('end.')
        assert 0 < tokens(repeated) <= OVERLAP
    # Nothing is lost: every sentence is in some chunk.
    assert all(any(f'S{i} ' in c.content for c in chunks) for i in range(300))


def test_a_chunk_ends_at_a_paragraph_when_it_can():
    text = '\n\n'.join(paragraph(i * 10, 10) for i in range(30))
    for c in chunked([Block(text=text)])[:-1]:
        assert int(c.content.rsplit('S', 1)[1].split()[0]) % 10 == 9  # the last sentence of a paragraph


def test_sections_are_not_mixed_and_a_chunk_has_the_page_it_starts_on():
    blocks = [Block(text=paragraph(0, 30), page=1), Block(text=paragraph(100, 30), page=2), Block(text=paragraph(200, 30), page=3),
              Block(text='A short note.', page=3, section='Annex')]
    chunks = chunked(blocks)
    assert chunks[-1].content == 'A short note.' and chunks[-1].section == 'Annex' and chunks[-1].page == 3
    body = chunks[:-1]
    assert [c.page for c in body] == sorted(c.page for c in body) and {c.page for c in body} >= {1, 2}
    assert body[1].content.startswith('S') and 'Annex' not in {c.section for c in body}
    # The page is that of the first new sentence, not of the sentences repeated from the chunk before.
    first_new = next(s for s in body[1].content.split('end.') if s.strip() and s.strip() not in body[0].content)
    assert body[1].page == (1 if int(first_new.split()[0][1:]) < 100 else 2)
    assert all(c.page_end >= c.page for c in body) and any(c.page_end > c.page for c in body)


def test_a_sentence_longer_than_the_limit_is_cut():
    chunks = chunked([Block(text=' '.join(['word'] * 2000) + '.')])
    assert len(chunks) >= 3 and max(tokens(c.content) for c in chunks) <= LIMIT


def test_a_table_is_markdown_under_a_sentence_that_says_where_it_is_from():
    rows = [['Product', 'Low USD/t', 'High USD/t'], ['TSP', '645', '668'], ['DAP | granular', '815', '850']]
    [chunk] = chunked([Block(rows=rows, section='FOB Morocco')])
    assert chunk.kind == 'table' and chunk.section == 'FOB Morocco'
    assert chunk.content.splitlines() == [
        'Table from Report (market report, dated 2026-09-24), “FOB Morocco”.',
        '',
        '| Product | Low USD/t | High USD/t |',
        '| --- | --- | --- |',
        '| TSP | 645 | 668 |',
        '| DAP \\| granular | 815 | 850 |',
    ]


def test_a_long_table_is_cut_by_rows_with_the_header_repeated():
    rows = [['Week', 'Route', 'USD/t']] + [[f'2026-W{i:03d}', 'Jorf Lasfar – Santos', str(20 + i)] for i in range(400)]
    chunks = chunked([Block(rows=rows)])
    assert len(chunks) > 3 and max(tokens(c.content) for c in chunks) <= LIMIT
    assert all('| Week | Route | USD/t |' in c.content for c in chunks)
    assert chunks[0].content.startswith('Table from Report (market report, dated 2026-09-24). Rows 1–')
    assert chunks[-1].content.splitlines()[0].endswith('–400 of 400.')
    assert sum(c.content.count('Jorf Lasfar') for c in chunks) == 400

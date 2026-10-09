"""Ingestion: text and tables out of each supported format."""
from datetime import date

import pytest

from app.rag.parser import UnreadableFile, UnsupportedFile, classify, date_in_name, parse


def test_workbook_sheets_become_tables(sample):
    parsed = parse('freights.xlsx', sample('fertilizer-week-historical-freights-01-10-2026.xlsx'))
    assert [b.section for b in parsed.blocks] == ['Phosphates', 'Sulphur']
    phosphates = parsed.blocks[0].rows
    assert phosphates[0] == ['Week ending', 'Route', 'Cargo (kt)', 'USD/t']
    assert phosphates[1] == ['2026-09-17', 'Jorf Lasfar – Santos', '30', '24.5']
    assert phosphates[2][3] == '25'  # the cell holds 25.0
    assert parsed.pages is None and all(not b.text for b in parsed.blocks)


def test_csv_with_semicolons_and_a_byte_order_mark():
    parsed = parse('prices.csv', '﻿crop;usd_per_t\nmaize;212\n\nwheat;248;\n'.encode('utf-8'))
    assert parsed.blocks[0].rows == [['crop', 'usd_per_t'], ['maize', '212'], ['wheat', '248']]


def test_markdown_is_cut_at_headings_and_keeps_their_path():
    text = '# Carbon methodology\n\nIntro.\n\n## Scope\n\nScopes 1 to 3.\n\n```\n# not a heading\n```\n\n### Baseline\n\n40 USD per t.\n\n## Value sharing\n\nOne third.\n'
    parsed = parse('carbon.md', text.encode())
    assert parsed.title == 'Carbon methodology'
    assert [(b.section, b.text.splitlines()[0]) for b in parsed.blocks] == [
        (None, 'Intro.'), ('Scope', 'Scopes 1 to 3.'), ('Scope › Baseline', '40 USD per t.'), ('Value sharing', 'One third.'),
    ]
    assert '# not a heading' in parsed.blocks[1].text
    # Without a title, the first heading is a section like any other.
    untitled = parse('notes.md', b'## Scope\n\nScopes 1 to 3.\n\n### Baseline\n\n40 USD per t.\n')
    assert untitled.title is None and [b.section for b in untitled.blocks] == ['Scope', 'Scope › Baseline']


def test_docx_headings_paragraphs_and_tables(docx):
    p = lambda text, style='': f'<w:p>{f"<w:pPr><w:pStyle w:val={chr(34)}{style}{chr(34)}/></w:pPr>" if style else ""}<w:r><w:t>{text}</w:t></w:r></w:p>'
    cell = lambda text: f'<w:tc>{p(text)}</w:tc>'
    table = f'<w:tbl><w:tr>{cell("Route")}{cell("USD/t")}</w:tr><w:tr>{cell("Jorf Lasfar – Santos")}{cell("25")}</w:tr></w:tbl>'
    parsed = parse('note.docx', docx(p('Freight outlook', 'Heading1') + p('Rates eased in September.') + table))
    assert [(b.section, b.text, b.rows) for b in parsed.blocks] == [
        ('Freight outlook', 'Rates eased in September.', []),
        ('Freight outlook', '', [['Route', 'USD/t'], ['Jorf Lasfar – Santos', '25']]),
    ]


def test_pdf_text_by_page(pdf):
    parsed = parse('report.pdf', pdf([['Freight rates eased', 'in the Atlantic basin.'], [], ['Sulphur (Middle East) stayed firm.']]))
    assert parsed.pages == 3
    # Lines of a page are one paragraph; the empty page gives no block but keeps its number.
    assert [(b.page, b.text) for b in parsed.blocks] == [(1, 'Freight rates eased in the Atlantic basin.'), (3, 'Sulphur (Middle East) stayed firm.')]


@pytest.mark.parametrize('name, data, error, says', [
    ('prices.xls', b'\xd0\xcf\x11\xe0', UnsupportedFile, 'save the file as .xlsx'),
    ('photo.png', b'\x89PNG', UnsupportedFile, 'Only .pdf'),
    ('broken.xlsx', b'\x00' * 2048, UnreadableFile, 'could not be read'),
    ('broken.pdf', b'not a pdf at all', UnreadableFile, 'could not be read'),
    ('empty.txt', b'  \n ', UnreadableFile, 'No text found'),
])
def test_files_that_cannot_be_indexed(name, data, error, says):
    with pytest.raises(error, match=says):
        parse(name, data)


def test_a_pdf_without_text_asks_for_ocr(pdf):
    with pytest.raises(UnreadableFile, match='OCR'):
        parse('scan.pdf', pdf([[], []]))


@pytest.mark.parametrize('name, kind, dated', [
    ('argus-fob-morocco-30-09-2026.xlsx', 'market_report', date(2026, 9, 30)),
    ('fertilizer-week-historical-prices-averages-01-10-2026.xlsx', 'market_report', date(2026, 10, 1)),
    ('fertilizer-week-historical-freights-01-10-2026.xlsx', 'freight', date(2026, 10, 1)),
    ('agro-trials-phosfusion-2026-09-15.xlsx', 'agronomy', date(2026, 9, 15)),
    ('crop-prices-2026-10-01.csv', 'market_report', date(2026, 10, 1)),
    ('holiday-photos.txt', 'other', None),
    ('notes-31-02-2026.txt', 'other', None),  # not a date
])
def test_kind_and_date_from_the_filename(name, kind, dated):
    assert classify(name, '') == kind
    assert date_in_name(name) == dated


def test_kind_from_the_text_when_the_name_says_nothing():
    assert classify('document.pdf', 'This supply agreement sets the offtake volumes and the Incoterm for each clause.') == 'contract'
    assert classify('document.pdf', 'Carbon valuation methodology: Scope 1 to Scope 3, and the CBAM rules.') == 'methodology'
    assert classify('value-sharing-note.md', 'The share of the agronomic value kept by the producer.') == 'methodology'  # "value sharing", across the hyphen
    # The filename counts more than a few words of the text.
    assert classify('freight-note.pdf', 'Prices and market quotes were stable.') == 'freight'

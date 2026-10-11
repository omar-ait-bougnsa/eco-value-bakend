"""The knowledge base: seeding, cosine-similarity search, and what happens when the model changes or fails."""
from unittest.mock import patch

from sqlalchemy import func, select

from app import rag
from app.db import DocumentChunkRow, DocumentRow
from app.rag.embeddings import EmbeddingError, HashEmbedder

FREIGHTS = 'fertilizer-week-historical-freights-01-10-2026.xlsx'
count = lambda s, table: s.scalar(select(func.count()).select_from(table))


def test_an_empty_knowledge_base_is_loaded_with_the_documents_that_ship(store):
    rag.prepare(store.db)
    docs = {d.name: d for d in rag.documents(store.db)}
    assert {name: d.type for name, d in docs.items()} == {
        'agro-trials-phosfusion-2026-09-15.xlsx': 'agronomy',
        'argus-fob-morocco-08-10-2026.xlsx': 'market_report',
        'argus-fob-morocco-30-09-2026.xlsx': 'market_report',
        'crop-prices-2026-10-01.csv': 'market_report',
        'fertilizer-week-historical-freights-01-10-2026.xlsx': 'freight',
        'fertilizer-week-historical-prices-averages-01-10-2026.xlsx': 'market_report',
        'engine.md': 'methodology',
    }
    assert all(d.status == 'ready' and d.seeded and d.chunks >= 1 for d in docs.values())
    assert docs[FREIGHTS].chunks == 2 and str(docs[FREIGHTS].date) == '2026-10-01'  # one table per sheet
    assert docs['engine.md'].title.startswith('Eco Value Simulator — Engine Specification') and docs['engine.md'].chunks > 10
    assert count(store.db, DocumentChunkRow) == count(store.db, select(DocumentChunkRow).where(DocumentChunkRow.embeddingModel == 'hash-1536').subquery())

    rag.prepare(store.db)  # a restart
    assert len(rag.documents(store.db)) == 7


def test_search_ranks_by_cosine_similarity_and_says_where_each_passage_is_from(store):
    rag.prepare(store.db)
    results = rag.search(store.db, 'freight rate from Jorf Lasfar to Santos')
    top = results[0]
    assert (top.source, top.section, top.docType, str(top.date)) == (FREIGHTS, 'Phosphates', 'freight', '2026-10-01')
    assert top.label == f'{FREIGHTS}, 01-Oct-2026, Phosphates'
    assert '| 2026-10-01 | Jorf Lasfar – Santos | 30 | 25.5 |' in top.passage
    scores = [r.relevanceScore for r in results]
    assert scores == sorted(scores, reverse=True) and 0 < scores[-1] <= scores[0] <= 1

    assert rag.search(store.db, 'yield gain of maize in the field trials')[0].docType == 'agronomy'
    assert rag.search(store.db, 'Reference-Minus pricing method', doc_type='methodology')[0].source.startswith('Eco Value Simulator')
    assert len(rag.search(store.db, 'price', limit=2)) == 2


def test_the_kind_filter_and_questions_with_no_answer(store):
    rag.prepare(store.db)
    assert {r.docType for r in rag.search(store.db, 'TSP FOB Morocco price', doc_type='market_report', limit=8)} == {'market_report'}
    assert rag.search(store.db, 'freight Jorf Lasfar Santos', doc_type='agronomy') == []
    assert rag.search(store.db, 'holiday weather forecast in Paris') == []  # nothing in common with any passage
    assert rag.search(store.db, 'the of and what') == []  # nothing but stop words


def test_a_pdf_is_found_by_its_text_and_cited_by_page(store, pdf):
    data = pdf([['Phosphate market summary for the week.'], ['Morocco to Brazil supramax freight eased on surplus vessel tonnage in the Atlantic basin.']])
    doc = rag.add_document(store.db, 'cru-fertilizer-week-2026-09-24.pdf', data, title='CRU Fertilizer Week')
    assert (doc.status, doc.pages, doc.type, str(doc.docDate)) == ('indexing', 2, 'market_report', '2026-09-24')
    assert rag.search(store.db, 'supramax vessel tonnage Atlantic') == []  # not embedded yet
    assert rag.embed(store.db, [doc.id]) == 1  # two short pages make one chunk
    top = rag.search(store.db, 'supramax vessel tonnage Atlantic')[0]
    assert top.label == 'CRU Fertilizer Week, 24-Sep-2026, p.1–2'  # and it is cited by both
    assert top.passage == 'Phosphate market summary for the week.\n\nMorocco to Brazil supramax freight eased on surplus vessel tonnage in the Atlantic basin.'

    long = rag.add_document(store.db, 'outlook.pdf', pdf([[f'Page one sentence {i} about potash.' for i in range(120)], [f'Page two sentence {i} about ammonia.' for i in range(120)]]))
    rag.embed(store.db, [long.id])
    assert rag.search(store.db, 'ammonia sentence 100')[0].label == 'outlook.pdf, p.2'


def test_the_same_file_is_stored_once_and_deleting_removes_its_chunks(store, sample):
    data = sample(FREIGHTS)
    first = rag.add_document(store.db, FREIGHTS, data)
    again = rag.add_document(store.db, 'renamed.xlsx', data, title='Other title')
    assert again.id == first.id and again.name == FREIGHTS
    assert (count(store.db, DocumentRow), count(store.db, DocumentChunkRow)) == (1, 2)

    assert rag.delete_document(store.db, first.id) is True
    assert (count(store.db, DocumentRow), count(store.db, DocumentChunkRow)) == (0, 0)
    assert rag.delete_document(store.db, first.id) is False


class OtherModel(HashEmbedder):
    """Another model: same texts, different vectors."""
    name = 'other-model'

    def _one(self, text):
        return super()._one(text)[::-1]


def test_vectors_of_another_model_are_not_searched_until_they_are_computed_again(store):
    rag.prepare(store.db)
    question = 'freight rate from Jorf Lasfar to Santos'
    before = rag.search(store.db, question)[0]
    with patch('app.rag.index.get_embedder', return_value=OtherModel()):
        assert rag.search(store.db, question) == []  # every stored vector is from hash-1536
        rag.prepare(store.db)  # a restart with the new model computes them again
        after = rag.search(store.db, question)[0]
        assert (after.chunkId, after.relevanceScore) == (before.chunkId, before.relevanceScore)
        assert store.db.scalar(select(func.count(func.distinct(DocumentChunkRow.embeddingModel)))) == 1
    assert rag.search(store.db, question) == []  # and back: the vectors are now the other model's


def test_a_document_that_cannot_be_embedded_is_marked_failed_and_the_others_go_through(store, sample):
    class Flaky(HashEmbedder):
        def embed(self, texts):
            if any('Jorf Lasfar' in t for t in texts):
                raise EmbeddingError('Embedding request to openrouter.ai failed: timed out')
            return super().embed(texts)

    freights = rag.add_document(store.db, FREIGHTS, sample(FREIGHTS))
    crops = rag.add_document(store.db, 'crop-prices-2026-10-01.csv', sample('crop-prices-2026-10-01.csv'))
    with patch('app.rag.index.get_embedder', return_value=Flaky()):
        assert rag.embed(store.db) == 1
    status = {d.id: (d.status, d.error) for d in rag.documents(store.db)}
    assert status[crops.id] == ('ready', None)
    assert status[freights.id] == ('failed', 'Embedding request to openrouter.ai failed: timed out')
    assert rag.search(store.db, 'freight Jorf Lasfar Santos') == []
    assert rag.embed(store.db, [freights.id]) == 2  # the network is back
    assert rag.search(store.db, 'freight Jorf Lasfar Santos')[0].documentId == freights.id


def test_a_setting_that_cannot_work_does_not_stop_the_start(store):
    with patch('app.rag.index.get_embedder', side_effect=EmbeddingError('EMBEDDINGS=cloud needs OPENAI_API_KEY or an OpenRouter key')):
        rag.prepare(store.db)
    assert len(rag.documents(store.db)) == 7 and all(d.status == 'indexing' for d in rag.documents(store.db))
    rag.prepare(store.db)
    assert all(d.status == 'ready' for d in rag.documents(store.db))

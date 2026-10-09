# Eco Value Simulator — RAG Architecture Specification (`evs.rag`)

## 1. Architectural Philosophy & Dual-Path Data Model

> **Core Axiom:** *Exact numbers live in SQL. Narrative knowledge and commentary live in the Vector Store. The LLM bridges them with verified citations.*

In commodity pricing and agronomy simulation, generic vector search cannot replace transactional databases because mathematical formulas require zero-tolerance numeric precision. The architecture strictly enforces a **Dual-Path Data Model**:

```
                              ┌─────────────────────────────────────────────────────────┐
                              │                    USER / AGENT TURN                    │
                              └────────────────────────────┬────────────────────────────┘
                                                           │
                      ┌────────────────────────────────────┴────────────────────────────────────┐
                      ▼                                                                         ▼
        [ EXACT NUMERICAL PATH ]                                                  [ NARRATIVE KNOWLEDGE PATH ]
  ┌───────────────────────────────────┐                                     ┌───────────────────────────────────┐
  │   PostgreSQL Relational Tables    │                                     │     Vector Database (pgvector)    │
  ├───────────────────────────────────┤                                     ├───────────────────────────────────┤
  │ • Argus Spot & Benchmark Quotes   │                                     │ • Argus Market Commentary         │
  │ • Recipe & Nutrient Specs (N,P,S) │                                     │ • CRU Freight Market Reports      │
  │ • Production & Logistics Costs    │                                     │ • Agronomic Field Trial Studies   │
  │ • Simulation Run Versions (v1..n) │                                     │ • Carbon Credit & CBAM Rules      │
  └─────────────────┬─────────────────┘                                     └─────────────────┬─────────────────┘
                    │                                                                         │
                    ▼                                                                         ▼
     [ app.engine Calculation ]                                                [ app.agent Knowledge Search ]
  (CostPlus, RefMinus, Margins)                                                (Source Citations & Provenance)
                    │                                                                         │
                    └────────────────────────────────────┬────────────────────────────────────┘
                                                         │
                                                         ▼
                                       [ Grounded Response + Provenance Chips ]
```

---

## 2. Target Ingestion Sources

### 2.1 Pre-Seeded Datasets (`sample-uploads/`)
1. **Market Price Reports:**
   - *Argus Phosphates Weekly* (FOB Morocco, CFR Brazil, Saudi export benchmarks).
   - Historical monthly series and forward curves.
2. **Freight & Supply Chain Reports:**
   - *CRU Fertilizer Week* (Morocco $\to$ Brazil Handysize shipping rates, fuel surcharges).
3. **Agronomic Research & Trials:**
   - Field trial papers establishing yield gain benchmarks ($12\%$ to $15\%$) for TSP vs Phosfusion across acid savanna soils (Cerrado).
4. **Internal Guidelines & Methodologies:**
   - OCP Value Sharing policies ($33.3\%$ default value share).
   - Carbon valuation methodology (\$40/t $\text{CO}_2$ baseline, Scope 1-3 definitions).

### 2.2 User Dynamic Uploads (`POST /api/uploads`)
- Formats supported: **PDF**, **XLSX**, **CSV**, **DOCX**, **TXT**.
- Automatic document classification: `market_report`, `freight`, `agronomy`, `contract`, `other`.

---

## 3. Technology Stack & Storage Architecture

### 3.1 Recommended Vector Store: `pgvector` inside PostgreSQL 17
Since the project already runs **PostgreSQL 17** in Docker (`ecoapp-db-1`), using `pgvector` provides major advantages:
* **Zero Extra Containers:** No separate ChromaDB, Qdrant, or Pinecone instances to orchestrate.
* **ACID Transactions & Joins:** Embeddings link directly to the existing `uploads` and `products` tables via foreign keys.
* **HNSW / IVFFlat Indexing:** Sub-millisecond cosine similarity search across tens of thousands of chunks.

### 3.2 Embedding Model Strategy
1. **Primary Cloud Model:** `text-embedding-3-small` (1536 dimensions) via OpenRouter or OpenAI.
   - High semantic fidelity, low latency, extremely low cost (\$0.02 / 1M tokens).
2. **Local Fallback Option:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) running locally via `fastembed` or `sentence-transformers`.
   - 100% offline development resilience when internet or API keys are unavailable.

---

## 4. Pipeline Design: Chunking, Storage, and Retrieval

```
[ Uploaded Document (PDF/XLSX) ]
               │
               ▼
   [ Text & Table Extraction ] ── (Extract text, headers, table summaries, metadata)
               │
               ▼
     [ Semantic Chunking ]    ── (500–800 tokens, 100 token overlap, preserve section hierarchy)
               │
               ▼
     [ Vector Embeddings ]    ── (Batch embedding generation with OpenRouter / fastembed)
               │
               ▼
    [ PostgreSQL + pgvector ] ── (Store chunks, vector embeddings, document provenance)
```

### 4.1 Relational Schema (`app/db.py`)

```python
# Conceptual schema for document chunks with embeddings
class DocumentChunk(Base):
    __tablename__ = 'document_chunks'

    id = Column(String, primary_key=True)                 # UUID
    upload_id = Column(String, ForeignKey('uploads.id'))   # Link to uploaded file record
    doc_title = Column(String, nullable=False)            # e.g., "Argus Phosphates Weekly"
    doc_type = Column(String, nullable=False)             # market_report | freight | agronomy
    doc_date = Column(Date, nullable=True)                # e.g., 2026-09-24
    page_number = Column(Integer, nullable=True)          # Page number in original PDF
    section_title = Column(String, nullable=True)         # Header/topic
    content = Column(Text, nullable=False)                # Chunk text
    metadata_json = Column(JSON, default=dict)            # Custom attributes
    embedding = Column(Vector(1536))                      # pgvector column
```

### 4.2 Chunking Strategy
- **Text Passages:** Recursive character splitting targeting 500–800 tokens with 100-token overlap to maintain sentence boundaries.
- **Tables & Quotes:** Tabular market price tables are converted into markdown summaries (e.g., `| Product | Benchmark | Low | High | Unit |`) with an accompanying contextual preamble describing the report date.

---

## 5. Agent Tool Specification: `search_knowledge`

A new high-priority tool is added to [`app/agent/tools.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/tools.py):

### Tool Definition
```python
def search_knowledge(
    query: str,
    doc_type: Optional[Literal['market_report', 'freight', 'agronomy', 'methodology']] = None,
    limit: int = 4,
) -> dict:
    """Search uploaded reports, market commentary, freight indices, and agronomic field trial papers.
    
    Use this tool whenever explaining WHY a price, freight rate, or yield assumption was chosen,
    or when citing source documentation.
    """
```

### Returned Fact Structure
```json
{
  "results": [
    {
      "passage": "Morocco to Brazil freight rates eased to $23.00/t for 45-50k mt supramax vessels due to surplus vessel tonnage in the Atlantic basin.",
      "source": "CRU Fertilizer Week",
      "date": "2026-09-24",
      "page": 4,
      "relevance_score": 0.89
    }
  ]
}
```

### Server-Side Grounding Integration ([`app/agent/checker.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/checker.py))
The numeric grounding checker validates that:
1. If the LLM mentions a report name or date, that document exists in the retrieved chunks.
2. If the LLM quotes a market statement, the phrasing matches the retrieved passage without hallucinating facts.
3. Every cited claim renders a **Provenance Chip** in the chat UI:
   `[Source: CRU Fertilizer Week, 24-Sep-2026, p.4]`

---

## 6. API Endpoints (`backend/app/routers/rag.py`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| **`POST`** | `/api/knowledge/search` | Direct semantic search endpoint for debugging and UI global search. |
| **`GET`** | `/api/knowledge/documents` | Lists all indexed documents, page counts, and chunk totals. |
| **`POST`** | `/api/knowledge/reindex` | Triggers a full re-embedding of seeded and uploaded documents. |
| **`DELETE`**| `/api/knowledge/documents/{id}`| Deletes a document and cascades deletion of its vector embeddings. |

---

## 7. Step-by-Step Implementation Roadmap

### Phase 1: Database Setup & Dependencies
1. Add `pgvector` extension to PostgreSQL in `docker-compose.yml` or container startup script.
2. Add dependencies to `requirements.txt`:
   - `pgvector>=0.3.0`
   - `pypdf>=4.0` (lightweight PDF parsing)
   - `openpyxl>=3.1` (Excel reading)
   - `tiktoken>=0.7` (token counting)
3. Create `DocumentChunk` table in [`app/db.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/db.py).

### Phase 2: Ingestion & Document Parsing Module
1. Create `backend/app/rag/parser.py`:
   - Extract text & tables from PDF and Excel files.
2. Create `backend/app/rag/chunker.py`:
   - Split extracted content into semantic chunks with metadata preservation.
3. Create `backend/app/rag/embeddings.py`:
   - Generate embeddings using OpenRouter embedding endpoint or local fallback.

### Phase 3: Seeding & Upload Hook
1. Build a startup seed loader for `sample-uploads/` so default reports are indexed automatically on first boot.
2. Connect `POST /api/uploads` so new uploaded documents are parsed and indexed asynchronously.

### Phase 4: Agent Tool & Provenance UI Events
1. Register `search_knowledge` tool in [`app/agent/tools.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/tools.py).
2. Add knowledge retrieval prompt instructions in the agent system prompt.
3. Emit `citation` events through the existing SSE stream ([`app/routers/agent.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/routers/agent.py)).
4. Write pytest suites in `tests/rag/` to verify ingestion, cosine similarity search, and citation generation.


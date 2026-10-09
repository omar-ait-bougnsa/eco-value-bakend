"""Database engine and tables.

Python attribute names are camelCase so rows map straight onto the API models in `schemas.py`;
the columns themselves are snake_case.
"""
import os
from datetime import date, datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DDL, JSON, DateTime, ForeignKey, Index, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://eco:eco@localhost:5432/eco')

if ':memory:' in DATABASE_URL:  # tests: one shared connection, or every session would see an empty database
    engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False}, poolclass=StaticPool)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(engine, expire_on_commit=False)

# json, not jsonb: jsonb reorders object keys, and key order carries meaning here (recipe lines, products of a run).
Json = JSON()

# Embeddings are a pgvector column. SQLite (the tests) has no vector type and keeps them as JSON.
EMBEDDING_DIM = 1536
Embedding = Vector(EMBEDDING_DIM).with_variant(JSON(), 'sqlite')


class Base(DeclarativeBase):
    pass


event.listen(Base.metadata, 'before_create', DDL('CREATE EXTENSION IF NOT EXISTS vector').execute_if(dialect='postgresql'))


class ProductRow(Base):
    __tablename__ = 'products'
    id: Mapped[str] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(index=True)
    name: Mapped[str]
    family: Mapped[str]
    recipe: Mapped[dict] = mapped_column(Json)
    composition: Mapped[dict] = mapped_column(Json)
    pcf: Mapped[Optional[float]]
    pcfPlaceholder: Mapped[Optional[bool]] = mapped_column('pcf_placeholder')
    appRate: Mapped[Optional[float]] = mapped_column('app_rate')
    yieldGain: Mapped[Optional[float]] = mapped_column('yield_gain')


class SnapshotRow(Base):
    __tablename__ = 'snapshots'
    id: Mapped[str] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(index=True)
    label: Mapped[str]
    asOf: Mapped[date] = mapped_column('as_of')
    inputs: Mapped[dict] = mapped_column(Json)
    refPrices: Mapped[dict] = mapped_column('ref_prices', Json)
    source: Mapped[str]


class UploadRow(Base):
    __tablename__ = 'uploads'
    id: Mapped[str] = mapped_column(primary_key=True)
    createdAt: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), index=True)
    name: Mapped[str]
    type: Mapped[str]
    uploadedAt: Mapped[date] = mapped_column('uploaded_at')
    fileDate: Mapped[date] = mapped_column('file_date')
    dataThrough: Mapped[date] = mapped_column('data_through')
    detail: Mapped[Optional[str]]


class ParametersRow(Base):
    """Single row (id = 1)."""
    __tablename__ = 'parameters'
    id: Mapped[int] = mapped_column(primary_key=True)
    costPlusMargin: Mapped[float] = mapped_column('cost_plus_margin')
    fullCost: Mapped[bool] = mapped_column('full_cost')
    valueShare: Mapped[float] = mapped_column('value_share')
    marketingPct: Mapped[float] = mapped_column('marketing_pct')
    dnaPerTon: Mapped[float] = mapped_column('dna_per_ton')
    marketShare: Mapped[float] = mapped_column('market_share')
    rampTargetYear: Mapped[int] = mapped_column('ramp_target_year')
    priceType: Mapped[str] = mapped_column('price_type')
    carbonMarket: Mapped[str] = mapped_column('carbon_market')
    freshnessMonths: Mapped[float] = mapped_column('freshness_months')
    staleDays: Mapped[int] = mapped_column('stale_days')
    defaultReference: Mapped[str] = mapped_column('default_reference')


class SimulationRow(Base):
    __tablename__ = 'simulations'
    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    createdAt: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), index=True)
    runs: Mapped[list['RunRow']] = relationship(order_by='RunRow.version', cascade='all, delete-orphan')


class RunRow(Base):
    __tablename__ = 'runs'
    __table_args__ = (UniqueConstraint('simulation_id', 'version'),)
    id: Mapped[str] = mapped_column(primary_key=True)
    simulationId: Mapped[str] = mapped_column('simulation_id', ForeignKey('simulations.id', ondelete='CASCADE'), index=True)
    version: Mapped[int]
    input: Mapped[dict] = mapped_column(Json)
    output: Mapped[dict] = mapped_column(Json)
    createdAt: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True))
    createdBy: Mapped[str] = mapped_column('created_by')
    summary: Mapped[str]
    changed: Mapped[list] = mapped_column(Json)
    editedKeys: Mapped[list] = mapped_column('edited_keys', Json)
    productSig: Mapped[dict] = mapped_column('product_sig', Json)


class DocumentRow(Base):
    """A file indexed for knowledge search (RAG.md). Its text is in `document_chunks`."""
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(primary_key=True)
    uploadId: Mapped[Optional[str]] = mapped_column('upload_id', ForeignKey('uploads.id', ondelete='CASCADE'), index=True)
    name: Mapped[str]  # filename
    title: Mapped[str] = mapped_column('doc_title')
    type: Mapped[str] = mapped_column('doc_type', index=True)
    docDate: Mapped[Optional[date]] = mapped_column('doc_date')
    pages: Mapped[Optional[int]]
    sha256: Mapped[str] = mapped_column(index=True)
    seeded: Mapped[bool]
    status: Mapped[str]  # indexing | ready | failed
    error: Mapped[Optional[str]]
    createdAt: Mapped[datetime] = mapped_column('created_at', DateTime(timezone=True), index=True)
    chunks: Mapped[list['DocumentChunkRow']] = relationship(order_by='DocumentChunkRow.position')


class DocumentChunkRow(Base):
    __tablename__ = 'document_chunks'
    __table_args__ = (
        Index('ix_document_chunks_embedding', 'embedding', postgresql_using='hnsw',
              postgresql_ops={'embedding': 'vector_cosine_ops'}).ddl_if(dialect='postgresql'),
    )
    id: Mapped[str] = mapped_column(primary_key=True)
    documentId: Mapped[str] = mapped_column('document_id', ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    position: Mapped[int]
    pageNumber: Mapped[Optional[int]] = mapped_column('page_number')  # PDF page
    sectionTitle: Mapped[Optional[str]] = mapped_column('section_title')  # heading, or sheet of a workbook
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column('metadata_json', Json)
    # Vectors of different models cannot be compared: a search only reads the chunks of the model it embedded the query with.
    embeddingModel: Mapped[Optional[str]] = mapped_column('embedding_model', index=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Embedding)

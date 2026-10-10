"""Schema changes for a database made by an earlier version. Additive and safe to run again: it only adds what is missing.

`create_all` makes missing tables, but never touches a table that exists. The columns added since are listed here.
Nothing in this file changes or removes a row: reviewing the stored records is `python -m app.maintenance`.
"""
from sqlalchemy import Engine, inspect, text

# table → (column, SQL type). All nullable: an older row simply has no value.
ADDED = {
    'products': [('yield_gain_unit', 'VARCHAR'), ('baseline_yield', 'FLOAT'), ('status', 'VARCHAR'), ('issues', 'JSON')],
    'uploads': [('size_bytes', 'INTEGER'), ('content_hash', 'VARCHAR'), ('status', 'VARCHAR'), ('issues', 'JSON')],
}


def upgrade(engine: Engine) -> list[str]:
    """Add the missing columns. Returns what it added."""
    done: list[str] = []
    existing = inspect(engine)
    with engine.begin() as conn:
        for table, columns in ADDED.items():
            if not existing.has_table(table):
                continue
            have = {c['name'] for c in existing.get_columns(table)}
            for name, type in columns:
                if name not in have:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {type}'))
                    done.append(f'{table}.{name}')
    return done

"""Review the stored records against the current validation rules, and set aside the ones that fail.

    python -m app.maintenance            # report only: nothing is changed
    python -m app.maintenance --apply    # quarantine what the report lists, and write it to the audit log

Nothing is deleted. A quarantined product stays in the list, marked for review, and cannot be priced until it is
corrected (saving a valid version restores it). A quarantined upload is kept but read by nothing; it is still served by
GET /api/uploads?includeQuarantined=true. Every change is in GET /api/audit.
"""
import argparse
import re

from sqlalchemy import select

from . import db, migrations
from .db import ProductRow, UploadRow
from .limits import product_errors
from .schemas import Product
from .store import Store

FILE_NAME = re.compile(r'.+\.(xlsx|xls|csv)$', re.I)


def review(store: Store) -> list[tuple[str, str, str, list[str]]]:
    """(entity, id, name, issues) of every active record that fails the rules."""
    found: list[tuple[str, str, str, list[str]]] = []
    for row in store.db.scalars(select(ProductRow).order_by(ProductRow.position)):
        if row.status == 'quarantined':
            continue
        issues = [f'{f}: {m}' for f, m in product_errors(Product.model_validate(row).model_dump())]
        if issues:
            found.append(('product', row.id, row.name, issues))
    seen: dict[tuple, str] = {}
    for row in store.db.scalars(select(UploadRow).order_by(UploadRow.createdAt)):  # oldest first: the first copy is the one kept
        if row.status == 'quarantined':
            continue
        issues = []
        if not FILE_NAME.fullmatch((row.name or '').strip()):
            issues.append(f'name: {row.name!r} is not a file name')
        key = (row.contentHash,) if row.contentHash else (row.name, row.type, row.fileDate, row.dataThrough)
        if key in seen:
            issues.append(f'duplicate of {seen[key]}')
        else:
            seen[key] = row.id
        if issues:
            found.append(('upload', row.id, row.name, issues))
    return found


def quarantine(store: Store, found: list[tuple[str, str, str, list[str]]], actor: str = 'maintenance') -> None:
    for entity, id, name, issues in found:
        row = store.db.get(ProductRow if entity == 'product' else UploadRow, id)
        row.status, row.issues = 'quarantined', issues
        store.audit('quarantine', entity, id, {'name': name, 'issues': issues}, actor=actor)
    store.db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='quarantine the records listed (default: report only)')
    args = parser.parse_args()
    migrations.upgrade(db.engine)
    with db.SessionLocal() as session:
        store = Store(session)
        found = review(store)
        for entity, id, name, issues in found:
            print(f'{entity:8} {id:24} {name!r}')
            for issue in issues:
                print(f'           - {issue}')
        if not found:
            print('Every active record passes the validation rules.')
        elif args.apply:
            quarantine(store, found)
            print(f'\nQuarantined {len(found)} record(s). See GET /api/audit.')
        else:
            print(f'\n{len(found)} record(s) would be quarantined. Run again with --apply to do it.')


if __name__ == '__main__':
    main()

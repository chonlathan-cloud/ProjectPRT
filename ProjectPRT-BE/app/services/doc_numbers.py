from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import DocCounter, DocumentType

def generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    current_ym = datetime.now(timezone.utc).strftime("%y%m")
    doc_counter = db.execute(
        select(DocCounter)
        .filter_by(doc_prefix=doc_prefix_enum, year_month=current_ym)
        .with_for_update()
    ).scalar_one_or_none()

    if not doc_counter:
        doc_counter = DocCounter(doc_prefix=doc_prefix_enum, year_month=current_ym, last_number=0)
        db.add(doc_counter)
        db.flush()

    doc_counter.last_number += 1
    new_number = int(doc_counter.last_number)
    return f"{doc_prefix_enum.value}-{current_ym}-{new_number:04d}"

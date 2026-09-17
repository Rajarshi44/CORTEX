from typing import Annotated, Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import String, or_

from ..db import Entity, Alert, Document, get_session
from ..auth import current_user, User

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("")
def global_search(q: str, db: Annotated[Session, Depends(get_session)], _: Annotated[User, Depends(current_user)]) -> Dict[str, List[Any]]:
    """Global search across entities, alerts, and documents."""
    if not q or len(q) < 2:
        return {"entities": [], "alerts": [], "documents": []}
        
    query_term = f"%{q}%"
    
    # 1. Search Entities
    # We search the JSON properties as text, and also the label/canonical key
    entities = db.query(Entity).filter(
        or_(
            Entity.label.ilike(query_term),
            Entity.canonical_key.ilike(query_term),
            # Simple cast to string for JSON search (works in SQLite & Postgres)
            Entity.attributes.cast(String).ilike(query_term) 
        )
    ).limit(10).all()
    
    entity_results = [{
        "id": e.id,
        "type": e.type,
        "label": e.label,
        "risk_score": e.risk_score
    } for e in entities]
    
    # 2. Search Alerts
    alerts = db.query(Alert).filter(
        or_(
            Alert.title.ilike(query_term),
            Alert.description.ilike(query_term)
        )
    ).limit(10).all()
    
    alert_results = [{
        "id": a.id,
        "kind": a.kind,
        "title": a.title,
        "severity": a.severity,
        "review_status": a.review_status
    } for a in alerts]
    
    # 3. Search Documents
    docs = db.query(Document).filter(
        or_(
            Document.title.ilike(query_term),
            Document.content.ilike(query_term)
        )
    ).limit(10).all()
    
    doc_results = [{
        "id": d.id,
        "source_type": d.source_type,
        "title": d.title,
        "occurred_at": d.occurred_at.isoformat() if d.occurred_at else None
    } for d in docs]
    
    return {
        "entities": entity_results,
        "alerts": alert_results,
        "documents": doc_results
    }

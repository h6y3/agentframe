from datetime import datetime
from typing import Optional
from sqlmodel import Session
from agentframe.graph.models import GraphEvent


def append_event(
    session: Session,
    event_type: str,
    node_id: str,
    node_type: str,
    payload: dict,
    proposal_id: Optional[str] = None,
) -> GraphEvent:
    event = GraphEvent(
        event_type=event_type,
        node_id=node_id,
        node_type=node_type,
        payload=payload,
        timestamp=datetime.utcnow(),
        proposal_id=proposal_id,
    )
    session.add(event)
    session.flush()
    return event

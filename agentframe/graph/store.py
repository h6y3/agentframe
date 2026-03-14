from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Session, select
from agentframe.graph.models import Node, GraphEvent
from agentframe.graph.events import append_event
from agentframe.database.connection import get_engine


class Graph:
    def __init__(self, db_url: str | None = None):
        self.engine = get_engine(db_url)
        SQLModel.metadata.create_all(self.engine)

    def add_node(
        self,
        node_type: str,
        id: str,
        label: str,
        attrs: dict,
        proposal_id: Optional[str] = None,
    ) -> Node:
        with Session(self.engine) as session:
            node = Node(
                id=id,
                node_type=node_type,
                label=label,
                attrs=attrs,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(node)
            append_event(
                session,
                "ADD_NODE",
                id,
                node_type,
                {"id": id, "node_type": node_type, "label": label, "attrs": attrs},
                proposal_id=proposal_id,
            )
            session.commit()
            session.refresh(node)
            return node

    def update_node(
        self,
        id: str,
        attrs: dict,
        label: Optional[str] = None,
        proposal_id: Optional[str] = None,
    ) -> Optional[Node]:
        with Session(self.engine) as session:
            node = session.get(Node, id)
            if node is None or node.deleted:
                return None
            merged = {**node.attrs, **attrs}
            node.attrs = merged
            node.updated_at = datetime.utcnow()
            if label is not None:
                node.label = label
            session.add(node)
            append_event(
                session,
                "UPDATE_NODE",
                id,
                node.node_type,
                {
                    "id": id,
                    "node_type": node.node_type,
                    "label": node.label,
                    "attrs": node.attrs,
                },
                proposal_id=proposal_id,
            )
            session.commit()
            session.refresh(node)
            return node

    def remove_node(self, id: str, proposal_id: Optional[str] = None) -> None:
        with Session(self.engine) as session:
            node = session.get(Node, id)
            if node is None:
                return
            node.deleted = True
            node.updated_at = datetime.utcnow()
            session.add(node)
            append_event(
                session,
                "REMOVE_NODE",
                id,
                node.node_type,
                {"id": id, "node_type": node.node_type, "label": node.label},
                proposal_id=proposal_id,
            )
            session.commit()

    def get_node(self, id: str) -> Optional[Node]:
        with Session(self.engine) as session:
            node = session.get(Node, id)
            if node is None or node.deleted:
                return None
            return node

    def list_nodes(self, node_type: Optional[str] = None) -> list[Node]:
        with Session(self.engine) as session:
            stmt = select(Node).where(Node.deleted == False)
            if node_type:
                stmt = stmt.where(Node.node_type == node_type)
            return list(session.exec(stmt).all())

    def query(self, q: str) -> list[Node]:
        """
        Simple keyword search over node labels and attrs.
        Splits on whitespace and matches nodes containing ANY keyword.
        Also matches node_type as a keyword.
        """
        keywords = [k.lower() for k in q.split() if k]
        if not keywords:
            return self.list_nodes()

        all_nodes = self.list_nodes()
        results = []
        for node in all_nodes:
            searchable = " ".join([
                node.id,
                node.label,
                node.node_type,
                " ".join(node.attrs.get("entity_refs", [])),
                " ".join(
                    v for v in node.attrs.values() if isinstance(v, str)
                ),
            ]).lower()

            if any(kw in searchable for kw in keywords):
                results.append(node)
        return results

    def get_event_log(self) -> list[GraphEvent]:
        with Session(self.engine) as session:
            stmt = select(GraphEvent).order_by(GraphEvent.id)
            return list(session.exec(stmt).all())

    def replay_to(self, event_id: int) -> "Graph":
        """
        Reconstruct graph state up to (and including) the given event id.
        Returns a new in-memory Graph built from replaying those events.
        """
        replay_graph = Graph(db_url="sqlite:///:memory:")
        with Session(self.engine) as session:
            stmt = (
                select(GraphEvent)
                .where(GraphEvent.id <= event_id)
                .order_by(GraphEvent.id)
            )
            events = list(session.exec(stmt).all())

        for event in events:
            p = event.payload
            if event.event_type == "ADD_NODE":
                with Session(replay_graph.engine) as rs:
                    existing = rs.get(Node, event.node_id)
                    if existing is None:
                        node = Node(
                            id=p.get("id", event.node_id),
                            node_type=p.get("node_type", event.node_type),
                            label=p.get("label", ""),
                            attrs=p.get("attrs", {}),
                            created_at=event.timestamp,
                            updated_at=event.timestamp,
                        )
                        rs.add(node)
                        rs.commit()
            elif event.event_type == "UPDATE_NODE":
                with Session(replay_graph.engine) as rs:
                    node = rs.get(Node, event.node_id)
                    if node:
                        node.attrs = p.get("attrs", node.attrs)
                        node.label = p.get("label", node.label)
                        node.updated_at = event.timestamp
                        rs.add(node)
                        rs.commit()
            elif event.event_type == "REMOVE_NODE":
                with Session(replay_graph.engine) as rs:
                    node = rs.get(Node, event.node_id)
                    if node:
                        node.deleted = True
                        rs.add(node)
                        rs.commit()

        return replay_graph

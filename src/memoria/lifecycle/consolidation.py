import logging
from dataclasses import dataclass, field

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, aliased

from memoria.database.models import Memory, MemoryEmbedding, MemoryStatus, MemoryType
from memoria.lifecycle.analysis import Relation, classify
from memoria.lifecycle.contradictions import ContradictionDetector
from memoria.lifecycle.policy import LifecyclePolicy
from memoria.lifecycle.scoring import effective_importance

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    canonical: Memory
    merged: list[Memory] = field(default_factory=list)


def plan_clusters(
    pairs: list[tuple[Memory, Memory]], policy: LifecyclePolicy
) -> list[Cluster]:
    """Group duplicate pairs around canonical memories.

    The highest-priority memory (importance, then reinforcement, then most recent) absorbs
    its direct duplicates. Members are never chained through each other, so A~B and B~C
    does not merge A with C unless A~C.
    """
    neighbours: dict[str, set[str]] = {}
    memories: dict[str, Memory] = {}
    for a, b in pairs:
        memories[a.id], memories[b.id] = a, b
        neighbours.setdefault(a.id, set()).add(b.id)
        neighbours.setdefault(b.id, set()).add(a.id)

    def priority(memory: Memory) -> tuple[float, int, object, str]:
        return (
            effective_importance(memory, policy),
            memory.reinforcement_count or 0,
            memory.updated_at,
            memory.id,
        )

    assigned: set[str] = set()
    clusters: list[Cluster] = []
    for memory in sorted(memories.values(), key=priority, reverse=True):
        if memory.id in assigned:
            continue
        members = sorted(
            (memories[i] for i in neighbours[memory.id] if i not in assigned),
            key=lambda m: m.id,
        )
        if members:
            clusters.append(Cluster(memory, members))
            assigned.update([memory.id, *(m.id for m in members)])
    return clusters


class Consolidator:
    """Merges near-duplicate active memories: duplicates become `superseded` by a canonical
    memory, which takes over their reinforcement and the highest explicit importance.

    Compares every pair in scope (O(n^2) in SQL), so scope large namespaces by repository.
    """

    def __init__(
        self,
        db: Session,
        model_name: str,
        policy: LifecyclePolicy,
        detector: ContradictionDetector,
    ):
        self.db = db
        self.model_name = model_name
        self.policy = policy
        self.detector = detector

    def consolidate(
        self,
        namespace: str,
        repository_id: str | None = None,
        session_id: str | None = None,
        memory_type: MemoryType | None = None,
        threshold: float | None = None,
        dry_run: bool = True,
    ) -> list[Cluster]:
        threshold = self.policy.dedup_threshold if threshold is None else threshold
        clusters = plan_clusters(
            self._duplicate_pairs(namespace, repository_id, session_id, memory_type, threshold),
            self.policy,
        )
        if not dry_run:
            for cluster in clusters:
                self._apply(cluster)
            self.db.commit()
            for cluster in clusters:
                for memory in [cluster.canonical, *cluster.merged]:
                    self.db.refresh(memory)
        logger.info(
            "memories consolidated",
            extra={
                "namespace": namespace,
                "dry_run": dry_run,
                "clusters": len(clusters),
                "merged": sum(len(c.merged) for c in clusters),
            },
        )
        return clusters

    def _duplicate_pairs(
        self,
        namespace: str,
        repository_id: str | None,
        session_id: str | None,
        memory_type: MemoryType | None,
        threshold: float,
    ) -> list[tuple[Memory, Memory]]:
        ma, mb = aliased(Memory), aliased(Memory)
        ea, eb = aliased(MemoryEmbedding), aliased(MemoryEmbedding)
        distance = ea.embedding.cosine_distance(eb.embedding)
        stmt = (
            select(ma, mb, (1 - distance).label("similarity"))
            .join(ea, ea.memory_id == ma.id)
            .join(
                mb,
                and_(
                    mb.namespace == ma.namespace,
                    mb.memory_type == ma.memory_type,
                    mb.repository_id.is_not_distinct_from(ma.repository_id),
                    ma.id < mb.id,
                ),
            )
            .join(eb, eb.memory_id == mb.id)
            .where(
                ma.namespace == namespace,
                ma.status == MemoryStatus.ACTIVE,
                mb.status == MemoryStatus.ACTIVE,
                ea.model == self.model_name,
                eb.model == self.model_name,
                distance <= 1 - threshold,
            )
        )
        for alias in (ma, mb):
            if repository_id is not None:
                stmt = stmt.where(alias.repository_id == repository_id)
            if session_id is not None:
                stmt = stmt.where(alias.session_id == session_id)
            if memory_type is not None:
                stmt = stmt.where(alias.memory_type == memory_type)

        pairs = []
        for a, b, similarity in self.db.execute(stmt).all():
            result = classify(a.content, a.memory_type, b, float(similarity), threshold, self.detector)
            if result.relation is Relation.DUPLICATE:
                pairs.append((a, b))
        return pairs

    def _apply(self, cluster: Cluster) -> None:
        canonical = cluster.canonical
        explicit = [
            m.importance_score
            for m in [canonical, *cluster.merged]
            if m.importance_score is not None
        ]
        if explicit:
            canonical.importance_score = max(explicit)
        canonical.reinforcement_count += sum(m.reinforcement_count + 1 for m in cluster.merged)
        for memory in cluster.merged:
            memory.status = MemoryStatus.SUPERSEDED
            memory.superseded_by_id = canonical.id

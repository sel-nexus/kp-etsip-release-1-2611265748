"""Enforce fixed-role administration and atomic audit writes."""
from datetime import UTC, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.core.errors import DomainError
from app.core.pagination import Page
from app.core.transactions import transaction
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.features.auth.schemas import Session
from app.features.roles.repository import RoleRepository
from app.features.roles.schemas import Role, RoleCreate, RoleWrite
from app.features.users.service import UserService


class RoleService:
    """Coordinate role changes with the common administrator guard."""
    def __init__(self, repository: RoleRepository, audit: AuditRepository, users: UserService) -> None:
        """Bind role persistence, audit and the shared authorization guard."""
        self.repository, self.audit, self.users = repository, audit, users

    def project(self, row: dict) -> Role:
        """Convert a persisted document to its public representation."""
        return Role.model_validate({key: value for key, value in row.items() if key != "_id"} | {"id": str(row["_id"])})

    async def listing(self, actor: Session, page: int, size: int) -> Page[Role]:
        """List roles only for authorized administrators."""
        self.users.guard(actor)
        if not 1 <= page <= 21474836 or not 1 <= size <= 100:
            raise DomainError(422, "Invalid pagination")
        rows, total = await self.repository.listing(page, size)
        return Page(items=[self.project(row) for row in rows], total=total, page=page, pageSize=size)

    async def event(self, actor: Session, identifier: ObjectId, action: str, tx) -> None:
        """Append an audit event in the same transaction as the role change."""
        now = datetime.now(UTC)
        await self.audit.append(AuditEvent(timestamp=now, userId=actor.user.id, userName=actor.user.name,
            action=action, entityType="role", entityId=str(identifier), details="Role permissions updated" if action == "permissionChange" else "Role created",
            createdAt=now, updatedAt=now), session=tx)

    async def create(self, actor: Session, payload: RoleCreate) -> Role:
        """Create only a missing fixed role and audit the write atomically."""
        self.users.guard(actor)
        async def work(tx):
            """Recheck authority and insert the role under the common guard."""
            await self.users.lock_actor(actor, tx)
            if payload.name == "Administrator" and "administer" not in payload.permissions:
                raise DomainError(409, "Administrator must retain administer permission")
            now = datetime.now(UTC)
            row = await self.repository.insert({**payload.model_dump(), "createdAt": now, "updatedAt": now}, tx)
            await self.event(actor, row["_id"], "create", tx)
            return row
        try:
            return self.project(await transaction(self.repository.db, work))
        except DuplicateKeyError as exc:
            raise DomainError(409, "Role already exists") from exc

    async def update(self, actor: Session, identifier: str, payload: RoleWrite) -> Role:
        """Replace editable fields without making administration unmanageable."""
        self.users.guard(actor)
        if not ObjectId.is_valid(identifier):
            raise DomainError(422, "Invalid role identifier")
        async def work(tx):
            """Serialize with user administration and recheck actor authority."""
            await self.users.lock_actor(actor, tx)
            row = await self.repository.get(ObjectId(identifier), tx)
            if row is None:
                raise DomainError(404, "Role not found")
            if row["name"] == "Administrator" and "administer" not in payload.permissions:
                raise DomainError(409, "Administrator must retain administer permission")
            updated = await self.repository.update(row["_id"], {**payload.model_dump(), "updatedAt": datetime.now(UTC)}, tx)
            await self.event(actor, row["_id"], "permissionChange", tx)
            return updated
        return self.project(await transaction(self.repository.db, work))

"""Enforce user administration, scoped assignments and transactional invariants."""
from datetime import UTC, datetime
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.core.access import portfolio_scope, require_permission
from app.core.errors import DomainError
from app.core.pagination import Page
from app.core.security import hash_password
from app.core.transactions import transaction, touch_portfolio
from app.features.audit.repository import AuditRepository
from app.features.audit.schemas import AuditEvent
from app.features.auth.schemas import Session
from app.features.auth.service import AuthService
from app.features.users.repository import UserRepository
from app.features.users.schemas import ManagedUser, UserCreate, UserWrite


class UserService:
    """Coordinate live account changes and audit entries in Mongo transactions."""
    def __init__(self, repository: UserRepository, audit: AuditRepository, auth: AuthService) -> None:
        """Bind the shared persistence and identity services."""
        self.repository, self.audit, self.auth = repository, audit, auth

    def guard(self, actor: Session) -> None:
        """Require an Administrator with the current administer permission."""
        require_permission(actor, "administer", "administration")

    def identifier(self, value: str) -> ObjectId:
        """Reject malformed IDs for direct service callers."""
        if not ObjectId.is_valid(value):
            raise DomainError(422, "Invalid user identifier")
        return ObjectId(value)

    async def project(self, row: dict) -> ManagedUser:
        """Project only explicitly safe user fields and current role permissions."""
        return ManagedUser.model_validate((await self.auth.public_user(row)).model_dump())

    async def listing(self, actor: Session, search: str, page: int, size: int) -> Page[ManagedUser]:
        """Read a bounded page of visible accounts."""
        self.guard(actor)
        if not 1 <= page <= 21474836 or not 1 <= size <= 100 or len(search) > 200:
            raise DomainError(422, "Invalid pagination or search")
        rows, total = await self.repository.listing(portfolio_scope(actor), search.strip(), page, size)
        return Page(items=[await self.project(row) for row in rows], total=total, page=page, pageSize=size)

    async def get(self, actor: Session, identifier: str) -> ManagedUser:
        """Hide absent and out-of-scope accounts alike."""
        self.guard(actor)
        row = await self.repository.get(self.identifier(identifier), portfolio_scope(actor))
        if row is None:
            raise DomainError(404, "User not found")
        return await self.project(row)

    async def event(self, actor: Session, identifier: ObjectId, action: str, tx) -> None:
        """Append a fixed summary without recording sensitive values."""
        now = datetime.now(UTC)
        await self.audit.append(AuditEvent(timestamp=now, userId=actor.user.id, userName=actor.user.name,
            action=action, entityType="user", entityId=str(identifier), details=f"User {action} succeeded",
            createdAt=now, updatedAt=now), session=tx)

    async def assign(self, actor: Session, payload: UserWrite, tx) -> list[ObjectId]:
        """Validate and lock assigned portfolios against concurrent deletion."""
        scope = portfolio_scope(actor)
        ids = [ObjectId(value) for value in payload.portfolioAccess]
        if scope is not None and ((not ids and payload.role in ("Administrator", "Executive", "Auditor")) or any(x not in scope for x in ids)):
            raise DomainError(403, "Cannot assign access outside your portfolio scope")
        for identifier in sorted(ids):
            try:
                await touch_portfolio(self.repository.db, identifier, scope, tx)
            except DomainError as exc:
                if exc.status == 404:
                    raise DomainError(409, "Portfolio assignment does not exist") from exc
                raise
        if not await self.repository.db.roles.find_one({"name": payload.role}, session=tx):
            raise DomainError(409, "Role does not exist")
        return ids

    async def lock_actor(self, actor: Session, tx) -> None:
        """Serialize account mutations and recheck the actor's live authority."""
        db = self.repository.db
        await db.guards.update_one({"_id": "active-administrators"}, {"$inc": {"version": 1}}, session=tx)
        live = await db.users.find_one({"_id": ObjectId(actor.user.id)}, session=tx)
        role = await db.roles.find_one({"name": "Administrator"}, session=tx)
        if (not live or live["status"] != "Active" or live["role"] != "Administrator"
                or live["tokenVersion"] != actor.token_version or live["mustChangePassword"]
                or [str(x) for x in live["portfolioAccess"]] != actor.user.portfolioAccess
                or not role or "administer" not in role["permissions"]):
            raise DomainError(403, "Access denied")

    async def create(self, actor: Session, payload: UserCreate) -> ManagedUser:
        """Create a local identity and audit it atomically."""
        self.guard(actor)
        hashed = await hash_password(payload.password.get_secret_value())
        db = self.repository.db
        async def work(tx):
            """Insert the account and its audit entry together."""
            await self.lock_actor(actor, tx)
            ids = await self.assign(actor, payload, tx)
            now = datetime.now(UTC)
            document = payload.model_dump(exclude={"password", "portfolioAccess"})
            document.update(portfolioAccess=ids, passwordHash=hashed, tokenVersion=0, lastLogin=None,
                authSource="local", defaultLandingPage=None, mustChangePassword=False, createdAt=now, updatedAt=now)
            inserted = await db.users.insert_one(document, session=tx)
            document["_id"] = inserted.inserted_id
            await self.event(actor, inserted.inserted_id, "create", tx)
            return document
        try:
            row = await transaction(db, work)
        except DuplicateKeyError as exc:
            raise DomainError(409, "Email already exists") from exc
        return await self.project(row)

    async def mutate(self, actor: Session, identifier: str, payload: UserWrite | None) -> ManagedUser:
        """Update or deactivate an account, serializing changes to active administrators."""
        self.guard(actor)
        user_id = self.identifier(identifier)
        db = self.repository.db
        hashed = await hash_password(payload.password.get_secret_value()) if payload and payload.password else None
        async def work(tx):
            """Touch the common guard before reading the administrator population."""
            await self.lock_actor(actor, tx)
            row = await self.repository.get(user_id, portfolio_scope(actor), session=tx)
            if row is None:
                raise DomainError(404, "User not found")
            status = payload.status if payload else "Inactive"
            role = payload.role if payload else row["role"]
            if str(user_id) == actor.user.id and status != "Active":
                raise DomainError(409, "You cannot deactivate your own account")
            removing_admin = row["status"] == "Active" and row["role"] == "Administrator" and (status != "Active" or role != "Administrator")
            if removing_admin and await db.users.count_documents({"status": "Active", "role": "Administrator"}, session=tx) <= 1:
                raise DomainError(409, "At least one active Administrator is required")
            fields = {"status": status, "updatedAt": datetime.now(UTC)}
            if payload:
                fields.update(payload.model_dump(exclude={"password", "portfolioAccess"}))
                fields["portfolioAccess"] = await self.assign(actor, payload, tx)
                if hashed:
                    fields["passwordHash"] = hashed
                    fields["mustChangePassword"] = False
            changes_auth = status != row["status"] or role != row["role"] or hashed is not None
            update = {"$set": fields}
            if changes_auth:
                update["$inc"] = {"tokenVersion": 1}
            await db.users.update_one({"_id": user_id}, update, session=tx)
            await self.event(actor, user_id, "delete" if payload is None else "edit", tx)
            if role != row["role"]:
                await self.event(actor, user_id, "roleChange", tx)
            return await db.users.find_one({"_id": user_id}, session=tx)
        try:
            row = await transaction(db, work)
        except DuplicateKeyError as exc:
            raise DomainError(409, "Email already exists") from exc
        return await self.project(row)

"""Bootstrap a platform admin user from environment variables.

Called once in the FastAPI lifespan. Idempotent:
- If PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD are not set → no-op.
- If the email already belongs to a platform admin → no-op (silent).
- If the email belongs to a normal user → promote them (set is_platform_admin=True).
- If the email doesn't exist → create a dedicated "FlexCRM Platform" org + owner user.
"""
import logging

from app.core.config import get_settings
from app.core.schema_naming import make_schema_name
from app.core.security import hash_password, verify_password
from app.core.tenancy import bypass
from app.database.enums import LeadIndustry, UserRole, UserStatus
from app.database.session import db_manager
from app.models.organization import Organization
from app.models.user import User
from app.repositories.users import UserRepository


logger = logging.getLogger(__name__)


async def ensure_platform_admin() -> None:
    settings = get_settings()
    email = settings.platform_admin_email
    password = settings.platform_admin_password

    if not email or not password:
        return

    async with db_manager.session_factory() as session:
        with bypass(session):
            user = await UserRepository(session).get_by_email(email)

            if user is not None:
                needs_commit = False
                if not user.is_platform_admin:
                    user.is_platform_admin = True
                    needs_commit = True
                    logger.info("platform_admin: promoted existing user <%s>", email)
                if not verify_password(password, user.password_hash):
                    user.password_hash = hash_password(password)
                    needs_commit = True
                    logger.info("platform_admin: updated password for platform admin <%s>", email)
                if needs_commit:
                    await session.commit()
                return

            # No user found — create a dedicated org + admin user.
            org = Organization(
                name="FlexCRM Platform",
                business_type=LeadIndustry.education,
                plan="platform",
                schema_name=make_schema_name(LeadIndustry.education.value, "FlexCRM Platform"),
            )
            session.add(org)
            await session.flush()   # populate org.id

            admin = User(
                first_name="Platform",
                last_name="Admin",
                email=email,
                password_hash=hash_password(password),
                role=UserRole.owner,
                status=UserStatus.active,
                organization_id=org.id,
                is_platform_admin=True,
            )
            session.add(admin)
            await session.flush()   # populate admin.id

            # Mirror audit FK now that we have both IDs.
            org.created_by_id = admin.id
            org.updated_by_id = admin.id

            await session.commit()
            logger.info("platform_admin: created new platform admin user <%s>", email)

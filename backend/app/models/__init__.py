from app.models.activity import Activity
from app.models.channel_partner import BrokeragePayout, ChannelPartner
from app.models.customer import Customer
from app.models.deal import Deal
from app.models.delivery_log import DeliveryLog
from app.models.lead import Lead
from app.models.lead_document import LeadDocument
from app.models.meta_connection import MetaConnection
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.pipeline_stage import PipelineStage
from app.models.referral import Referral
from app.models.refresh_token import RefreshToken
from app.models.renewal import Renewal
from app.models.stage_transition import StageTransition
from app.models.task import Task
from app.models.user import User
from app.models.user_permission_grant import UserPermissionGrant


__all__ = [
    "Activity",
    "BrokeragePayout",
    "ChannelPartner",
    "Customer",
    "Deal",
    "DeliveryLog",
    "Lead",
    "LeadDocument",
    "MetaConnection",
    "Notification",
    "Organization",
    "PipelineStage",
    "Referral",
    "RefreshToken",
    "Renewal",
    "StageTransition",
    "Task",
    "User",
    "UserPermissionGrant",
]


# NOTE: Finance + HR domain models live in their own packages
# (`app.finance.models`, `app.hr.models`) and register themselves with
# `Base.metadata` when those modules are imported. We deliberately do NOT
# re-import them here — doing so creates a circular import via
# `app.models.base`. Tests that need full metadata (`Base.metadata.create_all`)
# import the finance/hr modules in `conftest.py` instead.

from fastapi import APIRouter

from app.api.v1.endpoints import (
    activities,
    analytics,
    auth,
    customer_lifecycle,
    customers,
    dashboard,
    deals,
    exports,
    leads,
    organizations,
    permissions,
    pipeline_stages,
    tasks,
    users,
    websocket,
)
from app.finance.router import router as finance_router
from app.hr.router import router as hr_router


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
# Customer lifecycle sub-routes (delivery / renewals / referrals) also live
# under /customers/{id}/... — mounted on the same prefix so a single drawer
# can call them.
api_router.include_router(customer_lifecycle.router, prefix="/customers", tags=["Customers"])
api_router.include_router(leads.router, prefix="/leads", tags=["Leads"])
api_router.include_router(pipeline_stages.router, prefix="/pipeline-stages", tags=["Pipeline Stages"])
api_router.include_router(deals.router, prefix="/deals", tags=["Deals"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(activities.router, prefix="/activities", tags=["Activities"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(finance_router, prefix="/finance", tags=["Finance"])
api_router.include_router(hr_router, prefix="/hr", tags=["HR"])
api_router.include_router(exports.router, prefix="/exports", tags=["Exports"])
# Permissions routes mount at the root so `/me/permissions` and
# `/users/{id}/permissions` live alongside their conceptual siblings without
# duplicating prefixes.
api_router.include_router(permissions.router, tags=["Permissions"])
api_router.include_router(websocket.router, prefix="/ws", tags=["Realtime"])

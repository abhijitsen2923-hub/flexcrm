from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_request_metadata
from app.database.session import get_db_session
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshTokenRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth import AuthService


router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
):
    user_agent, ip_address = get_request_metadata(request)
    service = AuthService(session)
    return await service.register(
        payload,
        background_tasks=background_tasks,
        user_agent=user_agent,
        ip_address=ip_address,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    user_agent, ip_address = get_request_metadata(request)
    return await AuthService(session).login(payload, user_agent=user_agent, ip_address=ip_address)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    user_agent, ip_address = get_request_metadata(request)
    return await AuthService(session).refresh(payload, user_agent=user_agent, ip_address=ip_address)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await AuthService(session).logout(payload.refresh_token)


@router.get("/profile", response_model=UserRead)
async def profile(current_user=Depends(get_current_user)):
    return current_user

"""
FastAPI dependencies for authentication, tenant isolation, and database access.
Supports both Supabase JWT tokens and internal JWT tokens.
"""

import uuid
from typing import Annotated, Optional
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt, jwk
from jose.utils import base64url_decode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant

settings = get_settings()
security = HTTPBearer(auto_error=False)

# Cache for JWKS keys
_jwks_cache: dict = {}


def get_jwks_keys(supabase_url: str) -> dict:
    """
    Fetch JWKS keys from Supabase.
    Keys are cached to avoid repeated HTTP requests.
    """
    global _jwks_cache

    if not _jwks_cache:
        try:
            jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
            response = httpx.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            _jwks_cache = response.json()
        except Exception as e:
            print(f"[JWKS] Error fetching keys: {e}")
            return {}

    return _jwks_cache


def decode_supabase_token(token: str) -> dict:
    """
    Decode a Supabase JWT token.
    Supabase tokens contain: sub (user UUID), email, role, etc.
    Supports both HS256 (legacy) and ES256 (current) algorithms.
    """
    import json
    import base64

    # First, peek at the token header to determine the algorithm
    try:
        header_segment = token.split('.')[0]
        # Add padding if necessary
        padding = 4 - len(header_segment) % 4
        if padding != 4:
            header_segment += '=' * padding
        header_data = base64.urlsafe_b64decode(header_segment)
        header = json.loads(header_data)
        alg = header.get('alg', 'HS256')
        kid = header.get('kid')
    except Exception as e:
        print(f"[JWT] Error parsing header: {e}")
        alg = 'HS256'
        kid = None

    print(f"[JWT] Token algorithm: {alg}, kid: {kid}")

    # Try ES256 with JWKS if that's the algorithm
    if alg == 'ES256':
        try:
            jwks = get_jwks_keys(settings.supabase_url)
            if jwks and 'keys' in jwks:
                # Find the right key by kid, or use the first one
                key_data = None
                for k in jwks['keys']:
                    if kid and k.get('kid') == kid:
                        key_data = k
                        break
                if not key_data and jwks['keys']:
                    key_data = jwks['keys'][0]

                if key_data:
                    # Construct the public key
                    public_key = jwk.construct(key_data)
                    payload = jwt.decode(
                        token,
                        public_key,
                        algorithms=["ES256"],
                        options={"verify_aud": False}
                    )
                    print(f"[JWT] Successfully decoded ES256 token for user: {payload.get('sub')}")
                    return {"type": "supabase", "payload": payload}
        except JWTError as e:
            print(f"[JWT] ES256 decode error: {e}")
        except Exception as e:
            print(f"[JWT] ES256 unexpected error: {e}")

    # Try HS256 with Supabase JWT secret
    try:
        supabase_secret = getattr(settings, 'supabase_jwt_secret', None)
        if supabase_secret and supabase_secret != 'your_supabase_jwt_secret_here':
            payload = jwt.decode(
                token,
                supabase_secret,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            print(f"[JWT] Successfully decoded HS256 token for user: {payload.get('sub')}")
            return {"type": "supabase", "payload": payload}
    except JWTError as e:
        print(f"[JWT] HS256 decode error: {e}")

    # Fallback: try internal JWT
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        print(f"[JWT] Successfully decoded internal token for user: {payload.get('sub')}")
        return {"type": "internal", "payload": payload}
    except JWTError as e:
        print(f"[JWT] Internal decode error: {e}")

    print("[JWT] All decode attempts failed")
    return {"type": None, "payload": None}


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    Supports both Supabase and internal JWT tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exception

    token = credentials.credentials
    decoded = decode_supabase_token(token)

    if decoded["type"] is None:
        raise credentials_exception

    payload = decoded["payload"]

    if decoded["type"] == "supabase":
        # Supabase token: sub is the user UUID
        user_uuid_str = payload.get("sub")
        user_email = payload.get("email")

        if not user_uuid_str:
            raise credentials_exception

        # Find user by Supabase UUID (stored in auth_provider_id) or email
        try:
            user_uuid = uuid.UUID(user_uuid_str)
            result = await db.execute(
                select(User).where(
                    User.id == user_uuid,
                    User.is_active == True
                )
            )
            user = result.scalar_one_or_none()

            # Fallback: find by email if user not found by UUID
            if not user and user_email:
                result = await db.execute(
                    select(User).where(
                        User.email == user_email,
                        User.is_active == True
                    )
                )
                user = result.scalar_one_or_none()
        except (ValueError, TypeError):
            raise credentials_exception

    else:
        # Internal token: sub is the user ID (could be int or UUID string)
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception

        try:
            # Try UUID first
            user_uuid = uuid.UUID(str(user_id))
            result = await db.execute(
                select(User).where(User.id == user_uuid, User.is_active == True)
            )
        except (ValueError, TypeError):
            # Fallback to integer ID (legacy)
            result = await db.execute(
                select(User).where(User.id == int(user_id), User.is_active == True)
            )

        user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """
    Optional authentication - returns None if no valid credentials.
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def get_current_tenant(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    """
    Dependency to get the current tenant from the authenticated user.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant not found or inactive",
        )

    return tenant


def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific user roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_role("admin"))):
            ...
    """
    async def role_checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {', '.join(allowed_roles)}",
            )
        return user

    return role_checker


async def get_tenant_id(
    user: Annotated[User, Depends(get_current_user)],
) -> uuid.UUID:
    """
    Dependency to get the tenant ID from the authenticated user.
    Simpler than get_current_tenant when you only need the ID.
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no associated tenant",
        )
    return user.tenant_id


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserOptional = Annotated[Optional[User], Depends(get_current_user_optional)]
CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]
TenantId = Annotated[uuid.UUID, Depends(get_tenant_id)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

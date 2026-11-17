
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import Client

# Tell FastAPI to expect an Authorization: Bearer <token> header.
# auto_error=False lets us return 401 when the token is missing.
security = HTTPBearer(auto_error=False)


def make_current_user_dependency(supabase: Client):
    def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security)
    ) -> str:
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Missing authentication token"
            )
        try:
            response = supabase.auth.get_user(credentials.credentials)

            if response.user is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid authentication token"
                )

            return response.user.id

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired authentication token"
            ) from e

    return get_current_user

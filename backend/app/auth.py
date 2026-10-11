import httpx
from uuid import UUID
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from .config import settings
from .db import connection,one
bearer=HTTPBearer(auto_error=False)
async def current_user(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
    if not credentials: raise HTTPException(401,'Sign in to continue')
    s=settings()
    if not s.supabase_url or not s.supabase_anon_key: raise HTTPException(503,'Authentication is not configured')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response=await client.get(s.supabase_url.rstrip('/')+'/auth/v1/user',headers={'apikey':s.supabase_anon_key,'Authorization':'Bearer '+credentials.credentials})
        if response.status_code in (401,403): raise HTTPException(401,'Your session expired. Sign in again.')
        response.raise_for_status(); user=response.json(); UUID(user['id'])
    except HTTPException: raise
    except (httpx.HTTPError,ValueError,KeyError): raise HTTPException(503,'Authentication service is temporarily unavailable')
    if not user.get('email_confirmed_at'): raise HTTPException(403,'Verify your email before continuing')
    async with connection() as c:
        await c.execute('INSERT INTO user_profiles(id) VALUES(%s) ON CONFLICT DO NOTHING',(user['id'],))
        await c.execute("INSERT INTO user_roles VALUES(%s,'student') ON CONFLICT DO NOTHING",(user['id'],))
    return user
async def admin_user(user=Depends(current_user)):
    async with connection() as c:
        role=await one(c,"SELECT 1 FROM user_roles WHERE user_id=%s AND role='admin'",(user['id'],))
    if not role: raise HTTPException(403,'Administrator access required')
    return user

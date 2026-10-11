import json,logging,secrets,hashlib
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from uuid import UUID
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Form,Header,Query,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx,psycopg
from psycopg.types.json import Jsonb
from .config import settings
from . import db
from .auth import current_user,admin_user
from .schemas import *
from .matching import normalize_skill,lifecycle,actionable,recommend,rank_candidates,optimize_squad,input_hash
from .importer import inspect_import
from .ai import copilot
from .body_limit import BodyLimitMiddleware
log=logging.getLogger('hackconnect')
@asynccontextmanager
async def lifespan(app):
    settings().validate_production();await db.open_pool()
    yield
    await db.close_pool()
app=FastAPI(title='HackConnect AI',version='1.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings().cors_origins.split(',')],allow_methods=['GET','POST','PUT','PATCH','DELETE'],allow_headers=['Authorization','Content-Type'],allow_credentials=False)
app.add_middleware(BodyLimitMiddleware)
@app.middleware('http')
async def request_guard(request,call_next):
    request_id=secrets.token_hex(8)
    length=request.headers.get('content-length','0')
    if length.isdigit() and int(length)>6*1024*1024:return JSONResponse(status_code=413,content={'detail':'Request too large'})
    response=await call_next(request)
    response.headers['X-Request-ID']=request_id;response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    log.info(json.dumps({'request_id':request_id,'method':request.method,'path':request.url.path,'status':response.status_code}))
    return response
@app.exception_handler(psycopg.errors.UniqueViolation)
async def duplicate_handler(request,exc):return JSONResponse(status_code=409,content={'detail':'This record already exists or conflicts with another membership.'})
@app.exception_handler(psycopg.Error)
async def database_handler(request,exc):
    log.error('database_failure',extra={'sqlstate':exc.sqlstate})
    return JSONResponse(status_code=503,content={'detail':'Database operation failed. Please retry.'})
async def actor(user=Depends(current_user)):
    async with db.connection() as c:
        rate=await db.one(c,"INSERT INTO api_rate_limits(user_id,bucket,count) VALUES(%s,date_trunc('minute',now()),1) ON CONFLICT(user_id) DO UPDATE SET bucket=excluded.bucket,count=CASE WHEN api_rate_limits.bucket=excluded.bucket THEN api_rate_limits.count+1 ELSE 1 END RETURNING count",(user['id'],))
        if rate['count']>120:raise HTTPException(429,'Too many requests. Try again in a minute.')
    return user
async def get_profile(c,user_id):
    p=await db.one(c,'SELECT * FROM user_profiles WHERE id=%s',(user_id,))
    if not p:raise HTTPException(404,'Profile not found')
    p['skills']=await db.all_rows(c,'SELECT s.name,s.category,u.proficiency FROM user_skills u JOIN skills s ON s.id=u.skill_id WHERE user_id=%s',(user_id,))
    p['availability']=await db.all_rows(c,'SELECT starts_at,ends_at FROM user_availability WHERE user_id=%s ORDER BY starts_at',(user_id,))
    return p
async def get_event(c,event_id):
    e=await db.one(c,'SELECT * FROM hackathons WHERE id=%s',(event_id,))
    if not e:raise HTTPException(404,'Hackathon not found')
    e['requirements']=await db.all_rows(c,'SELECT s.name,s.category,r.proficiency FROM hackathon_requirements r JOIN skills s ON s.id=r.skill_id WHERE r.hackathon_id=%s',(event_id,))
    return {**e,**lifecycle(e)}
def public_profile(p):
    keys=['id','display_name','bio','skills','roles','interests','format','experience']
    result={k:p[k] for k in keys}
    if p['visibility'].get('institution'):result['institution']=p['institution']
    if p['visibility'].get('city'):result['city']=p['city']
    if p['visibility'].get('links'):
        for k in ['github_url','linkedin_url','portfolio_url']:result[k]=p[k]
    return result
async def ensure_no_event_conflict(c,user_id,event):
    # Serialize this user's memberships across distinct squads/events.
    await c.execute('SELECT id FROM user_profiles WHERE id=%s FOR UPDATE',(user_id,))
    if await db.one(c,'SELECT 1 FROM team_members WHERE user_id=%s AND hackathon_id=%s',(user_id,event['id'])):raise HTTPException(409,'Already a member of a squad for this hackathon')
    if event.get('starts_at') and event.get('ends_at'):
        conflict=await db.one(c,'SELECT 1 FROM team_members m JOIN hackathons h ON h.id=m.hackathon_id WHERE m.user_id=%s AND NOT h.cancelled AND h.starts_at<%s AND h.ends_at>%s LIMIT 1',(user_id,event['ends_at'],event['starts_at']))
        if conflict:raise HTTPException(409,'Another squad event overlaps this hackathon')
async def require_member(c,team_id,user_id,leader=False,lock=False):
    t=await db.one(c,'SELECT * FROM teams WHERE id=%s'+(' FOR UPDATE' if lock else ''),(team_id,))
    if not t:raise HTTPException(404,'Squad not found')
    m=await db.one(c,'SELECT * FROM team_members WHERE team_id=%s AND user_id=%s',(team_id,user_id))
    if not m:raise HTTPException(403,'Only current squad members can access this workspace')
    if leader and str(t['leader_id'])!=str(user_id):raise HTTPException(403,'Squad leader access required')
    return t
async def audit(c,user_id,action,target=None,details=None):
    await c.execute('INSERT INTO audit_logs(actor_id,action,target,details) VALUES(%s,%s,%s,%s)',(user_id,action,str(target) if target else None,Jsonb(details or {})))
async def activity(c,team_id,user_id,action,details=None):
    await c.execute('INSERT INTO team_activity(team_id,actor_id,action,details) VALUES(%s,%s,%s,%s)',(team_id,user_id,action,Jsonb(details or {})))
async def notify(c,user_id,kind,title,link=None,dedupe=None):
    prefs=await db.one(c,'SELECT notification_preferences FROM profile_preferences WHERE user_id=%s',(user_id,))
    if prefs and prefs['notification_preferences'].get(kind) is False:return
    await c.execute('INSERT INTO notifications(user_id,kind,title,link,dedupe_key) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(user_id,dedupe_key) DO NOTHING',(user_id,kind,title,link,dedupe))
async def save_skills(c,user_id,skills):
    await c.execute('DELETE FROM user_skills WHERE user_id=%s',(user_id,))
    seen={}
    for s in skills:
        s=s.model_dump() if hasattr(s,'model_dump') else s
        key=normalize_skill(s['name'])
        if key in seen:continue
        seen[key]=True
        await c.execute('INSERT INTO skills(id,name,category) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(key,key,s['category']))
        await c.execute('INSERT INTO user_skills VALUES(%s,%s,%s)',(user_id,key,s['proficiency']))
@app.get('/health')
async def health():return {'status':'ok','service':'hackconnect-api','version':'1.0.0'}
@app.get('/ready')
async def ready():
    async with db.connection() as c:await c.execute('SELECT 1 FROM schema_migrations LIMIT 1')
    if not settings().supabase_url or not settings().supabase_anon_key:raise HTTPException(503,'Authentication configuration missing')
    return {'status':'ready','ai_configured':bool(settings().xai_api_key and settings().xai_model)}
@app.get('/api/v1/me')
async def me(user=Depends(actor)):
    async with db.connection() as c:
        p=await get_profile(c,user['id']);p['is_admin']=bool(await db.one(c,"SELECT 1 FROM user_roles WHERE user_id=%s AND role='admin'",(user['id'],)))
        return p
@app.put('/api/v1/me')
async def update_me(body:Profile,user=Depends(actor)):
    values=body.model_dump(exclude={'skills','availability'})
    async with db.connection() as c:
        fields=','.join(f'{k}=%s' for k in values)
        vals=[Jsonb(v) if isinstance(v,dict) else v for v in values.values()]
        await c.execute(f'UPDATE user_profiles SET {fields},updated_at=now() WHERE id=%s',(*vals,user['id']))
        await save_skills(c,user['id'],body.skills)
        await c.execute('DELETE FROM user_availability WHERE user_id=%s',(user['id'],))
        for slot in body.availability:await c.execute('INSERT INTO user_availability(user_id,starts_at,ends_at) VALUES(%s,%s,%s)',(user['id'],slot.starts_at,slot.ends_at))
        await c.execute('DELETE FROM hackathon_recommendations WHERE user_id=%s',(user['id'],))
        await c.execute('DELETE FROM ai_cache WHERE user_id=%s',(user['id'],))
        return await get_profile(c,user['id'])
@app.post('/api/v1/me/claim-import')
async def claim_import(user=Depends(actor)):
    async with db.connection() as c:
        row=await db.one(c,'SELECT * FROM imported_students WHERE email=%s FOR UPDATE',(user.get('email','').casefold(),))
        if not row:raise HTTPException(404,'No imported record matches your verified email')
        if row['claimed_by']:raise HTTPException(409,'Record already claimed. Edit your profile to make corrections.')
        p=await get_profile(c,user['id'])
        if p['onboarding_complete']:raise HTTPException(409,'Your profile is complete. Edit it instead of overwriting it.')
        await c.execute('UPDATE user_profiles SET display_name=%s,institution=%s,updated_at=now() WHERE id=%s',(row['display_name'],row['institution'],user['id']))
        await save_skills(c,user['id'],row['skills'])
        await c.execute('UPDATE imported_students SET claimed_by=%s WHERE id=%s',(user['id'],row['id']))
        return await get_profile(c,user['id'])
@app.delete('/api/v1/me')
async def delete_account(user=Depends(actor)):
    s=settings()
    if not s.supabase_service_role_key:raise HTTPException(503,'Account deletion is not configured')
    async with db.connection() as c:
        leaders=await db.all_rows(c,'SELECT id FROM teams WHERE leader_id=%s ORDER BY id FOR UPDATE',(user['id'],))
        for team in leaders:
            next_member=await db.one(c,'SELECT user_id FROM team_members WHERE team_id=%s AND user_id<>%s ORDER BY joined_at LIMIT 1',(team['id'],user['id']))
            if next_member:await c.execute('UPDATE teams SET leader_id=%s WHERE id=%s',(next_member['user_id'],team['id']))
            else:await c.execute('DELETE FROM teams WHERE id=%s',(team['id'],))
        # Imported personal information must also disappear on deletion.
        await c.execute('DELETE FROM imported_students WHERE claimed_by=%s OR email=%s',(user['id'],user.get('email','').casefold()))
    async with httpx.AsyncClient(timeout=15) as client:
        try:r=await client.delete(s.supabase_url+'/auth/v1/admin/users/'+user['id'],headers={'apikey':s.supabase_service_role_key,'Authorization':'Bearer '+s.supabase_service_role_key})
        except httpx.HTTPError:raise HTTPException(503,'Account deletion service is unavailable. Retry or contact support.')
        if r.status_code not in (200,204):raise HTTPException(503,'Account deletion failed. Retry or contact support.')
    return {'deleted':True}
@app.get('/api/v1/hackathons')
async def events(q:str='',format:str='',saved:bool=False,archive:bool=False,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),user=Depends(actor)):
    async with db.connection() as c:
        ids=await db.all_rows(c,"SELECT h.id FROM hackathons h WHERE verification_status='verified' AND (%s='' OR h.title ILIKE %s) AND (%s='' OR h.format=%s) AND (NOT %s OR EXISTS(SELECT 1 FROM hackathon_bookmarks b WHERE b.hackathon_id=h.id AND b.user_id=%s)) AND NOT EXISTS(SELECT 1 FROM recommendation_feedback f WHERE f.hackathon_id=h.id AND f.user_id=%s AND f.feedback='hide') ORDER BY starts_at NULLS LAST LIMIT 1000",(q,'%'+q+'%',format,format,saved,user['id'],user['id']))
        p=await get_profile(c,user['id']);items=[]
        for row in ids:
            e=await get_event(c,row['id'])
            if archive or saved or actionable(e,max_age_days=settings().verification_max_age_days):
                digest=input_hash(p,e)
                cached=await db.one(c,'SELECT result FROM hackathon_recommendations WHERE user_id=%s AND hackathon_id=%s AND version=%s AND input_hash=%s',(user['id'],e['id'],'v1',digest))
                fit=cached['result'] if cached else recommend(p,e)
                fit['actionable']=fit['actionable'] and actionable(e,max_age_days=settings().verification_max_age_days)
                await c.execute('INSERT INTO hackathon_recommendations(user_id,hackathon_id,version,input_hash,result) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(user['id'],e['id'],'v1',digest,Jsonb(fit)))
                bookmarked=bool(await db.one(c,'SELECT 1 FROM hackathon_bookmarks WHERE user_id=%s AND hackathon_id=%s',(user['id'],e['id'])))
                items.append({**e,'match':fit,'bookmarked':bookmarked})
        items.sort(key=lambda x:-x['match']['score'])
        return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit,'bounded_to':1000}
@app.get('/api/v1/hackathons/{event_id}')
async def event_detail(event_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        e=await get_event(c,event_id)
        if e['verification_status']!='verified':raise HTTPException(404,'Hackathon is not published')
        fit=recommend(await get_profile(c,user['id']),e);fit['actionable']=fit['actionable'] and actionable(e,max_age_days=settings().verification_max_age_days)
        return {**e,'match':fit}
@app.put('/api/v1/hackathons/{event_id}/bookmark')
async def bookmark(event_id:UUID,save:bool=True,user=Depends(actor)):
    async with db.connection() as c:
        e=await get_event(c,event_id)
        if e['verification_status']!='verified':raise HTTPException(404,'Hackathon is not published')
        if save:await c.execute('INSERT INTO hackathon_bookmarks VALUES(%s,%s) ON CONFLICT DO NOTHING',(user['id'],event_id))
        else:await c.execute('DELETE FROM hackathon_bookmarks WHERE user_id=%s AND hackathon_id=%s',(user['id'],event_id))
    return {'saved':save}
@app.post('/api/v1/hackathons/{event_id}/hide')
async def hide(event_id:UUID,user=Depends(actor)):
    async with db.connection() as c:await c.execute("INSERT INTO recommendation_feedback VALUES(%s,%s,'hide') ON CONFLICT(user_id,hackathon_id) DO UPDATE SET feedback='hide'",(user['id'],event_id))
    return {'hidden':True}
@app.delete('/api/v1/me/hidden-events')
async def reset_hidden(user=Depends(actor)):
    async with db.connection() as c:await c.execute("DELETE FROM recommendation_feedback WHERE user_id=%s AND feedback='hide'",(user['id'],))
    return {'reset':True}
@app.get('/api/v1/hackathons/{event_id}/teammates')
async def teammates(event_id:UUID,team_id:UUID|None=None,ideal:bool=False,user=Depends(actor)):
    async with db.connection() as c:
        e=await get_event(c,event_id)
        if not actionable(e,max_age_days=settings().verification_max_age_days):raise HTTPException(409,'This hackathon is not verified and open for team formation')
        p=await get_profile(c,user['id']);members=[]
        if team_id:
            t=await require_member(c,team_id,user['id'])
            if t['hackathon_id']!=event_id:raise HTTPException(422,'Squad belongs to a different hackathon')
            rows=await db.all_rows(c,'SELECT user_id FROM team_members WHERE team_id=%s',(team_id,))
            members=[await get_profile(c,r['user_id']) for r in rows if str(r['user_id'])!=user['id']]
        ids=await db.all_rows(c,"SELECT p.id FROM user_profiles p WHERE p.id<>%s AND p.discoverable AND p.contact_consent AND p.open_to_invitations AND p.onboarding_complete AND NOT EXISTS(SELECT 1 FROM team_members m WHERE m.user_id=p.id AND m.hackathon_id=%s) AND NOT EXISTS(SELECT 1 FROM user_blocks b WHERE (b.blocker_id=%s AND b.blocked_id=p.id) OR (b.blocked_id=%s AND b.blocker_id=p.id)) ORDER BY p.updated_at DESC LIMIT 500",(user['id'],event_id,user['id'],user['id']))
        candidates=[await get_profile(c,r['id']) for r in ids];ranked=rank_candidates(p,e,candidates,members)
        if ideal:
            result=optimize_squad(ranked,min(e['maximum_team_size'],p['preferred_team_size'])-len(members)-1)
            for item in result['members']:
                item['proposed_role']=next(iter(item['profile'].get('roles',[])),'Discuss with the candidate')
                item['profile']=public_profile(item['profile'])
            return result
        for item in ranked:item['profile']=public_profile(item['profile'])
        return {'items':ranked[:50],'bounded_to':500}
@app.post('/api/v1/teams',status_code=201)
async def create_team(body:TeamCreate,user=Depends(actor)):
    async with db.connection() as c:
        e=await get_event(c,body.hackathon_id);p=await get_profile(c,user['id'])
        if not p['onboarding_complete']:raise HTTPException(409,'Complete your profile first')
        if not actionable(e,max_age_days=settings().verification_max_age_days) or not recommend(p,e)['actionable']:raise HTTPException(409,'Review eligibility and event availability before forming a squad')
        await ensure_no_event_conflict(c,user['id'],e)
        t=await db.one(c,'INSERT INTO teams(hackathon_id,name,leader_id) VALUES(%s,%s,%s) RETURNING *',(body.hackathon_id,body.name,user['id']))
        await c.execute("INSERT INTO team_members(team_id,user_id,hackathon_id,role) VALUES(%s,%s,%s,'leader')",(t['id'],user['id'],body.hackathon_id))
        await activity(c,t['id'],user['id'],'squad_created');return t
@app.get('/api/v1/teams')
async def teams(user=Depends(actor)):
    async with db.connection() as c:return await db.all_rows(c,'SELECT t.*,h.title AS hackathon_title,(SELECT count(*) FROM team_members m WHERE m.team_id=t.id) AS member_count,(SELECT count(*) FROM team_messages msg WHERE msg.team_id=t.id AND msg.sender_id<>%s AND msg.created_at>COALESCE((SELECT read_at FROM message_read_cursors r WHERE r.team_id=t.id AND r.user_id=%s),t.created_at)) AS unread FROM teams t JOIN team_members m ON m.team_id=t.id JOIN hackathons h ON h.id=t.hackathon_id WHERE m.user_id=%s ORDER BY t.created_at DESC',(user['id'],user['id'],user['id']))
@app.post('/api/v1/teams/{team_id}/invitations',status_code=201)
async def invite(team_id:UUID,body:InvitationCreate,user=Depends(actor)):
    async with db.connection() as c:
        t=await require_member(c,team_id,user['id'],leader=True,lock=True);e=await get_event(c,t['hackathon_id'])
        if not actionable(e,max_age_days=settings().verification_max_age_days):raise HTTPException(409,'Event registration is no longer open')
        p=await get_profile(c,body.recipient_id)
        blocked=await db.one(c,'SELECT 1 FROM user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocked_id=%s AND blocker_id=%s)',(user['id'],body.recipient_id,user['id'],body.recipient_id))
        if blocked or not all(p[k] for k in ('discoverable','contact_consent','open_to_invitations','onboarding_complete')):raise HTTPException(403,'This student is not accepting invitations')
        if not recommend(p,e)['actionable']:raise HTTPException(409,'Candidate eligibility or schedule is incompatible')
        count=await db.one(c,'SELECT count(*) AS n FROM team_members WHERE team_id=%s',(team_id,))
        if count['n']>=e['maximum_team_size']:raise HTTPException(409,'Squad is full')
        if await db.one(c,'SELECT 1 FROM team_members WHERE user_id=%s AND hackathon_id=%s',(body.recipient_id,t['hackathon_id'])):raise HTTPException(409,'Student already belongs to a squad for this hackathon')
        item=await db.one(c,'INSERT INTO team_invitations(team_id,sender_id,recipient_id) VALUES(%s,%s,%s) RETURNING *',(team_id,user['id'],body.recipient_id))
        await notify(c,body.recipient_id,'invitation','You have a squad invitation','/dashboard?tab=invitations',str(item['id']));return item
@app.get('/api/v1/invitations')
async def invitations(user=Depends(actor)):
    async with db.connection() as c:return await db.all_rows(c,'SELECT i.*,t.name AS team_name,h.title AS hackathon_title FROM team_invitations i JOIN teams t ON t.id=i.team_id JOIN hackathons h ON h.id=t.hackathon_id WHERE i.recipient_id=%s OR i.sender_id=%s ORDER BY i.created_at DESC LIMIT 100',(user['id'],user['id']))
@app.patch('/api/v1/invitations/{invitation_id}')
async def respond(invitation_id:UUID,body:InvitationResponse,user=Depends(actor)):
    async with db.connection() as c:
        item=await db.one(c,'SELECT * FROM team_invitations WHERE id=%s',(invitation_id,))
        if not item or str(item['recipient_id'])!=user['id']:raise HTTPException(404,'Invitation not found')
        # Lock team first consistently with all other membership mutations.
        t=await db.one(c,'SELECT * FROM teams WHERE id=%s FOR UPDATE',(item['team_id'],))
        item=await db.one(c,'SELECT * FROM team_invitations WHERE id=%s FOR UPDATE',(invitation_id,))
        if item['status']!='pending':raise HTTPException(409,'Invitation was already answered')
        if body.decision=='accepted':
            e=await get_event(c,t['hackathon_id']);p=await get_profile(c,user['id'])
            if not actionable(e,max_age_days=settings().verification_max_age_days) or not recommend(p,e)['actionable']:raise HTTPException(409,'Hackathon is unavailable or eligibility changed')
            if not p['open_to_invitations']:raise HTTPException(409,'Enable invitations before accepting')
            if await db.one(c,'SELECT 1 FROM user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocked_id=%s AND blocker_id=%s)',(user['id'],t['leader_id'],user['id'],t['leader_id'])):raise HTTPException(403,'Invitation is blocked')
            count=await db.one(c,'SELECT count(*) AS n FROM team_members WHERE team_id=%s',(t['id'],))
            if count['n']>=e['maximum_team_size']:raise HTTPException(409,'Squad is full')
            await ensure_no_event_conflict(c,user['id'],e)
            await c.execute('INSERT INTO team_members(team_id,user_id,hackathon_id) VALUES(%s,%s,%s)',(t['id'],user['id'],t['hackathon_id']))
            await c.execute("UPDATE team_invitations SET status='cancelled',responded_at=now() WHERE recipient_id=%s AND status='pending' AND id<>%s AND team_id IN(SELECT id FROM teams WHERE hackathon_id=%s)",(user['id'],invitation_id,t['hackathon_id']))
            await activity(c,t['id'],user['id'],'member_joined')
            if count['n']+1>=e['minimum_team_size']:
                for m in await db.all_rows(c,'SELECT user_id FROM team_members WHERE team_id=%s',(t['id'],)):await notify(c,m['user_id'],'team','Squad has enough members to participate','/squads/'+str(t['id']),'formed:'+str(t['id']))
        await c.execute('UPDATE team_invitations SET status=%s,responded_at=now() WHERE id=%s',(body.decision,invitation_id))
        await notify(c,item['sender_id'],'invitation','Invitation '+body.decision,'/squads/'+str(t['id']),'response:'+str(invitation_id))
        return {'status':body.decision,'team_id':t['id']}
@app.get('/api/v1/teams/{team_id}')
async def workspace(team_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        t=await require_member(c,team_id,user['id']);members=await db.all_rows(c,'SELECT user_id,role,assigned_role FROM team_members WHERE team_id=%s ORDER BY joined_at',(team_id,))
        t['members']=[{**public_profile(await get_profile(c,m['user_id'])),'team_role':'leader' if str(m['user_id'])==str(t['leader_id']) else 'member','assigned_role':m['assigned_role']} for m in members]
        t['event']=await get_event(c,t['hackathon_id']);t['tasks']=await db.all_rows(c,'SELECT * FROM project_tasks WHERE team_id=%s ORDER BY created_at',(team_id,))
        t['milestones']=await db.all_rows(c,'SELECT * FROM milestones WHERE team_id=%s ORDER BY title',(team_id,))
        t['resources']=await db.all_rows(c,'SELECT * FROM project_resources WHERE team_id=%s ORDER BY created_at DESC',(team_id,))
        t['activity']=await db.all_rows(c,'SELECT * FROM team_activity WHERE team_id=%s ORDER BY created_at DESC LIMIT 50',(team_id,))
        t['pending_invitations']=await db.all_rows(c,'SELECT id,recipient_id,status FROM team_invitations WHERE team_id=%s AND status=\'pending\'',(team_id,))
        t['progress']=round(100*sum(x['status']=='completed' for x in t['tasks'])/len(t['tasks'])) if t['tasks'] else 0
        return t
@app.put('/api/v1/teams/{team_id}')
async def team_settings(team_id:UUID,body:TeamSettings,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'],leader=True,lock=True)
        await c.execute('UPDATE teams SET name=%s,ai_consent=%s WHERE id=%s',(body.name,body.ai_consent,team_id))
        await activity(c,team_id,user['id'],'settings_updated')
    return {'saved':True}
@app.delete('/api/v1/teams/{team_id}/members/{member_id}')
async def leave(team_id:UUID,member_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        t=await require_member(c,team_id,user['id'],lock=True)
        if str(member_id)!=user['id'] and str(t['leader_id'])!=user['id']:raise HTTPException(403,'Only the leader can remove other members')
        if str(member_id)==str(t['leader_id']):
            nxt=await db.one(c,'SELECT user_id FROM team_members WHERE team_id=%s AND user_id<>%s ORDER BY joined_at LIMIT 1',(team_id,member_id))
            if nxt:await c.execute('UPDATE teams SET leader_id=%s,ai_consent=false WHERE id=%s',(nxt['user_id'],team_id))
            else:
                await c.execute('DELETE FROM teams WHERE id=%s',(team_id,));return {'deleted':True}
        await c.execute('DELETE FROM team_members WHERE team_id=%s AND user_id=%s',(team_id,member_id))
        await c.execute('UPDATE project_tasks SET assignee_id=NULL WHERE team_id=%s AND assignee_id=%s',(team_id,member_id))
        await activity(c,team_id,user['id'],'member_left');return {'left':True}
@app.get('/api/v1/teams/{team_id}/messages')
async def messages(team_id:UUID,before:datetime|None=None,limit:int=Query(50,ge=1,le=100),user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        rows=await db.all_rows(c,'SELECT m.*,p.display_name FROM team_messages m LEFT JOIN user_profiles p ON p.id=m.sender_id WHERE m.team_id=%s AND (%s::timestamptz IS NULL OR m.created_at<%s) ORDER BY m.created_at DESC LIMIT %s',(team_id,before,before,limit))
        return list(reversed(rows))
@app.post('/api/v1/teams/{team_id}/messages',status_code=201)
async def send_message(team_id:UUID,body:Message,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        row=await db.one(c,'INSERT INTO team_messages(team_id,sender_id,body) VALUES(%s,%s,%s) RETURNING *',(team_id,user['id'],body.body))
        for m in await db.all_rows(c,'SELECT user_id FROM team_members WHERE team_id=%s AND user_id<>%s',(team_id,user['id'])):
            if '@'+str(m['user_id']) in body.body:await notify(c,m['user_id'],'mention','You were mentioned in squad chat','/squads/'+str(team_id),str(row['id']))
        return row
@app.patch('/api/v1/teams/{team_id}/messages/{message_id}')
async def edit_message(team_id:UUID,message_id:UUID,body:Message,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        row=await db.one(c,'UPDATE team_messages SET body=%s,edited_at=now() WHERE id=%s AND team_id=%s AND sender_id=%s AND deleted_at IS NULL RETURNING *',(body.body,message_id,team_id,user['id']))
        if not row:raise HTTPException(404,'Editable message not found')
        return row
@app.delete('/api/v1/teams/{team_id}/messages/{message_id}')
async def delete_message(team_id:UUID,message_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        row=await db.one(c,"UPDATE team_messages SET body='[deleted]',deleted_at=now() WHERE id=%s AND team_id=%s AND sender_id=%s RETURNING id",(message_id,team_id,user['id']))
        if not row:raise HTTPException(404,'Message not found')
        return {'deleted':True}
@app.post('/api/v1/teams/{team_id}/messages/read')
async def read_messages(team_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        await c.execute('INSERT INTO message_read_cursors(team_id,user_id) VALUES(%s,%s) ON CONFLICT(team_id,user_id) DO UPDATE SET read_at=now()',(team_id,user['id']))
    return {'read':True}
async def check_assignee(c,team_id,assignee_id):
    if assignee_id and not await db.one(c,'SELECT 1 FROM team_members WHERE team_id=%s AND user_id=%s',(team_id,assignee_id)):raise HTTPException(422,'Assignee must be a current squad member')
@app.post('/api/v1/teams/{team_id}/tasks',status_code=201)
async def create_task(team_id:UUID,body:Task,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id']);await check_assignee(c,team_id,body.assignee_id)
        row=await db.one(c,'INSERT INTO project_tasks(team_id,title,description,assignee_id,priority,deadline,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(team_id,body.title,body.description,body.assignee_id,body.priority,body.deadline,body.status,user['id']))
        await activity(c,team_id,user['id'],'task_created',{'title':body.title})
        if body.assignee_id:await notify(c,body.assignee_id,'task','Assigned: '+body.title,'/squads/'+str(team_id),str(row['id']))
        return row
@app.put('/api/v1/teams/{team_id}/tasks/{task_id}')
async def update_task(team_id:UUID,task_id:UUID,body:Task,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id']);await check_assignee(c,team_id,body.assignee_id)
        row=await db.one(c,'UPDATE project_tasks SET title=%s,description=%s,assignee_id=%s,priority=%s,deadline=%s,status=%s,version=version+1 WHERE id=%s AND team_id=%s AND version=%s RETURNING *',(body.title,body.description,body.assignee_id,body.priority,body.deadline,body.status,task_id,team_id,body.version))
        if not row:raise HTTPException(409,'Task changed on another device. Refresh before editing.')
        await activity(c,team_id,user['id'],'task_updated',{'title':body.title,'status':body.status});return row
@app.delete('/api/v1/teams/{team_id}/tasks/{task_id}')
async def remove_task(team_id:UUID,task_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id']);await c.execute('DELETE FROM project_tasks WHERE id=%s AND team_id=%s',(task_id,team_id));await activity(c,team_id,user['id'],'task_deleted')
    return {'deleted':True}
@app.get('/api/v1/teams/{team_id}/tasks/{task_id}/comments')
async def comments(team_id:UUID,task_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        return await db.all_rows(c,'SELECT tc.*,p.display_name FROM task_comments tc JOIN project_tasks t ON t.id=tc.task_id LEFT JOIN user_profiles p ON p.id=tc.user_id WHERE t.team_id=%s AND t.id=%s ORDER BY tc.created_at',(team_id,task_id))
@app.post('/api/v1/teams/{team_id}/tasks/{task_id}/comments')
async def add_comment(team_id:UUID,task_id:UUID,body:Message,user=Depends(actor)):
    if len(body.body)>2000:raise HTTPException(422,'Comments must be at most 2000 characters')
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        if not await db.one(c,'SELECT 1 FROM project_tasks WHERE id=%s AND team_id=%s',(task_id,team_id)):raise HTTPException(404,'Task not found')
        return await db.one(c,'INSERT INTO task_comments(task_id,user_id,body) VALUES(%s,%s,%s) RETURNING *',(task_id,user['id'],body.body))
@app.post('/api/v1/teams/{team_id}/milestones')
async def add_milestone(team_id:UUID,body:Milestone,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        return await db.one(c,'INSERT INTO milestones(team_id,title,completed,deadline) VALUES(%s,%s,%s,%s) RETURNING *',(team_id,body.title,body.completed,body.deadline))
@app.put('/api/v1/teams/{team_id}/milestones/{milestone_id}')
async def edit_milestone(team_id:UUID,milestone_id:UUID,body:Milestone,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        row=await db.one(c,'UPDATE milestones SET title=%s,completed=%s,deadline=%s WHERE id=%s AND team_id=%s RETURNING *',(body.title,body.completed,body.deadline,milestone_id,team_id))
        if not row:raise HTTPException(404,'Milestone not found')
        await activity(c,team_id,user['id'],'milestone_updated');return row
@app.post('/api/v1/teams/{team_id}/resources')
async def add_resource(team_id:UUID,body:Resource,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        return await db.one(c,'INSERT INTO project_resources(team_id,title,url,created_by) VALUES(%s,%s,%s,%s) RETURNING *',(team_id,body.title,body.url,user['id']))
@app.delete('/api/v1/teams/{team_id}/resources/{resource_id}')
async def delete_resource(team_id:UUID,resource_id:UUID,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'])
        await c.execute('DELETE FROM project_resources WHERE id=%s AND team_id=%s',(resource_id,team_id))
    return {'deleted':True}
@app.post('/api/v1/teams/{team_id}/copilot')
async def ai_help(team_id:UUID,body:CopilotRequest,user=Depends(actor)):
    async with db.connection() as c:
        t=await require_member(c,team_id,user['id'])
        members=await db.all_rows(c,'SELECT p.id,p.ai_consent FROM team_members m JOIN user_profiles p ON p.id=m.user_id WHERE m.team_id=%s',(team_id,))
        if not t['ai_consent'] or not all(x['ai_consent'] for x in members):raise HTTPException(403,'Leader and every current member must consent to sharing team context with Grok')
        e=await get_event(c,t['hackathon_id'])
        profiles=[await get_profile(c,m['id']) for m in members]
        tasks=await db.all_rows(c,'SELECT title,description,status,priority,deadline FROM project_tasks WHERE team_id=%s LIMIT 100',(team_id,))
        context={'hackathon':{'requirements':e['requirements'],'starts_at':e['starts_at'],'ends_at':e['ends_at']},'members':[{'roles':p['roles'],'skills':p['skills']} for p in profiles],'tasks':tasks}
    return await copilot(user['id'],team_id,body.prompt,context)
@app.get('/api/v1/notifications')
async def notifications(user=Depends(actor)):
    async with db.connection() as c:return await db.all_rows(c,'SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 100',(user['id'],))
@app.patch('/api/v1/notifications/{notification_id}')
async def read_notification(notification_id:UUID,user=Depends(actor)):
    async with db.connection() as c:await c.execute('UPDATE notifications SET read_at=now() WHERE id=%s AND user_id=%s',(notification_id,user['id']))
    return {'read':True}
@app.get('/api/v1/me/notification-preferences')
async def get_preferences(user=Depends(actor)):
    async with db.connection() as c:return await db.one(c,'SELECT notification_preferences FROM profile_preferences WHERE user_id=%s',(user['id'],)) or {'notification_preferences':{}}
@app.put('/api/v1/me/notification-preferences')
async def preferences(body:dict[str,bool],user=Depends(actor)):
    if not set(body)<= {'invitation','team','task','mention','deadline','event','cancellation'}:raise HTTPException(422,'Unknown notification type')
    async with db.connection() as c:await c.execute('INSERT INTO profile_preferences VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET notification_preferences=excluded.notification_preferences',(user['id'],Jsonb(body)))
    return {'saved':True}
@app.post('/api/v1/reports')
async def report(body:Report,user=Depends(actor)):
    async with db.connection() as c:return await db.one(c,'INSERT INTO abuse_reports(reporter_id,target_user_id,reason) VALUES(%s,%s,%s) RETURNING id',(user['id'],body.target_user_id,body.reason))
@app.put('/api/v1/blocks/{target_id}')
async def block(target_id:UUID,user=Depends(actor)):
    if str(target_id)==user['id']:raise HTTPException(422,'Cannot block yourself')
    async with db.connection() as c:
        await c.execute('INSERT INTO user_blocks VALUES(%s,%s) ON CONFLICT DO NOTHING',(user['id'],target_id))
        await c.execute("UPDATE team_invitations SET status='cancelled' WHERE status='pending' AND ((sender_id=%s AND recipient_id=%s) OR (sender_id=%s AND recipient_id=%s))",(user['id'],target_id,target_id,user['id']))
    return {'blocked':True}
@app.delete('/api/v1/blocks/{target_id}')
async def unblock(target_id:UUID,user=Depends(actor)):
    async with db.connection() as c:await c.execute('DELETE FROM user_blocks WHERE blocker_id=%s AND blocked_id=%s',(user['id'],target_id))
    return {'blocked':False}
@app.get('/api/v1/blocks')
async def blocks(user=Depends(actor)):
    async with db.connection() as c:return await db.all_rows(c,'SELECT b.blocked_id,p.display_name FROM user_blocks b JOIN user_profiles p ON p.id=b.blocked_id WHERE b.blocker_id=%s',(user['id'],))
async def save_event(c,body,event_id=None,source_id=None,reference=None):
    data=body.model_dump(exclude={'requirements'})
    data['last_verified_at']=datetime.now(timezone.utc) if body.verification_status=='verified' else None
    if event_id:
        if not await db.one(c,'SELECT 1 FROM hackathons WHERE id=%s',(event_id,)):raise HTTPException(404,'Hackathon not found')
        await c.execute('UPDATE hackathons SET '+','.join(k+'=%s' for k in data)+',updated_at=now() WHERE id=%s',(*data.values(),event_id))
    else:
        if source_id is None:
            source=await db.one(c,"INSERT INTO hackathon_sources(name,kind,reference,authorized) VALUES('Administrator submissions','manual','manual',true) ON CONFLICT(reference) DO UPDATE SET authorized=true RETURNING id")
            source_id=source['id']
        data['source_id']=source_id;data['source_reference']=reference or hashlib.sha256(body.registration_url.encode()).hexdigest()
        existing=await db.one(c,'SELECT id FROM hackathons WHERE registration_url=%s',(body.registration_url,))
        if existing:raise HTTPException(409,'An event with this registration URL already exists. Edit it instead.')
        row=await db.one(c,'INSERT INTO hackathons('+','.join(data)+') VALUES('+','.join(['%s']*len(data))+') RETURNING id',tuple(data.values()));event_id=row['id']
    await c.execute('DELETE FROM hackathon_requirements WHERE hackathon_id=%s',(event_id,))
    for skill in body.requirements:
        name=normalize_skill(skill.name)
        await c.execute('INSERT INTO skills VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(name,name,skill.category))
        await c.execute('INSERT INTO hackathon_requirements VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(event_id,name,skill.proficiency))
    await c.execute('DELETE FROM hackathon_recommendations WHERE hackathon_id=%s',(event_id,))
    return await get_event(c,event_id)
@app.get('/api/v1/admin/overview')
async def admin_overview(user=Depends(admin_user)):
    async with db.connection() as c:
        stats={}
        for table in ['user_profiles','hackathons','teams','imported_students','abuse_reports']:
            stats[table]=(await db.one(c,f'SELECT count(*) AS n FROM {table}'))['n']
        stats['ai_usage']=await db.one(c,"SELECT count(*) AS requests,coalesce(sum(input_tokens),0) AS input_tokens,coalesce(sum(output_tokens),0) AS output_tokens FROM ai_usage WHERE created_at>=date_trunc('day',now())")
        stats['integrations']={'telegram_configured':bool(settings().telegram_channel_id and settings().telegram_webhook_secret),'grok_configured':bool(settings().xai_api_key and settings().xai_model)}
        return stats
@app.get('/api/v1/admin/hackathons')
async def admin_events(user=Depends(admin_user)):
    async with db.connection() as c:
        rows=await db.all_rows(c,'SELECT id FROM hackathons ORDER BY updated_at DESC LIMIT 200')
        return [await get_event(c,r['id']) for r in rows]
@app.post('/api/v1/admin/hackathons',status_code=201)
async def admin_create_event(body:Event,user=Depends(admin_user)):
    async with db.connection() as c:
        e=await save_event(c,body);await audit(c,user['id'],'event_created',e['id']);return e
@app.put('/api/v1/admin/hackathons/{event_id}')
async def admin_edit_event(event_id:UUID,body:Event,user=Depends(admin_user)):
    async with db.connection() as c:
        old=await get_event(c,event_id);e=await save_event(c,body,event_id);await audit(c,user['id'],'event_updated',e['id'])
        if body.cancelled or old['registration_deadline']!=body.registration_deadline:
            subscribers=await db.all_rows(c,'SELECT user_id FROM hackathon_bookmarks WHERE hackathon_id=%s UNION SELECT user_id FROM team_members WHERE hackathon_id=%s',(event_id,event_id))
            for m in subscribers:await notify(c,m['user_id'],'cancellation' if body.cancelled else 'event',('Cancelled: ' if body.cancelled else 'Updated: ')+body.title,'/hackathons/'+str(event_id),'event:'+str(event_id)+':'+str(e['updated_at']))
        return e
@app.post('/api/v1/admin/import/preview')
async def preview_import(file:UploadFile=File(...),mapping:str=Form('{}'),user=Depends(admin_user)):
    try:map_data=json.loads(mapping)
    except ValueError:raise HTTPException(422,'Mapping must be a JSON object')
    if not isinstance(map_data,dict):raise HTTPException(422,'Mapping must be a JSON object')
    return inspect_import(await file.read(5*1024*1024+1),file.filename or '',map_data or None)
@app.post('/api/v1/admin/import/commit')
async def commit_import(file:UploadFile=File(...),mapping:str=Form('{}'),authorized:bool=Form(False),user=Depends(admin_user)):
    if not authorized:raise HTTPException(422,'Confirm authorization to import student records')
    try:map_data=json.loads(mapping)
    except ValueError:raise HTTPException(422,'Mapping must be a JSON object')
    if not isinstance(map_data,dict):raise HTTPException(422,'Mapping must be a JSON object')
    result=inspect_import(await file.read(5*1024*1024+1),file.filename or '',map_data or None)
    async with db.connection() as c:
        existing=await db.one(c,'SELECT summary FROM import_jobs WHERE digest=%s',(result['digest'],))
        if existing:return {**existing['summary'],'reimport':True}
        summary={'successful':0,'duplicates':len(result['duplicates']),'invalid':len(result['invalid']),'skipped':result['skipped']}
        job=await db.one(c,'INSERT INTO import_jobs(actor_id,digest,summary) VALUES(%s,%s,%s) RETURNING id',(user['id'],result['digest'],Jsonb(summary)))
        for r in result['valid']:
            row=await db.one(c,'INSERT INTO imported_students(email,display_name,institution,skills,import_job_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING RETURNING id',(r['email'],r['display_name'],r['institution'],Jsonb(r['skills']),job['id']))
            summary['successful' if row else 'duplicates']+=1
        await c.execute('UPDATE import_jobs SET summary=%s WHERE id=%s',(Jsonb(summary),job['id']))
        await audit(c,user['id'],'student_import',job['id'],summary)
        return summary
@app.post('/api/v1/admin/import/invite/{record_id}')
async def invite_claim(record_id:UUID,user=Depends(admin_user)):
    async with db.connection() as c:
        r=await db.one(c,'SELECT email,claimed_by FROM imported_students WHERE id=%s',(record_id,))
        if not r:raise HTTPException(404,'Imported student not found')
        if r['claimed_by']:raise HTTPException(409,'Student has already claimed the record')
    s=settings()
    if not s.supabase_service_role_key:raise HTTPException(503,'Invitation email is not configured')
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.post(s.supabase_url+'/auth/v1/invite',headers={'apikey':s.supabase_service_role_key,'Authorization':'Bearer '+s.supabase_service_role_key},json={'email':r['email']})
        if response.status_code>=400:raise HTTPException(503,'Invitation email failed. Check Supabase email configuration.')
    async with db.connection() as c:await audit(c,user['id'],'claim_invitation_sent',record_id)
    return {'invited':True}
@app.get('/api/v1/admin/{section}')
async def admin_section(section:str,user=Depends(admin_user)):
    tables={'students':('user_profiles','created_at'),'imports':('import_jobs','created_at'),'imported-students':('imported_students','created_at'),'ingestion':('ingestion_events','updated_at'),'jobs':('background_jobs','created_at'),'audit':('audit_logs','created_at'),'reports':('abuse_reports','created_at'),'sources':('hackathon_sources','id')}
    if section not in tables:raise HTTPException(404,'Unknown admin section')
    table,order=tables[section]
    async with db.connection() as c:return await db.all_rows(c,f'SELECT * FROM {table} ORDER BY {order} DESC LIMIT 200')
@app.patch('/api/v1/admin/reports/{report_id}')
async def resolve_report(report_id:UUID,user=Depends(admin_user)):
    async with db.connection() as c:
        await c.execute("UPDATE abuse_reports SET status='resolved' WHERE id=%s",(report_id,));await audit(c,user['id'],'report_resolved',report_id)
    return {'resolved':True}
@app.put('/api/v1/admin/students/{student_id}/hide')
async def moderate_student(student_id:UUID,user=Depends(admin_user)):
    async with db.connection() as c:
        await c.execute('UPDATE user_profiles SET discoverable=false,open_to_invitations=false WHERE id=%s',(student_id,));await audit(c,user['id'],'profile_hidden',student_id)
    return {'hidden':True}
@app.post('/api/v1/integrations/telegram')
async def telegram(request:Request,x_telegram_bot_api_secret_token:str|None=Header(None)):
    s=settings()
    if not s.telegram_webhook_secret or not secrets.compare_digest(x_telegram_bot_api_secret_token or '',s.telegram_webhook_secret):raise HTTPException(403,'Invalid webhook secret')
    payload=await request.json()
    if not isinstance(payload,dict):raise HTTPException(422,'Invalid Telegram update')
    post=payload.get('edited_channel_post') or payload.get('channel_post')
    if not post:return {'ignored':True}
    if str(post.get('chat',{}).get('id'))!=s.telegram_channel_id:raise HTTPException(403,'Channel is not authorized')
    reference=str(post.get('message_id',''))
    if not reference:raise HTTPException(422,'Missing message ID')
    content=post.get('text') or post.get('caption') or ''
    # Preserve origin for human review; do not send Telegram posts to AI.
    async with db.connection() as c:
        source=await db.one(c,"SELECT id FROM hackathon_sources WHERE reference=%s AND authorized=true",('telegram:'+s.telegram_channel_id,))
        if not source:raise HTTPException(403,'Administrator must authorize this source first')
        previous=await db.one(c,'SELECT id,payload FROM ingestion_events WHERE source_id=%s AND reference=%s',(source['id'],reference))
        if previous and previous['payload'].get('text')==content[:20000]:return {'queued':True,'duplicate':True,'id':previous['id']}
        row=await db.one(c,'INSERT INTO ingestion_events(source_id,reference,payload) VALUES(%s,%s,%s) ON CONFLICT(source_id,reference) DO UPDATE SET payload=excluded.payload,status=\'pending\',updated_at=now() RETURNING id',(source['id'],reference,Jsonb({'text':content[:20000],'source_reference':reference,'edited':bool(payload.get('edited_channel_post'))})))
        await c.execute("UPDATE hackathons SET verification_status='pending',quality_flags=array_append(quality_flags,'source_edited'),updated_at=now() WHERE source_id=%s AND source_reference=%s",(source['id'],reference))
        return {'queued':True,'id':row['id']}
class Source(Strict):
    name:str=Field(min_length=1,max_length=200)
    kind:Literal['telegram','export','feed']
    reference:str=Field(min_length=1,max_length=500)
    authorized:bool=False
@app.post('/api/v1/admin/sources')
async def source_create(body:Source,user=Depends(admin_user)):
    async with db.connection() as c:
        row=await db.one(c,'INSERT INTO hackathon_sources(name,kind,reference,authorized) VALUES(%s,%s,%s,%s) ON CONFLICT(reference) DO UPDATE SET name=excluded.name,authorized=excluded.authorized RETURNING *',(body.name,body.kind,body.reference,body.authorized))
        await audit(c,user['id'],'source_configured',row['id']);return row
class Backfill(Strict):
    source_id:UUID
    announcements:list[dict]=Field(max_length=500)
@app.post('/api/v1/admin/ingestion/backfill')
async def backfill(body:Backfill,user=Depends(admin_user)):
    async with db.connection() as c:
        if not await db.one(c,'SELECT 1 FROM hackathon_sources WHERE id=%s AND authorized=true',(body.source_id,)):raise HTTPException(403,'Source is not authorized')
        for i,a in enumerate(body.announcements):
            ref=str(a.get('reference') or hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest())
            await c.execute("INSERT INTO ingestion_events(source_id,reference,payload) VALUES(%s,%s,%s) ON CONFLICT(source_id,reference) DO UPDATE SET payload=excluded.payload,status='pending',updated_at=now()",(body.source_id,ref,Jsonb(a)))
        await audit(c,user['id'],'authorized_backfill',body.source_id,{'rows':len(body.announcements)})
    return {'queued':len(body.announcements)}
@app.post('/api/v1/admin/ingestion/{ingestion_id}/publish')
async def publish_ingestion(ingestion_id:UUID,body:Event,user=Depends(admin_user)):
    async with db.connection() as c:
        row=await db.one(c,'SELECT * FROM ingestion_events WHERE id=%s FOR UPDATE',(ingestion_id,))
        if not row:raise HTTPException(404,'Announcement not found')
        existing=await db.one(c,'SELECT id FROM hackathons WHERE source_id=%s AND source_reference=%s',(row['source_id'],row['reference']))
        event=await save_event(c,body,existing['id'] if existing else None,row['source_id'],row['reference'])
        await c.execute("UPDATE ingestion_events SET status='reviewed' WHERE id=%s",(ingestion_id,));await audit(c,user['id'],'announcement_reviewed',ingestion_id)
        return event
async def scheduled_checks():
    async with db.connection() as c:
        await c.execute('SELECT pg_advisory_xact_lock(823045)')
        stale=await c.execute("UPDATE hackathons SET verification_status='needs_correction',updated_at=now() WHERE verification_status='verified' AND last_verified_at<now()-(%s*interval '1 day')",(settings().verification_max_age_days,))
        profiles=await db.all_rows(c,'SELECT id FROM user_profiles WHERE onboarding_complete=true LIMIT 1000')
        ids=await db.all_rows(c,"SELECT id FROM hackathons WHERE verification_status='verified' AND NOT cancelled AND registration_deadline>now() LIMIT 1000")
        for uid in profiles:
            p=await get_profile(c,uid['id'])
            for row in ids:
                e=await get_event(c,row['id'])
                if actionable(e,max_age_days=settings().verification_max_age_days) and recommend(p,e)['actionable']:
                    await notify(c,uid['id'],'event','New opportunity: '+e['title'],'/hackathons/'+str(e['id']),'new-event:'+str(e['id']))
        deadlines=await db.all_rows(c,"SELECT b.user_id,h.id,h.title FROM hackathon_bookmarks b JOIN hackathons h ON h.id=b.hackathon_id WHERE NOT h.cancelled AND NOT h.registration_closed AND h.registration_deadline>now() AND h.registration_deadline<now()+interval '24 hours'")
        for row in deadlines:await notify(c,row['user_id'],'deadline','Registration closes soon: '+row['title'],'/hackathons/'+str(row['id']),'deadline:'+str(row['id']))
        tasks=await db.all_rows(c,"SELECT id,team_id,title,assignee_id FROM project_tasks WHERE assignee_id IS NOT NULL AND status<>'completed' AND deadline>now() AND deadline<now()+interval '24 hours'")
        for row in tasks:await notify(c,row['assignee_id'],'deadline','Task due soon: '+row['title'],'/squads/'+str(row['team_id']),'task-deadline:'+str(row['id']))
        await c.execute("DELETE FROM ai_cache WHERE expires_at<now()")
        await c.execute("DELETE FROM hackathon_recommendations WHERE created_at<now()-interval '30 days'")
        await c.execute("INSERT INTO background_jobs(kind,status,summary) VALUES('lifecycle','completed',%s)",(Jsonb({'stale_events':stale.rowcount}),))
        return {'checked':True,'stale_events':stale.rowcount}
@app.post('/api/v1/admin/sync')
async def admin_sync(user=Depends(admin_user)):
    result=await scheduled_checks()
    async with db.connection() as c:await audit(c,user['id'],'scheduled_checks_triggered')
    return result
@app.post('/api/v1/jobs/checks')
async def job_checks(x_job_secret:str|None=Header(None)):
    if not settings().job_secret or not secrets.compare_digest(x_job_secret or '',settings().job_secret):raise HTTPException(403,'Invalid job secret')
    return await scheduled_checks()
class MemberRole(Strict):
    assigned_role:str=Field(max_length=100)
    leader:bool=False
@app.put('/api/v1/teams/{team_id}/members/{member_id}/role')
async def assign_role(team_id:UUID,member_id:UUID,body:MemberRole,user=Depends(actor)):
    async with db.connection() as c:
        await require_member(c,team_id,user['id'],leader=True,lock=True)
        if not await db.one(c,'SELECT 1 FROM team_members WHERE team_id=%s AND user_id=%s',(team_id,member_id)):raise HTTPException(404,'Member not found')
        await c.execute('UPDATE team_members SET assigned_role=%s WHERE team_id=%s AND user_id=%s',(body.assigned_role,team_id,member_id))
        if body.leader:
            await c.execute("UPDATE team_members SET role=CASE WHEN user_id=%s THEN 'leader' ELSE 'member' END WHERE team_id=%s",(member_id,team_id))
            await c.execute('UPDATE teams SET leader_id=%s,ai_consent=false WHERE id=%s',(member_id,team_id))
        await activity(c,team_id,user['id'],'role_assigned',{'assigned_role':body.assigned_role})
    return {'saved':True}

"""Runs only against a disposable database with test auth.users; never a live Supabase project."""
import os
from uuid import UUID
import psycopg,pytest
from fastapi import Header
from fastapi.testclient import TestClient
from app.config import settings
from app.auth import current_user
from app.main import app
URL=os.getenv('TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Set TEST_DATABASE_URL to an isolated PostgreSQL test database')
IDS=['00000000-0000-0000-0000-00000000000'+str(i) for i in range(1,5)]
def execute(sql,params=()):
    with psycopg.connect(URL,autocommit=True) as c:return c.execute(sql,params).fetchall() if sql.lstrip().upper().startswith('SELECT') else c.execute(sql,params)

def test_telegram_feed_is_channel_scoped_and_excludes_removed_posts(client,monkeypatch):
    channel='-1001111222333'
    monkeypatch.setattr(settings(),'telegram_channel_id',channel)
    with psycopg.connect(URL,autocommit=True) as c:
        c.execute('DELETE FROM telegram_announcements WHERE channel_id IN (%s,%s)',(channel,'-1009999888777'))
        for cid,mid,text,relevant,deleted in [
            (channel,1,'Hackathon Alpha',True,False),
            (channel,2,'Hackathon Beta',True,False),
            (channel,3,'Removed hackathon',True,True),
            (channel,4,'Ordinary conversation',False,False),
            ('-1009999888777',1,'Other channel hackathon',True,False),
        ]:
            c.execute('''INSERT INTO telegram_announcements(channel_id,message_id,title,body,source_url,posted_at,relevant,deleted)
                VALUES(%s,%s,%s,%s,%s,now(),%s,%s)''',(cid,mid,text,text,'https://t.me/c/1111222333/'+str(mid),relevant,deleted))
    response=request(client,'get','/telegram/announcements?limit=1')
    assert response.status_code==200
    data=response.json()
    assert data['total']==2 and len(data['items'])==1
    assert data['items'][0]['title']=='Hackathon Beta'
    assert request(client,'get','/telegram/announcements?offset=1&limit=1').json()['items'][0]['title']=='Hackathon Alpha'
    assert request(client,'get','/telegram/announcements?q=Alpha').json()['total']==1
    assert request(client,'get','/telegram/announcements?limit=51').status_code==422
    with psycopg.connect(URL,autocommit=True) as c:
        c.execute("SET ROLE authenticated")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SELECT * FROM telegram_announcements')
@pytest.fixture(scope='module')
def client():
    s=settings();old=s.database_url;s.database_url=URL
    with psycopg.connect(URL,autocommit=True) as c:
        for i,uid in enumerate(IDS):
            c.execute('INSERT INTO auth.users(id,email) VALUES(%s,%s) ON CONFLICT DO NOTHING',(uid,f'fixture{i}@example.com'))
            c.execute('INSERT INTO user_profiles(id) VALUES(%s) ON CONFLICT DO NOTHING',(uid,))
            c.execute("INSERT INTO user_roles VALUES(%s,'student') ON CONFLICT DO NOTHING",(uid,))
        c.execute("INSERT INTO user_roles VALUES(%s,'admin') ON CONFLICT DO NOTHING",(IDS[0],))
    import time
    time.sleep(.1)
    async def fake_user(x_test_user:str=Header(IDS[0])):
        if x_test_user not in IDS:raise ValueError('Unknown synthetic test user')
        return {'id':x_test_user,'email':f'fixture{IDS.index(x_test_user)}@example.com','email_confirmed_at':'test'}
    app.dependency_overrides[current_user]=fake_user
    with TestClient(app) as client:yield client
    app.dependency_overrides.clear();s.database_url=old

def request(client,method,path,user=0,**kwargs):return getattr(client,method)('/api/v1'+path,headers={'X-Test-User':IDS[user]},**kwargs)
def test_full_database_journey(client):
    from datetime import datetime,timezone,timedelta
    now=datetime.now(timezone.utc)
    for i,uid in enumerate(IDS):
        p={'display_name':f'Synthetic Builder {i}','institution':'Fixture College','country':'India','onboarding_complete':True,'onboarding_step':6,'discoverable':True,'contact_consent':True,'open_to_invitations':True,'skills':[{'name':'Python' if i==0 else 'React','category':'technical','proficiency':2}], 'interests':['Education']}
        r=request(client,'put','/me',user=i,json=p);assert r.status_code==200,r.text
    event={'title':'SYNTHETIC integration challenge','description':'Test fixture, not a real event','registration_url':'https://example.com/fixture-register','source_url':'https://example.com/fixture','starts_at':(now+timedelta(days=2)).isoformat(),'ends_at':(now+timedelta(days=4)).isoformat(),'registration_deadline':(now+timedelta(days=1)).isoformat(),'verification_status':'verified','maximum_team_size':2,'requirements':[{'name':'Python','proficiency':2},{'name':'React','proficiency':1}]}
    r=request(client,'post','/admin/hackathons',json=event);assert r.status_code==201,r.text;eid=r.json()['id']
    r=request(client,'get','/hackathons');assert r.status_code==200 and len(r.json()['items'])==1
    r=request(client,'get',f'/hackathons/{eid}/teammates');assert r.status_code==200 and r.json()['items'];assert 'email' not in r.json()['items'][0]['profile'];assert 'availability' not in r.json()['items'][0]['profile']
    r=request(client,'post','/teams',json={'hackathon_id':eid,'name':'Fixture Squad'});assert r.status_code==201,r.text;tid=r.json()['id']
    invite=request(client,'post',f'/teams/{tid}/invitations',json={'recipient_id':IDS[1]});assert invite.status_code==201,invite.text
    duplicate=request(client,'post',f'/teams/{tid}/invitations',json={'recipient_id':IDS[1]});assert duplicate.status_code==409
    second=request(client,'post',f'/teams/{tid}/invitations',json={'recipient_id':IDS[2]});assert second.status_code==201
    stranger=request(client,'get',f'/teams/{tid}/messages',user=3);assert stranger.status_code==403
    accepted=request(client,'patch','/invitations/'+invite.json()['id'],user=1,json={'decision':'accepted'});assert accepted.status_code==200,accepted.text
    repeat=request(client,'patch','/invitations/'+invite.json()['id'],user=1,json={'decision':'accepted'});assert repeat.status_code==409
    overfilled=request(client,'patch','/invitations/'+second.json()['id'],user=2,json={'decision':'accepted'});assert overfilled.status_code==409
    message=request(client,'post',f'/teams/{tid}/messages',user=1,json={'body':'Persistent fixture message'});assert message.status_code==201,message.text
    mid=message.json()['id'];assert request(client,'get',f'/teams/{tid}/messages').json()[0]['body']=='Persistent fixture message'
    assert request(client,'patch',f'/teams/{tid}/messages/{mid}',json={'body':'Forged edit'}).status_code==404
    assert request(client,'patch',f'/teams/{tid}/messages/{mid}',user=1,json={'body':'Edited message'}).status_code==200
    task=request(client,'post',f'/teams/{tid}/tasks',json={'title':'Fixture task','assignee_id':IDS[1]});assert task.status_code==201,task.text
    task_id=task.json()['id'];body={'title':'Fixture task','assignee_id':IDS[1],'status':'completed','version':1}
    updated=request(client,'put',f'/teams/{tid}/tasks/{task_id}',json=body);assert updated.status_code==200
    assert request(client,'put',f'/teams/{tid}/tasks/{task_id}',json=body).status_code==409
    assert request(client,'get',f'/teams/{tid}').json()['progress']==100
    mile=request(client,'post',f'/teams/{tid}/milestones',json={'title':'MVP built'});assert mile.status_code==200
    assert request(client,'put',f'/teams/{tid}/milestones/'+mile.json()['id'],json={'title':'MVP built','completed':True}).status_code==200
    assert request(client,'post',f'/teams/{tid}/copilot',json={'prompt':'plan our work'}).status_code==403
    assert request(client,'get','/admin/overview',user=1).status_code==403
    assert request(client,'delete',f'/teams/{tid}/members/{IDS[1]}',user=1).status_code==200
    assert request(client,'get',f'/teams/{tid}/messages',user=1).status_code==403
    closed={**event,'registration_closed':True}
    assert request(client,'put',f'/admin/hackathons/{eid}',json=closed).status_code==200
    assert not request(client,'get','/hackathons').json()['items']
    assert request(client,'post','/teams',user=2,json={'hackathon_id':eid,'name':'Closed Event Squad'}).status_code==409

def query_in_app(client,sql,params=(),restricted=False):
    from app import db
    async def query():
        async with db.connection() as c:
            if restricted:
                await c.execute('SET LOCAL ROLE authenticated')
                await c.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(IDS[3],))
            return await db.all_rows(c,sql,params)
    return client.portal.call(query)

def test_import_preview_commit_reimport(client):
    content=b'Name,Email,Skills\nFixture A,import-fixture@example.com,Python\nDuplicate,import-fixture@example.com,React\nInvalid,no,JS\n'
    files={'file':('students.csv',content,'text/csv')}
    p=request(client,'post','/admin/import/preview',files=files);assert p.status_code==200,p.text
    assert len(p.json()['valid'])==1 and len(p.json()['duplicates'])==1
    first=request(client,'post','/admin/import/commit',files=files,data={'authorized':'true'});assert first.status_code==200,first.text;assert first.json()['successful']==1
    again=request(client,'post','/admin/import/commit',files=files,data={'authorized':'true'});assert again.json()['reimport'] is True
    assert query_in_app(client,"SELECT count(*) AS n FROM imported_students WHERE email='import-fixture@example.com'")[0]['n']==1

def test_row_level_security_isolation(client):
    assert query_in_app(client,'SELECT count(*) AS n FROM user_profiles',restricted=True)[0]['n']==1
    assert query_in_app(client,'SELECT count(*) AS n FROM team_messages',restricted=True)[0]['n']==0
    assert query_in_app(client,'SELECT count(*) AS n FROM teams',restricted=True)[0]['n']==0
    for table in ['imported_students','audit_logs','api_rate_limits','ai_usage']:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):query_in_app(client,'SELECT * FROM '+table,restricted=True)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):query_in_app(client,"INSERT INTO user_roles VALUES(%s,'admin')",(IDS[3],),restricted=True)
@pytest.mark.skipif(os.getenv('TEST_NATIVE_POSTGRES')!='1',reason='Requires native PostgreSQL concurrency; embedded runtime is single connection')
def test_simultaneous_invitation_acceptance(client):
    from datetime import datetime,timezone,timedelta
    from concurrent.futures import ThreadPoolExecutor
    now=datetime.now(timezone.utc)
    event={'title':'SYNTHETIC race challenge','registration_url':'https://example.com/race-fixture','source_url':'https://example.com/race-source','starts_at':(now+timedelta(days=2)).isoformat(),'ends_at':(now+timedelta(days=3)).isoformat(),'registration_deadline':(now+timedelta(days=1)).isoformat(),'verification_status':'verified','minimum_team_size':2,'maximum_team_size':2}
    r=request(client,'post','/admin/hackathons',json=event);assert r.status_code==201,r.text
    t=request(client,'post','/teams',user=1,json={'hackathon_id':r.json()['id'],'name':'Race fixture'});assert t.status_code==201,t.text
    tid=t.json()['id'];invitations=[]
    for i in [2,3]:
        invite=request(client,'post',f'/teams/{tid}/invitations',user=1,json={'recipient_id':IDS[i]});assert invite.status_code==201,invite.text;invitations.append((i,invite.json()['id']))
    def accept(entry):return request(client,'patch','/invitations/'+entry[1],user=entry[0],json={'decision':'accepted'}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(accept,invitations))
    assert sorted(results)==[200,409]
    assert len(request(client,'get','/teams/'+tid,user=1).json()['members'])==2
def test_telegram_duplicate_and_edit_review(client,monkeypatch):
    s=settings();monkeypatch.setattr(s,'telegram_channel_id','-100123456');monkeypatch.setattr(s,'telegram_webhook_secret','synthetic-webhook-secret')
    source=request(client,'post','/admin/sources',json={'name':'Synthetic authorized channel','kind':'telegram','reference':'telegram:-100123456','authorized':True});assert source.status_code==200
    post={'channel_post':{'chat':{'id':-100123456},'message_id':71,'text':'Synthetic owner announcement'}}
    headers={'X-Telegram-Bot-Api-Secret-Token':'synthetic-webhook-secret'}
    first=client.post('/api/v1/integrations/telegram',json=post,headers=headers);assert first.status_code==200,first.text
    duplicate=client.post('/api/v1/integrations/telegram',json=post,headers=headers);assert duplicate.status_code==200 and duplicate.json()['duplicate'] is True
    edited={'edited_channel_post':{**post['channel_post'],'text':'Edited synthetic owner announcement'}}
    changed=client.post('/api/v1/integrations/telegram',json=edited,headers=headers);assert changed.status_code==200 and changed.json()['id']==first.json()['id']
    wrong=client.post('/api/v1/integrations/telegram',json={'channel_post':{'chat':{'id':-100999},'message_id':1}},headers=headers);assert wrong.status_code==403

def test_71_synthetic_students_import(client):
    content=('Name,Email,Skills\n'+''.join(f'Synthetic Student {i},synthetic71-{i}@example.com,Python\n' for i in range(71))).encode()
    files={'file':('synthetic-71.csv',content,'text/csv')}
    preview=request(client,'post','/admin/import/preview',files=files);assert preview.status_code==200 and len(preview.json()['valid'])==71
    assert preview.json()['valid'][0]['skills'][0]['proficiency'] is None
    committed=request(client,'post','/admin/import/commit',files=files,data={'authorized':'true'});assert committed.status_code==200 and committed.json()['successful']==71
    assert query_in_app(client,'SELECT count(*) AS n FROM imported_students WHERE claimed_by IS NULL')[0]['n']>=71

def test_profile_claim_without_invented_proficiency(client):
    request(client,'put','/me',user=3,json={'display_name':'Synthetic Builder 3','country':'India','onboarding_complete':False})
    content=b'Name,Email,Skills\nSynthetic Claim,fixture3@example.com,Python\n'
    result=request(client,'post','/admin/import/commit',files={'file':('claim.csv',content,'text/csv')},data={'authorized':'true'});assert result.status_code==200
    claimed=request(client,'post','/me/claim-import',user=3);assert claimed.status_code==200,claimed.text
    assert claimed.json()['skills'][0]['proficiency'] is None
    assert claimed.json()['discoverable'] is False
    assert request(client,'post','/me/claim-import',user=3).status_code==409


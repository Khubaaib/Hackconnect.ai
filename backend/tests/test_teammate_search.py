from contextlib import asynccontextmanager
from uuid import UUID
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app, actor
from app.matching import rank_teammates, rank_candidates
from app.schemas import SearchIntent
from test_core import profile, candidate, event


def test_alias_search_finds_real_profiles_without_inventing_proficiency():
    rows=rank_teammates(profile(),[candidate('react',['React']),candidate('python',['Python'])],'Need React.js')
    assert [r['profile']['id'] for r in rows]==['react']
    c=candidate('unknown',['Python']);c['skills'][0]['proficiency']=None
    rows=rank_teammates(profile(),[c],'Python')
    assert rows[0]['unknown_proficiency']==['Python']

def test_ai_criteria_rank_relevant_profiles_and_no_fabricated_candidates():
    rows=rank_teammates(profile(),[candidate('one',['React']),candidate('two',['React','Python']),candidate('three',['Java'])],
        'Help me build a frontend',{'skills':['React','Python']})
    assert [r['profile']['id'] for r in rows]==['two','one']
    assert rows[0]['score']==100 and rows[1]['score']==50

def test_private_and_self_profiles_excluded():
    private=candidate('private',['React']);private['discoverable']=False
    assert rank_teammates(profile(),[private,candidate('me',['React'])])==[]

def test_fully_covered_event_still_recognizes_relevant_teammate():
    p=profile(skills=[{'name':s,'proficiency':3} for s in ['Python','React','UI/UX']])
    result=rank_candidates(p,event(),[candidate('r',['React'])])
    assert result[0]['score']>0 and 'react' in result[0]['explanation']

def test_unspecified_event_requirements_use_profile_relevance():
    e=event();e.update(requirements=[],domains=[])
    assert rank_candidates(profile(),e,[candidate('r',['React'])])[0]['score']>0

ME='00000000-0000-0000-0000-000000000001'
OTHER=UUID('00000000-0000-0000-0000-000000000002')
@pytest.fixture
def search_client(monkeypatch):
    import app.main as main
    @asynccontextmanager
    async def connection():yield object()
    async def get_profile(c,uid):return profile(id=ME,onboarding_complete=True)
    async def rows(c,sql,args):
        if 'SELECT p.*' in sql:
            # SQL enforces both block directions before any profile can reach the matcher.
            assert 'b.blocker_id=%s AND b.blocked_id=p.id' in sql
            assert 'b.blocked_id=%s AND b.blocker_id=p.id' in sql
            return [{**candidate(OTHER,['React']), 'visibility':{'institution':True},'display_name':'React Builder','bio':'Builder','experience':0,'email':'private@example.com'}]
        if 'FROM user_skills' in sql:return [{'user_id':OTHER,'name':'React','category':'technical','proficiency':2}]
        if 'FROM imported_students' in sql:return []
        raise AssertionError(sql)
    monkeypatch.setattr(main.db,'connection',connection)
    monkeypatch.setattr(main,'get_profile',get_profile)
    monkeypatch.setattr(main.db,'all_rows',rows)
    async def one(c,sql,args=()):return {'total':0}
    monkeypatch.setattr(main.db,'one',one)
    app.dependency_overrides[actor]=lambda:{'id':ME}
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_search_requires_auth():
    assert TestClient(app).post('/api/v1/teammates/search',json={}).status_code==401

def test_search_reads_fresh_profiles_and_redacts_private_data(search_client):
    for _ in range(2):
        r=search_client.post('/api/v1/teammates/search',json={'query':'React'})
        assert r.status_code==200,r.text
        data=r.json();assert data['total']==1 and data['mode']=='keyword'
        p=data['items'][0]['profile']
        assert p['id']==str(OTHER) and 'email' not in p and 'availability' not in p
    assert search_client.post('/api/v1/teammates/search',json={'query':'Java'}).json()['items']==[]
    assert search_client.post('/api/v1/teammates/search',json={'limit':100}).status_code==422

@pytest.mark.asyncio
async def test_provider_accepts_typed_search_intent(monkeypatch):
    import httpx
    from app.ai import GrokProvider
    from app.config import settings
    monkeypatch.setattr(settings(),'xai_api_key','test-only');monkeypatch.setattr(settings(),'xai_model','test-only')
    async def post(*a,**kw):
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"skills":["React"],"roles":[],"interests":[],"explanation":"Frontend work"}'}}]},request=httpx.Request('POST','https://api.x.ai/v1/chat/completions'))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    result,_=await GrokProvider().generate('frontend',{},SearchIntent,'Extract JSON criteria')
    assert result['skills']==['React']

def test_ai_search_uses_query_only_and_outage_falls_back(search_client,monkeypatch):
    import app.main as main
    async def ai(uid,team,prompt,context,model,instructions):
        assert context=={} and team is None and model is SearchIntent
        return {'skills':['React'],'roles':[],'interests':[],'explanation':'Frontend'}
    monkeypatch.setattr(main,'copilot',ai)
    r=search_client.post('/api/v1/teammates/search',json={'query':'frontend builder','use_ai':True})
    assert r.json()['mode']=='ai' and r.json()['total']==1
    async def outage(*a,**kw):raise HTTPException(503,'Unavailable')
    monkeypatch.setattr(main,'copilot',outage)
    r=search_client.post('/api/v1/teammates/search',json={'query':'React','use_ai':True})
    assert r.status_code==200 and r.json()['mode']=='keyword' and r.json()['notice'] and r.json()['total']==1

@pytest.mark.asyncio
@pytest.mark.parametrize('status,message,expected',[(401,'SECRET do not expose','API key was rejected'),(403,'insufficient credits SECRET','insufficient credits'),(404,'SECRET do not expose','model or endpoint was not found')])
async def test_provider_explains_config_failures_without_leaking_upstream(monkeypatch,status,message,expected):
    import httpx
    from app.ai import GrokProvider
    from app.config import settings
    monkeypatch.setattr(settings(),'xai_api_key','test-only');monkeypatch.setattr(settings(),'xai_model','test-only')
    calls=[]
    async def post(*a,**kw):
        calls.append(1)
        return httpx.Response(status,text=message,request=httpx.Request('POST','https://api.x.ai/v1/chat/completions'))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    with pytest.raises(HTTPException) as error:await GrokProvider().generate('test',{})
    assert expected in error.value.detail and 'SECRET' not in error.value.detail
    assert len(calls)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('upstream,category', [('Incorrect API key provided: SECRET','credential format'),('response_format is unsupported SECRET','structured output format'),('max_tokens unsupported SECRET','output token parameter'),('Insufficient credits SECRET','insufficient credits')])
async def test_bad_request_diagnostic_categories_hide_raw_details(monkeypatch,upstream,category):
    import httpx
    from app.ai import GrokProvider
    from app.config import settings
    monkeypatch.setattr(settings(),'xai_api_key','test-only');monkeypatch.setattr(settings(),'xai_model','test-only')
    async def post(*a,**kw):return httpx.Response(400,text=upstream,request=httpx.Request('POST','https://api.x.ai/v1/chat/completions'))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    with pytest.raises(HTTPException) as error:await GrokProvider().generate('test',{})
    assert category in error.value.detail and 'SECRET' not in error.value.detail


def test_imported_directory_records_are_explicit_and_not_invitable():
    imported={'id':'imported:fixture','display_name':'Imported Builder','skills':[{'name':'Python','proficiency':None}], '_imported_record':True}
    assert rank_teammates(profile(),[imported],'Python')==[]
    result=rank_teammates(profile(),[imported],'Python',allow_imported=True)
    assert len(result)==1 and result[0]['source']=='imported' and result[0]['can_invite'] is False
    assert result[0]['unknown_proficiency']==['Python']
    assert rank_candidates(profile(),event(),[imported])==[]
    assert rank_teammates(profile(),[imported],'Java',allow_imported=True)==[]

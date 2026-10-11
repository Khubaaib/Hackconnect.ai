import io
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from openpyxl import Workbook
from app.schemas import Profile,Event,Task,Resource,CopilotOutput
from app.matching import normalize_skill,lifecycle,actionable,recommend,rank_candidates,optimize_squad
from app.importer import inspect_import
NOW=datetime(2026,10,11,12,tzinfo=timezone.utc)
def event(**kw):
    return dict(id='event',requirements=[{'name':'Python','proficiency':2},{'name':'React','proficiency':1},{'name':'UI/UX','proficiency':1}],roles=['Backend Developer'],domains=['Education'],format='online',verification_status='verified',last_verified_at=NOW,starts_at=NOW+timedelta(days=2),ends_at=NOW+timedelta(days=4),registration_deadline=NOW+timedelta(days=1),**kw)
def profile(**kw):
    result=dict(id='me',skills=[{'name':'Python','proficiency':2}],interests=['Education'],roles=['Backend Developer'],country='India',institution='College',format='online',availability=[])
    result.update(kw);return result
@pytest.mark.parametrize('a,b',[(' JS ','javascript'),('React.js','react'),('ML','machine learning'),('Custom Skill','custom skill')])
def test_skill_aliases(a,b):assert normalize_skill(a)==b
@pytest.mark.parametrize('offset,status',[(timedelta(days=-1),'closed'),(timedelta(seconds=0),'closed'),(timedelta(days=1),'open')])
def test_registration_boundary(offset,status):
    e=event();e['registration_deadline']=NOW+offset
    assert lifecycle(e,NOW)['registration_status']==status

def test_ongoing_is_not_open_registration():
    e=event();e.update(starts_at=NOW-timedelta(days=1),registration_deadline=NOW-timedelta(hours=1))
    assert lifecycle(e,NOW)=={'event_status':'ongoing','registration_status':'closed'}
    assert not actionable(e,NOW)
@pytest.mark.parametrize('change',[{'cancelled':True},{'verification_status':'pending'},{'last_verified_at':NOW-timedelta(days=15)},{'registration_deadline':None},{'ends_at':NOW-timedelta(hours=1)}])
def test_excludes_unavailable_events(change):
    e=event();e.update(change);assert not actionable(e,NOW)
def test_transparent_score():
    r=recommend(profile(),event());assert r['matching_skills']==['python'];assert 'react' in r['missing_skills'];assert 0<=r['score']<=100;assert 'schedule' not in r['components'];assert r['unknowns']
def test_hard_eligibility_overrides_score():
    r=recommend(profile(),event(eligible_countries=['USA']));assert not r['actionable'];assert r['eligibility_checks']
def test_no_skills_is_valid_and_not_fabricated():
    r=recommend(profile(skills=[]),event());assert not r['matching_skills'];assert len(r['missing_skills'])==3

def candidate(id,skills,**kw):
    return profile(id=id,skills=[{'name':s,'proficiency':2} for s in skills],discoverable=True,contact_consent=True,open_to_invitations=True,onboarding_complete=True,**kw)
def test_complementary_matching():
    ranked=rank_candidates(profile(),event(),[candidate('same',['Python']),candidate('complement',['React','UI/UX'])]);assert ranked[0]['profile']['id']=='complement';assert ranked[0]['contributed_skills']==['react','ui/ux']
@pytest.mark.parametrize('key',['discoverable','contact_consent','open_to_invitations','onboarding_complete'])
def test_consent_gates(key):
    c=candidate('x',['React']);c[key]=False;assert not rank_candidates(profile(),event(),[c])
def test_optimization_bounded_and_capacity():
    ranked=rank_candidates(profile(),event(),[candidate(str(i),['React'] if i%2 else ['UI/UX']) for i in range(100)])
    result=optimize_squad(ranked,1);assert len(result['members'])<=1;assert optimize_squad(ranked,0)['members']==[]
def test_pairwise_availability():
    one=[{'starts_at':NOW,'ends_at':NOW+timedelta(hours=1)}];two=[{'starts_at':NOW+timedelta(hours=2),'ends_at':NOW+timedelta(hours=3)}]
    ranked=[{'profile':candidate('a',['React'],availability=one),'score':90,'contributed_skills':['react']},{'profile':candidate('b',['UI/UX'],availability=two),'score':90,'contributed_skills':['ui/ux']}]
    assert len(optimize_squad(ranked,2)['members'])==1
@pytest.mark.parametrize('url',['javascript:alert(1)','http://example.com','https://user:password@example.com','https://localhost/test'])
def test_resource_url_validation(url):
    with pytest.raises(ValidationError):Resource(title='test',url=url)
def test_profile_rejects_privilege_escalation():
    with pytest.raises(ValidationError):Profile(display_name='x',is_admin=True)
def test_discovery_consent_required():
    with pytest.raises(ValidationError):Profile(discoverable=True,contact_consent=False)
def test_timezone_validation():
    with pytest.raises(ValidationError):Profile(timezone='Made/Up')
def test_verified_event_requires_confirmed_dates():
    with pytest.raises(ValidationError):Event(title='Challenge',registration_url='https://example.com/register',source_url='https://example.com',verification_status='verified')
def test_naive_event_dates_rejected():
    with pytest.raises(ValidationError):Event(title='Challenge',registration_url='https://example.com/register',source_url='https://example.com',starts_at='2026-12-01T12:00:00')
def test_csv_import_duplicate_and_invalid():
    r=inspect_import(b'Name,Email,Skills\nOne,one@example.com,JS\nTwo,one@example.com,ML\nThree,bad,Python\n','students.csv')
    assert len(r['valid'])==1 and len(r['invalid'])==1 and len(r['duplicates'])==1
    assert r['valid'][0]['skills'][0]['name']=='javascript'
def test_excel_import():
    w=Workbook();s=w.active;s.append(['Full Name','Email Address','College']);s.append(['Synthetic Student','fixture@example.com','Test College']);b=io.BytesIO();w.save(b)
    result=inspect_import(b.getvalue(),'students.xlsx');assert result['valid'][0]['institution']=='Test College'
def test_explicit_mapping():
    r=inspect_import(b'Person,Contact\nFixture,fixture@example.com\n','students.csv',{'display_name':'Person','email':'Contact'});assert len(r['valid'])==1
def test_oversize_import():
    with pytest.raises(HTTPException) as exc:inspect_import(b'x'*(5*1024*1024+1),'x.csv')
    assert exc.value.status_code==413
@pytest.mark.asyncio
async def test_grok_missing_config_safe():
    from app.ai import GrokProvider
    with pytest.raises(HTTPException) as exc:await GrokProvider().generate('plan',{})
    assert exc.value.status_code==503
@pytest.mark.asyncio
async def test_grok_rejects_malformed_output(monkeypatch):
    import httpx
    from app.ai import GrokProvider
    from app.config import settings
    s=settings();monkeypatch.setattr(s,'xai_api_key','test-only');monkeypatch.setattr(s,'xai_model','test-only')
    async def post(*a,**kw):return httpx.Response(200,json={'choices':[{'message':{'content':'{"answer":"fake", "suggested_tasks":[]}'}}]},request=httpx.Request('POST','https://api.x.ai/v1/chat/completions'))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    with pytest.raises(HTTPException) as exc:await GrokProvider().generate('plan',{})
    assert exc.value.status_code==503
@pytest.mark.asyncio
async def test_invalid_auth_token_rejected(monkeypatch):
    import httpx
    from app.auth import current_user
    from app.config import settings
    from fastapi.security import HTTPAuthorizationCredentials
    s=settings();monkeypatch.setattr(s,'supabase_url','https://fixture.supabase.co');monkeypatch.setattr(s,'supabase_anon_key','test-only')
    async def get(*a,**kw):return httpx.Response(401,json={'message':'Invalid token'},request=httpx.Request('GET','https://fixture.supabase.co/auth/v1/user'))
    monkeypatch.setattr(httpx.AsyncClient,'get',get)
    with pytest.raises(HTTPException) as exc:await current_user(HTTPAuthorizationCredentials(scheme='Bearer',credentials='test-only'))
    assert exc.value.status_code==401
@pytest.mark.asyncio
async def test_unverified_email_rejected(monkeypatch):
    import httpx
    from app.auth import current_user
    from app.config import settings
    from fastapi.security import HTTPAuthorizationCredentials
    s=settings();monkeypatch.setattr(s,'supabase_url','https://fixture.supabase.co');monkeypatch.setattr(s,'supabase_anon_key','test-only')
    async def get(*a,**kw):return httpx.Response(200,json={'id':'00000000-0000-0000-0000-000000000001'},request=httpx.Request('GET','https://fixture.supabase.co/auth/v1/user'))
    monkeypatch.setattr(httpx.AsyncClient,'get',get)
    with pytest.raises(HTTPException) as exc:await current_user(HTTPAuthorizationCredentials(scheme='Bearer',credentials='test-only'))
    assert exc.value.status_code==403

def test_unknown_proficiency_not_invented():
    result=recommend(profile(skills=[{'name':'Python','proficiency':None}]),event())
    assert not result['matching_skills'] and result['components']['skills']==0

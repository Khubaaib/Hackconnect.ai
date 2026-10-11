from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from pydantic import BaseModel,Field,ConfigDict,field_validator,model_validator
from typing import Literal
from urllib.parse import urlsplit
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
def safe_url(value):
    if value is None or value=='': return None
    u=urlsplit(str(value))
    if u.scheme!='https' or not u.hostname or u.username or u.password: raise ValueError('Use a public HTTPS URL without embedded credentials')
    if u.hostname in ('localhost','127.0.0.1','::1') or u.hostname.endswith('.local'): raise ValueError('Use a public HTTPS URL')
    return str(value)
class Skill(Strict):
    name:str=Field(min_length=1,max_length=80)
    category:Literal['technical','nontechnical']='technical'
    proficiency:int|None=Field(default=None,ge=1,le=3)
class Availability(Strict):
    starts_at:datetime
    ends_at:datetime
    @model_validator(mode='after')
    def dates(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at<=self.starts_at: raise ValueError('Availability needs timezone-aware, increasing dates')
        return self
class Profile(Strict):
    display_name:str=Field(default='',max_length=100)
    institution:str=Field(default='',max_length=200)
    degree:str=Field(default='',max_length=100)
    year_of_study:str=Field(default='',max_length=30)
    city:str=Field(default='',max_length=100)
    country:str=Field(default='',max_length=100)
    timezone:str='UTC'
    bio:str=Field(default='',max_length=1000)
    github_url:str|None=None
    linkedin_url:str|None=None
    portfolio_url:str|None=None
    avatar_url:str|None=None
    skills:list[Skill]=Field(default_factory=list,max_length=100)
    roles:list[str]=Field(default_factory=list,max_length=20)
    interests:list[str]=Field(default_factory=list,max_length=30)
    format:Literal['any','online','offline','hybrid']='any'
    travel_willing:bool=False
    preferred_team_size:int=Field(default=4,ge=2,le=10)
    experience:int=Field(default=0,ge=0,le=100)
    onboarding_step:int=Field(default=0,ge=0,le=6)
    onboarding_complete:bool=False
    discoverable:bool=False
    open_to_invitations:bool=False
    contact_consent:bool=False
    ai_consent:bool=False
    visibility:dict[str,bool]=Field(default_factory=lambda:{'institution':True,'city':False,'links':True})
    availability:list[Availability]=Field(default_factory=list,max_length=30)
    _urls=field_validator('github_url','linkedin_url','portfolio_url','avatar_url')(safe_url)
    @field_validator('timezone')
    @classmethod
    def tz(cls,v):
        try:ZoneInfo(v)
        except ZoneInfoNotFoundError:raise ValueError('Unknown time zone')
        return v
    @model_validator(mode='after')
    def consent(self):
        if self.discoverable and not self.contact_consent:raise ValueError('Discoverability requires contact consent')
        if self.onboarding_complete and (not self.display_name.strip() or not self.country.strip()):raise ValueError('Name and country are required to complete onboarding')
        return self
class Event(Strict):
    title:str=Field(min_length=3,max_length=200)
    description:str=Field(default='',max_length=10000)
    organizer:str|None=None
    domains:list[str]=Field(default_factory=list,max_length=30)
    roles:list[str]=Field(default_factory=list,max_length=20)
    registration_url:str
    source_url:str
    registration_opens_at:datetime|None=None
    registration_deadline:datetime|None=None
    starts_at:datetime|None=None
    ends_at:datetime|None=None
    format:Literal['online','offline','hybrid']='online'
    location:str|None=None
    country:str|None=None
    eligibility:str|None=None
    eligible_countries:list[str]=Field(default_factory=list)
    student_only:bool=False
    minimum_team_size:int=Field(default=2,ge=1,le=10)
    maximum_team_size:int=Field(default=4,ge=1,le=10)
    prizes:str|None=None
    cancelled:bool=False
    registration_closed:bool=False
    verification_status:Literal['pending','verified','needs_correction','rejected']='pending'
    quality_flags:list[str]=Field(default_factory=list)
    requirements:list[Skill]=Field(default_factory=list,max_length=100)
    _urls=field_validator('registration_url','source_url')(safe_url)
    @model_validator(mode='after')
    def dates(self):
        for key in ('registration_opens_at','registration_deadline','starts_at','ends_at'):
            value=getattr(self,key)
            if value and not value.tzinfo:raise ValueError('Event dates must include a time zone')
        if any(s.proficiency is None for s in self.requirements):raise ValueError('Specify proficiency for every event skill requirement')
        if self.maximum_team_size<self.minimum_team_size:raise ValueError('Invalid team size range')
        if self.starts_at and self.ends_at and self.ends_at<self.starts_at:raise ValueError('End precedes start')
        if self.registration_opens_at and self.registration_deadline and self.registration_deadline<self.registration_opens_at:raise ValueError('Registration deadline precedes opening')
        if self.verification_status=='verified' and (not self.starts_at or not self.registration_deadline):raise ValueError('Verify start and registration deadline before publishing')
        return self
class TeamCreate(Strict):
    hackathon_id:UUID
    name:str=Field(min_length=1,max_length=100)
class InvitationCreate(Strict):recipient_id:UUID
class InvitationResponse(Strict):decision:Literal['accepted','declined']
class Message(Strict):body:str=Field(min_length=1,max_length=4000)
class Task(Strict):
    title:str=Field(min_length=1,max_length=200)
    description:str=Field(default='',max_length=5000)
    assignee_id:UUID|None=None
    priority:Literal['low','medium','high']='medium'
    deadline:datetime|None=None
    status:Literal['todo','in_progress','in_review','completed']='todo'
    version:int=Field(default=1,ge=1)
    @field_validator('deadline')
    @classmethod
    def aware(cls,v):
        if v and not v.tzinfo:raise ValueError('Deadline must include a time zone')
        return v
class Milestone(Strict):
    title:str=Field(min_length=1,max_length=200)
    completed:bool=False
    deadline:datetime|None=None
    @field_validator('deadline')
    @classmethod
    def aware(cls,v):
        if v and not v.tzinfo:raise ValueError('Deadline must include a time zone')
        return v
class Resource(Strict):
    title:str=Field(min_length=1,max_length=200)
    url:str
    _url=field_validator('url')(safe_url)
class CopilotRequest(Strict):prompt:str=Field(min_length=3,max_length=2000)
class SuggestedTask(Strict):
    title:str=Field(max_length=200)
    description:str=Field(max_length=3000)
class CopilotOutput(Strict):
    answer:str=Field(max_length=10000)
    suggested_tasks:list[SuggestedTask]=Field(max_length=20)
    caveats:list[str]=Field(max_length=10)
class Report(Strict):
    target_user_id:UUID
    reason:str=Field(min_length=5,max_length=2000)
class TeamSettings(Strict):
    name:str=Field(min_length=1,max_length=100)
    ai_consent:bool=False

from datetime import datetime,timezone,timedelta
from itertools import combinations
import hashlib,json,re
ALIASES={'js':'javascript','ts':'typescript','py':'python','reactjs':'react','react.js':'react','nextjs':'next.js','next js':'next.js','ml':'machine learning','ai/ml':'machine learning','postgres':'postgresql','ux':'ui/ux','ui ux':'ui/ux','public-speaking':'public speaking'}
def normalize_skill(name):
    value=re.sub(r'\s+',' ',name.strip().lower())
    return ALIASES.get(value,value)
def lifecycle(event,now=None):
    now=now or datetime.now(timezone.utc)
    if event.get('cancelled'):state='cancelled'
    elif event.get('ends_at') and now>=event['ends_at']:state='completed'
    elif event.get('starts_at') and now>=event['starts_at']:state='ongoing'
    elif event.get('starts_at'):state='upcoming'
    else:state='unknown'
    if event.get('registration_closed') or event.get('cancelled'):registration='closed'
    elif event.get('registration_deadline') and now>=event['registration_deadline']:registration='closed'
    elif event.get('registration_opens_at') and now<event['registration_opens_at']:registration='not_yet_open'
    elif event.get('registration_deadline'):registration='open'
    else:registration='unknown'
    return {'event_status':state,'registration_status':registration}
def actionable(event,now=None,max_age_days=14):
    now=now or datetime.now(timezone.utc);state=lifecycle(event,now)
    verified=event.get('last_verified_at')
    return event.get('verification_status')=='verified' and verified is not None and now-verified<=timedelta(days=max_age_days) and state['registration_status']=='open' and state['event_status'] in ('upcoming','ongoing')
def eligible(profile,event):
    reasons=[]
    countries={x.casefold() for x in event.get('eligible_countries',[])}
    if countries and profile.get('country','').casefold() not in countries:reasons.append('Country eligibility is not met')
    if event.get('student_only') and not profile.get('institution'):reasons.append('Student eligibility needs verification')
    if event.get('format')=='offline' and not profile.get('travel_willing') and profile.get('city','').casefold()!=str(event.get('location') or '').casefold():reasons.append('Travel or location requirement is not met')
    if event.get('eligibility') and not countries and not event.get('student_only'):reasons.append('Additional eligibility rules require your review')
    return reasons
def overlap(a,b):
    return sum(max(0,(min(x['ends_at'],y['ends_at'])-max(x['starts_at'],y['starts_at'])).total_seconds()) for x in a for y in b)
def available(profile,event):
    slots=profile.get('availability',[])
    if not slots or not event.get('starts_at') or not event.get('ends_at'):return None
    return overlap(slots,[{'starts_at':event['starts_at'],'ends_at':event['ends_at']}])>0
WEIGHTS={'skills':.30,'interests':.25,'roles':.15,'schedule':.10,'experience':.10,'format':.10}
def recommend(profile,event):
    req={normalize_skill(s['name']):(s.get('proficiency') or 1) for s in event.get('requirements',[])}
    own={normalize_skill(s['name']):(s.get('proficiency') or 0) for s in profile.get('skills',[])}
    evidence={};unknown=[]
    matched=[s for s in req if own.get(s,0)>=req[s]]
    if req:evidence['skills']=sum(min(own.get(s,0)/level,1) for s,level in req.items())/len(req)
    else:unknown.append('Required skills are not specified')
    interests=set(s.casefold() for s in profile.get('interests',[])); domains=set(s.casefold() for s in event.get('domains',[]))
    if domains:evidence['interests']=len(interests&domains)/len(domains)
    else:unknown.append('Domain fit is unknown')
    roles=set(profile.get('roles',[])); required_roles=set(event.get('roles',[]))
    if required_roles:evidence['roles']=len(roles&required_roles)/len(required_roles)
    else:unknown.append('Role requirements are unspecified')
    fit=available(profile,event)
    if fit is not None:evidence['schedule']=float(fit)
    else:unknown.append('Schedule compatibility is unknown')
    unknown.append('Experience fit is not scored without event experience requirements')
    evidence['format']=float(profile.get('format','any') in ('any',event.get('format')))
    denominator=sum(WEIGHTS[k] for k in evidence)
    score=round(100*sum(WEIGHTS[k]*v for k,v in evidence.items())/denominator) if denominator else 0
    blockers=eligible(profile,event)
    if fit is False:blockers.append('Your availability does not overlap the event')
    return {'score':score,'score_label':'Profile fit, not a probability of acceptance','version':'v1','matching_skills':matched,'missing_skills':[s for s in req if s not in matched],'components':evidence,'unknowns':unknown,'eligibility_checks':blockers,'actionable':not blockers and fit is not False,'explanation':('Relevant skills: '+', '.join(matched)) if matched else 'Review the skills and eligibility before applying.'}
def rank_candidates(profile,event,candidates,current_members=()):
    requirements={normalize_skill(s['name']):(s.get('proficiency') or 1) for s in event.get('requirements',[])}
    covered={normalize_skill(s['name']) for p in [profile,*current_members] for s in p.get('skills',[]) if (s.get('proficiency') or 0)>=requirements.get(normalize_skill(s['name']),1)}
    missing=set(requirements)-covered
    ranked=[]
    for c in candidates:
        if not all(c.get(k) for k in ('discoverable','contact_consent','open_to_invitations','onboarding_complete')) or str(c['id'])==str(profile['id']) or eligible(c,event) or available(c,event) is False:continue
        common=overlap(profile.get('availability',[]),c.get('availability',[])) if profile.get('availability') and c.get('availability') else None
        if common==0:continue
        skills={normalize_skill(s['name']) for s in c.get('skills',[]) if (s.get('proficiency') or 0)>=requirements.get(normalize_skill(s['name']),1)}
        contribution=skills&missing
        denominator=len(missing) or 1
        score=round(80*len(contribution)/denominator+(10 if common else 0)+(10 if set(c.get('interests',[]))&set(event.get('domains',[])) else 0))
        ranked.append({'profile':c,'score':score,'contributed_skills':sorted(contribution),'remaining_gaps':sorted(missing-contribution),'availability_known':common is not None,'explanation':'Covers '+(', '.join(sorted(contribution)) or 'no additional required skills')})
    return sorted(ranked,key=lambda x:(-x['score'],str(x['profile']['id'])))
def optimize_squad(ranked,slots):
    # Exhaustive search only over 15 candidates and at most 4 seats: <=1940 combinations.
    pool=ranked[:15];slots=min(max(slots,0),4,len(pool))
    if not slots:return {'members':[],'coverage':[],'limited_search':True}
    best=();best_key=(-1,-1)
    for n in range(1,slots+1):
        for group in combinations(pool,n):
            members=[x['profile'] for x in group]
            if any(a.get('availability') and b.get('availability') and overlap(a['availability'],b['availability'])==0 for a,b in combinations(members,2)):continue
            coverage=set(s for x in group for s in x['contributed_skills']);key=(len(coverage),sum(x['score'] for x in group))
            if key>best_key:best=group;best_key=key
    return {'members':list(best),'coverage':sorted(set(s for x in best for s in x['contributed_skills'])),'limited_search':True,'note':'Proposal only. Invitations and acceptance are required. Search is bounded to 15 candidates and 4 additional seats.'}
def input_hash(profile,event):
    return hashlib.sha256(json.dumps([profile,event],sort_keys=True,default=str).encode()).hexdigest()

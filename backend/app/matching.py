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
        # Once gaps are filled, measure event relevance rather than dividing by an empty gap set.
        targets=missing or set(requirements)
        signals=[(.8,len(skills&targets)/len(targets))] if targets else []
        domains={s.casefold() for s in event.get('domains',[])}
        if domains:signals.append((.1,len({s.casefold() for s in c.get('interests',[])}&domains)/len(domains)))
        if common is not None:signals.append((.1,float(common>0)))
        if not signals:
            base=rank_teammates(profile,[c])
            score=base[0]['score'] if base else 0
        else:score=round(100*sum(w*v for w,v in signals)/sum(w for w,v in signals))
        explanation=('Covers '+', '.join(sorted(contribution))) if contribution else ('Relevant event skills: '+', '.join(sorted(skills&targets)) if skills&targets else 'No additional required skills verified; review their profile')
        ranked.append({'profile':c,'score':score,'contributed_skills':sorted(contribution),'remaining_gaps':sorted(missing-contribution),'availability_known':common is not None,'explanation':explanation})
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

def query_terms(query):
    words=re.findall(r'[\w.+/#-]+',query.casefold())
    stop={'i','a','an','the','for','and','or','with','who','can','is','in','to','me','my','need','find','want','looking','someone','teammate','teammates','student','students','build','project','using','help','please'}
    return {normalize_skill(w) for w in words if w not in stop}

def rank_teammates(profile,candidates,query='',intent=None):
    """Search actual opted-in profiles; unknown proficiency remains unknown."""
    intent=intent or {}
    requested={normalize_skill(s) for s in intent.get('skills',[])}
    roles={s.casefold() for s in intent.get('roles',[])}
    interests={s.casefold() for s in intent.get('interests',[])}
    terms=query_terms(query)
    own={normalize_skill(s['name']) for s in profile.get('skills',[])}
    ranked=[]
    for c in candidates:
        if str(c['id'])==str(profile['id']) or not all(c.get(k) for k in ('discoverable','contact_consent','open_to_invitations','onboarding_complete')):continue
        skills={normalize_skill(s['name']) for s in c.get('skills',[])}
        c_roles={s.casefold() for s in c.get('roles',[])}
        c_interests={s.casefold() for s in c.get('interests',[])}
        # Only fields eligible for public discovery participate in text search.
        text=' '.join([c.get('display_name',''),c.get('bio',''),*skills,*c_roles,*c_interests]).casefold()
        text_terms=query_terms(text)
        text_hits={s for s in terms if s in text_terms or s in skills}
        matches=skills&requested
        role_hits=roles&c_roles;interest_hits=interests&c_interests
        if query.strip():
            if not (text_hits or matches or role_hits or interest_hits):continue
            signals=[]
            if requested:signals.append((.7,len(matches)/len(requested)))
            if roles:signals.append((.2,len(role_hits)/len(roles)))
            if interests:signals.append((.1,len(interest_hits)/len(interests)))
            if not signals:signals=[(1,len(text_hits)/max(len(terms),1))]
            score=round(100*sum(w*v for w,v in signals)/sum(w for w,v in signals))
            if not score:continue
            evidence=sorted(matches or text_hits)+sorted(role_hits|interest_hits)
            explanation='Profile evidence: '+', '.join(evidence)
        else:
            shared=c_interests&{s.casefold() for s in profile.get('interests',[])}
            additional=skills-own
            # This is a browsing relevance score, not an invented AI confidence.
            score=round(100*(.6*len(additional)/max(len(skills),1)+.3*bool(shared)+.1*bool(c_roles-set(profile.get('roles',[])))))
            explanation=('Adds '+', '.join(sorted(additional))) if additional else 'Similar skills; discuss how to share the work'
            if shared:explanation+='; shared interests: '+', '.join(sorted(shared))
        ranked.append({'profile':c,'score':score,'explanation':explanation,'matching_skills':sorted(matches),'additional_skills':sorted(skills-own),'unknown_proficiency':[s['name'] for s in c.get('skills',[]) if s.get('proficiency') is None]})
    return sorted(ranked,key=lambda x:(-x['score'],str(x['profile']['id'])))

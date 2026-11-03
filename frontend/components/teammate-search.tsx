'use client';
import {FormEvent,useEffect,useRef,useState} from 'react';
import {api,send} from '@/lib/api';
import {Empty,ErrorBox,Loading} from '@/components/ui';

type Result={items:any[];total:number;searchable_profiles:number;registered_profiles?:number;imported_profiles?:number;imported_records_total?:number;mode:string;notice:string;criteria:{explanation?:string};bounded:boolean;score_label:string};
export default function TeammateSearch(){
 const[query,setQuery]=useState(''),[useAI,setUseAI]=useState(true),[data,setData]=useState<Result|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[offset,setOffset]=useState(0);
 const requestId=useRef(0),lastSearch=useRef({query:'',use_ai:false});
 async function search(q:string,ai:boolean,start=0){
  const current=++requestId.current;setLoading(true);setError('');
  try{const result=await api<Result>('/teammates/search',send('POST',{query:q,use_ai:ai,offset:start}));if(current===requestId.current){setData(result);setOffset(start);lastSearch.current={query:q,use_ai:ai};}}
  catch(e){if(current===requestId.current)setError((e as Error).message)}finally{if(current===requestId.current)setLoading(false)}
 }
 useEffect(()=>{search('',false);return()=>{requestId.current++}},[]);
 function submit(e:FormEvent){e.preventDefault();search(query,useAI)}
 return <section aria-label="Find teammates">
  <h2>Find your next teammate.</h2><p>Search students by skills, role, name, or what you want to build. You can explore teammates before choosing an event.</p>
  <form onSubmit={submit}>
   <div className="filters"><input aria-label="Search teammates" placeholder="Find a Python and React teammate for an education project…" value={query} maxLength={2000} onChange={e=>setQuery(e.target.value)}/><button className="button small" disabled={loading}>{loading?'Searching…':'Find teammates'}</button><button type="button" className="button secondary small" disabled={loading} onClick={()=>search(lastSearch.current.query,lastSearch.current.use_ai)}>Refresh profiles</button></div>
   <label className="check"><input type="checkbox" checked={useAI} onChange={e=>setUseAI(e.target.checked)}/>Use Grok to understand my search</label><p className="help">When enabled, your search text is sent to xAI. Student profiles stay in HackConnect. Results include registered students who enabled discovery and invitations, plus imported student records. Imported records show uploaded names, institutions, and skills; registration and consent are required before invitations.</p>
  </form>
  <ErrorBox error={error}/>{data?.notice&&<div className="notice" role="status">{data.notice}</div>}
  {loading?<Loading/>:data&&<>
   <p className="small-text" role="status">{data.total} results · {data.searchable_profiles} searchable profiles · {data.mode==='ai'?'AI-assisted search':data.mode==='keyword'?'Keyword search':'Suggested from your profile'}. {data.criteria.explanation}</p>
   {data.imported_profiles!==undefined&&<p className="small-text">{data.registered_profiles} registered profiles · {data.imported_profiles} imported candidates · {data.imported_records_total} uploaded records in total. Records linked to an account use that account’s privacy settings and appear once.</p>}
   {data.bounded&&<p className="notice">Searching the 1,000 most recently updated profiles.</p>}
   {data.items.length?<div className="cards">{data.items.map(c=><article className="card" key={c.profile.id}>
    <div className="card-top"><span className="tag">{c.source==='imported'?'Imported — not registered':c.profile.roles[0]||'Open role'}</span><span className="small-text">{c.score}% relevance</span></div>
    <h3>{c.profile.display_name}</h3>{c.profile.institution&&<p className="small-text">{c.profile.institution}</p>}<p>{c.profile.bio}</p>
    <div className="tags">{c.profile.skills.map((s:any)=><span key={s.name}>{s.name}{s.proficiency?' · '+['','Beginner','Intermediate','Advanced'][s.proficiency]:''}</span>)}</div>
    <p>{c.explanation}</p>{c.unknown_proficiency.length>0&&<p className="help">Proficiency not specified: {c.unknown_proficiency.join(', ')}.</p>}
    <p className="help">{c.source==='imported'?'Uploaded student record. Skills have not been confirmed by the student. Invitations become available after registration, profile completion, and consent.':'Choose a reviewed hackathon to create a squad and invite teammates.'} {data.score_label}.</p>
    <div className="card-actions">{c.source!=='imported'&&<a className="button small" href="/dashboard?tab=opportunities">Choose a hackathon</a>}{c.profile.github_url&&<a className="text-button" href={c.profile.github_url} target="_blank" rel="noopener noreferrer">GitHub ↗</a>}</div>
   </article>)}</div>:<Empty title={data.searchable_profiles?'No profiles match this search':'No teammates available yet'}><p>{data.searchable_profiles?'Try a specific skill such as Python, React, or UI/UX.':'No eligible registered profiles or unclaimed imported records are available. Registered students must enable discovery and invitations.'}</p><a className="button secondary small" href="/onboarding">Review my profile</a></Empty>}
   <div className="pagination"><button className="button secondary small" disabled={offset===0} onClick={()=>search(lastSearch.current.query,lastSearch.current.use_ai,Math.max(0,offset-20))}>Previous</button><span>{data.total?offset+1:0}–{Math.min(offset+20,data.total)} of {data.total} results</span><button className="button secondary small" disabled={offset+20>=data.total} onClick={()=>search(lastSearch.current.query,lastSearch.current.use_ai,offset+20)}>Next</button></div>
  </>}
 </section>
}

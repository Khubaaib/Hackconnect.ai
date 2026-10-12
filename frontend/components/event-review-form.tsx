'use client';
import {Field} from '@/components/ui';
function localDate(value:string|null){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?'':new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
export default function EventReviewForm({value,onChange}:{value:any;onChange:(value:any)=>void}){
 const set=(key:string,next:any)=>onChange({...value,[key]:next});
 const skills=value.requirements||[];
 return <>
  <Field label="Hackathon title"><input value={value.title||''} maxLength={200} onChange={e=>set('title',e.target.value)}/></Field>
  <Field label="Announcement / description"><textarea value={value.description||''} maxLength={10000} rows={6} onChange={e=>set('description',e.target.value)}/></Field>
  <div className="two-grid">{[['registration_url','Official registration link'],['source_url','Original announcement link']].map(([key,label])=><Field label={label} key={key}><input type="url" placeholder="https://…" value={value[key]||''} onChange={e=>set(key,e.target.value)}/></Field>)}</div>
  {value.source_url&&value.source_url!=='https://'&&<a className="text-button" href={value.source_url} target="_blank" rel="noopener noreferrer">Open source to confirm the details</a>}
  <div className="two-grid">{[['organizer','Organizer'],['location','Location'],['country','Country'],['eligibility','Eligibility rules']].map(([key,label])=><Field label={label} key={key}><input value={value[key]||''} onChange={e=>set(key,e.target.value||null)}/></Field>)}</div>
  <div className="two-grid">{[['registration_deadline','Registration deadline'],['starts_at','Event start'],['ends_at','Event end (optional)']].map(([key,label])=><Field label={label} key={key}><input type="datetime-local" value={localDate(value[key])} onChange={e=>set(key,e.target.value?new Date(e.target.value).toISOString():null)}/></Field>)}</div>
  <p className="help">Dates use your device’s time zone. Leave unknown dates blank; a registration deadline and start date are required to enable team formation.</p>
  <div className="two-grid"><Field label="Attendance format"><select value={value.format} onChange={e=>set('format',e.target.value)}>{['online','offline','hybrid'].map(x=><option key={x}>{x}</option>)}</select></Field>{[['minimum_team_size','Minimum team size'],['maximum_team_size','Maximum team size']].map(([key,label])=><Field key={key} label={label}><input type="number" min={1} max={10} value={value[key]} onChange={e=>set(key,Number(e.target.value))}/></Field>)}</div>
  <h4>Skills required by the event</h4><p className="help">Add confirmed requirements, not guessed skills.</p>
  {skills.map((skill:any,index:number)=><div className="skill-row" key={index}>
   <input aria-label={'Required skill '+(index+1)} placeholder="Skill name" maxLength={80} value={skill.name} onChange={e=>set('requirements',skills.map((s:any,i:number)=>i===index?{...s,name:e.target.value}:s))}/>
   <select aria-label={'Skill category '+(index+1)} value={skill.category||'technical'} onChange={e=>set('requirements',skills.map((s:any,i:number)=>i===index?{...s,category:e.target.value}:s))}><option value="technical">Technical</option><option value="nontechnical">Soft skill</option></select>
   <select aria-label={'Required level '+(index+1)} value={skill.proficiency||''} onChange={e=>set('requirements',skills.map((s:any,i:number)=>i===index?{...s,proficiency:Number(e.target.value)||null}:s))}><option value="">Select level</option><option value={1}>Beginner</option><option value={2}>Intermediate</option><option value={3}>Advanced</option></select>
   <button className="text-button" type="button" onClick={()=>set('requirements',skills.filter((_:any,i:number)=>i!==index))}>Remove</button>
  </div>)}
  <button className="button secondary small" type="button" onClick={()=>set('requirements',[...skills,{name:'',category:'technical',proficiency:null}])}>Add required skill</button>
  <Field label="Review status"><select value={value.verification_status} onChange={e=>set('verification_status',e.target.value)}><option value="pending">Details still need review</option><option value="verified">Confirmed — enable team formation</option><option value="needs_correction">Needs correction</option><option value="rejected">Reject announcement</option></select></Field>
  <label className="check"><input type="checkbox" checked={!!value.registration_closed} onChange={e=>set('registration_closed',e.target.checked)}/>Registration is closed</label>
  <label className="check"><input type="checkbox" checked={!!value.cancelled} onChange={e=>set('cancelled',e.target.checked)}/>Event is cancelled</label>
 </>;
}

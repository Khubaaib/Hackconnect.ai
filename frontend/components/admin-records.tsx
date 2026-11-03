'use client';
import {useEffect,useId,useRef} from 'react';
import {X} from 'lucide-react';
import {date} from '@/lib/api';
import {Empty} from '@/components/ui';

export function Status({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){
 return <span className={'admin-status '+tone}>{children}</span>;
}
export function Skills({skills=[],limit=3}:{skills?:any[];limit?:number}){
 return <div className="admin-skills">{skills.slice(0,limit).map((s:any,i:number)=><span key={s.name||i}>{s.name}</span>)}{skills.length>limit&&<span className="admin-more">+{skills.length-limit}</span>}{!skills.length&&<span className="admin-placeholder">Not provided</span>}</div>;
}
export function RecordDialog({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
 const ref=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{const d=ref.current;d?.showModal();return()=>d?.close()},[]);
 return <dialog ref={ref} className="admin-dialog" aria-labelledby={id} onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget)onClose()}}>
  <div className="admin-dialog-heading"><div><span className="eyebrow">STUDENT RECORD</span><h2 id={id}>{title}</h2></div><button className="icon-button" aria-label="Close student details" onClick={onClose}><X size={18}/></button></div>{children}
 </dialog>;
}
export function StudentDetails({record,imported,busy,onInvite,onHide}:{record:any;imported:boolean;busy:boolean;onInvite:()=>void;onHide:()=>void}){
 const fields=imported?[['Email',record.email],['Roll number',record.roll_number],['Institution',record.institution],['Added',date(record.created_at)]]:[['Institution',record.institution],['Location',[record.city,record.country].filter(Boolean).join(', ')],['Course',record.degree],['Year',record.year_of_study],['Added',date(record.created_at)]];
 return <><div className="admin-detail-status"><Status tone={imported?(record.claimed_by?'green':'amber'):(record.discoverable?'green':'neutral')}>{imported?(record.claimed_by?'Claimed':'Unclaimed'):(record.discoverable?'Discoverable':'Hidden from discovery')}</Status></div>
  <dl className="admin-detail-grid">{fields.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value||'Not provided'}</dd></div>)}</dl>
  {imported?<><h3>Technical skills</h3><Skills skills={(record.skills||[]).filter((s:any)=>s.category!=='nontechnical')} limit={100}/><h3>Other strengths</h3><Skills skills={(record.skills||[]).filter((s:any)=>s.category==='nontechnical')} limit={100}/><p className="help">Imported skills are self-reported. An unspecified proficiency has not been assessed.</p></>:<><h3>Preferred roles</h3><div className="tags">{(record.roles||[]).map((s:string)=><span key={s}>{s}</span>)}</div>{record.bio&&<p>{record.bio}</p>}<p className="help">Profile {record.onboarding_complete?'complete':'in progress'} · Invitations {record.open_to_invitations?'enabled':'disabled'}</p></>}
  <div className="admin-dialog-footer">{imported?!record.claimed_by?<button className="button small" disabled={busy} onClick={onInvite}>Send registration invitation</button>:<p className="help">This record is linked to a registered account.</p>:<button className="button secondary small" disabled={busy||!record.discoverable&&!record.open_to_invitations} onClick={onHide}>Hide from discovery</button>}</div>
 </>;
}
export function StudentTable({rows,imported,onSelect}:{rows:any[];imported:boolean;onSelect:(record:any)=>void}){
 if(!rows.length)return <Empty title="No students match this view"><p>Try another name, skill, or status.</p></Empty>;
 return <div className="admin-table-scroll"><table className="admin-table" aria-label={imported?'Imported student records':'Registered student profiles'}><thead><tr><th>Student</th><th>{imported?'Roll number':'Institution'}</th><th>{imported?'Skills & strengths':'Preferred roles'}</th><th>Status</th><th><span className="admin-sr-only">Actions</span></th></tr></thead><tbody>{rows.map(r=><tr key={r.id}>
  <td><div className="admin-person"><span className="admin-avatar" aria-hidden="true">{(r.display_name||'?').trim().split(/\s+/).map((s:string)=>s[0]).slice(0,2).join('').toUpperCase()}</span><div><button className="admin-name" onClick={()=>onSelect(r)}>{r.display_name||'Unnamed student'}</button>{imported&&r.institution&&<small>{r.institution}</small>}</div></div></td>
  <td><span className={imported?'admin-roll':''}>{(imported?r.roll_number:r.institution)||'—'}</span></td>
  <td>{imported?<Skills skills={r.skills}/>:<div className="admin-skills">{(r.roles||[]).slice(0,2).map((x:string)=><span key={x}>{x}</span>)}{!r.roles?.length&&<span className="admin-placeholder">Not selected</span>}</div>}</td>
  <td><Status tone={imported?(r.claimed_by?'green':'amber'):(r.discoverable?'green':'neutral')}>{imported?(r.claimed_by?'Claimed':'Unclaimed'):(r.discoverable?'Discoverable':'Hidden')}</Status></td>
  <td><button className="text-button" aria-label={'View '+r.display_name} onClick={()=>onSelect(r)}>View details</button></td>
 </tr>)}</tbody></table></div>;
}
const detailText=(v:unknown)=>typeof v==='string'||typeof v==='number'?String(v):'Additional activity recorded';
const words=(s:string)=>s.replaceAll('_',' ').replaceAll('-',' ').replace(/^./,c=>c.toUpperCase());
export function OperationsTable({rows,section,busy,onResolve}:{rows:any[];section:string;busy:boolean;onResolve:(id:string)=>void}){
 if(!rows.length)return <Empty title="Nothing here yet"><p>New activity will appear here when it is recorded.</p></Empty>;
 return <div className="admin-table-scroll"><table className="admin-table" aria-label="Administration activity"><thead><tr><th>{section==='reports'?'Report':section==='imports'?'Import summary':'Activity'}</th><th>Details</th><th>Status</th><th>Date</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><strong>{words(r.name||r.kind||r.action||(section==='imports'?'Student import':section==='reports'?'Student report':'Activity'))}</strong></td><td>{section==='imports'?<span>{r.summary?.successful||0} imported · {r.summary?.duplicates||0} duplicates · {r.summary?.invalid||0} invalid</span>:section==='reports'?<span>{r.reason}</span>:<span>{detailText(r.error||r.details?.message||r.details?.summary||(section==='jobs'?'Scheduled platform check':'Recorded by the platform'))}</span>}</td><td><Status tone={['completed','resolved'].includes(r.status)?'green':r.status==='failed'?'red':'neutral'}>{words(r.status||'Recorded')}</Status>{section==='reports'&&r.status!=='resolved'&&<button className="text-button" disabled={busy} onClick={()=>onResolve(r.id)}>Resolve report</button>}</td><td>{date(r.created_at||r.started_at||r.updated_at)}</td></tr>)}</tbody></table></div>;
}

'use client';
import {useState} from 'react';
import {Upload} from 'lucide-react';
import {api} from '@/lib/api';
import {Field,ErrorBox} from '@/components/ui';
import {Skills} from '@/components/admin-records';
const columns=[['display_name','Student name'],['email','Email address'],['institution','Institution'],['skills','Technical skills'],['nontechnical','Other strengths']];
export default function AdminImport({onComplete}:{onComplete:()=>void}){
 const[file,setFile]=useState<File|null>(null),[mapping,setMapping]=useState<Record<string,string>>({}),[available,setAvailable]=useState<string[]>([]),[preview,setPreview]=useState<any>(null),[authorized,setAuthorized]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function upload(action:'preview'|'commit'){
  if(!file)return;setBusy(true);setError('');setNotice('');
  try{const f=new FormData();f.append('file',file);f.append('mapping',JSON.stringify(mapping));f.append('authorized',String(authorized));const r=await api('/admin/import/'+action,{method:'POST',body:f});
   if(action==='preview'){setPreview(r);setMapping(r.mapping||{});setAvailable(r.columns||[])}
   else{setNotice(`${r.successful||0} students imported · ${r.duplicates||0} duplicates skipped · ${r.invalid||0} invalid rows.${r.reimport?' This file was already processed.':''}`);setPreview(null);onComplete()}
  }catch(e){const message=(e as Error).message;try{const detail=JSON.parse(message);if(detail.columns){setAvailable(detail.columns);setMapping(Object.fromEntries(Object.entries(detail.inferred_mapping||{}).filter(([,v])=>typeof v==='string')) as Record<string,string>);setError('Choose the student name and email columns below, then preview again.')}else setError('The file could not be processed. Check its column headings.')}catch{setError(message)}}finally{setBusy(false)}
 }
 return <section className="admin-form-panel"><div className="admin-section-heading"><div><h2>Upload student records</h2><p>Preview a CSV or Excel spreadsheet before adding it to your directory.</p></div><Upload size={22}/></div><ErrorBox error={error}/>{notice&&<div className="success" role="status">{notice}</div>}
  <Field label="CSV or Excel file"><input type="file" accept=".csv,.xlsx" onChange={e=>{setFile(e.target.files?.[0]||null);setPreview(null);setAvailable([]);setMapping({});setError('')}}/></Field><p className="help">Up to 5 MB. Include column headings for each field.</p>
  {available.length>0&&<details className="admin-disclosure"><summary>Check column mapping</summary><div className="two-grid">{columns.map(([key,label])=><Field key={key} label={label+' column'}><select value={mapping[key]||''} onChange={e=>{setPreview(null);setMapping(m=>{const next={...m};if(e.target.value)next[key]=e.target.value;else delete next[key];return next})}}><option value="">Not included</option>{available.map(c=><option key={c}>{c}</option>)}</select></Field>)}</div></details>}
  <label className="check"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/>I have permission to import these records and show names, institutions, and skills in the signed-in directory. Contact details remain administrator-only.</label>
  <div className="row"><button className="button secondary small" disabled={busy||!file} onClick={()=>upload('preview')}>{busy?'Processing…':'Preview rows'}</button><button className="button small" disabled={busy||!preview||!authorized} onClick={()=>upload('commit')}>Import valid students</button></div>
  {preview&&<div className="admin-preview"><h3>Ready to import</h3><div className="admin-preview-counts"><span><strong>{preview.valid.length}</strong>Valid students</span><span><strong>{preview.invalid.length}</strong>Invalid rows</span><span><strong>{preview.duplicates.length}</strong>Duplicates</span></div><p className="help">Preview of the first five valid students. No records are added until you choose Import valid students.</p><div className="admin-table-scroll"><table className="admin-table" aria-label="Student import preview"><thead><tr><th>Student</th><th>Institution</th><th>Skills</th></tr></thead><tbody>{preview.valid.slice(0,5).map((r:any,i:number)=><tr key={i}><td>{r.display_name}</td><td>{r.institution||'—'}</td><td><Skills skills={r.skills}/></td></tr>)}</tbody></table></div>{[...preview.invalid,...preview.duplicates].length>0&&<details className="admin-disclosure"><summary>Review skipped rows</summary>{[...preview.invalid,...preview.duplicates].map((r:any,i:number)=><p key={i} className="small-text">Row {r.row}: {r.reason}</p>)}</details>}</div>}
 </section>;
}

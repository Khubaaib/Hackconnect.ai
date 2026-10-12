'use client';
import {useEffect,useState} from 'react';
import {api,date} from '@/lib/api';
import {ErrorBox,Loading,Empty} from '@/components/ui';

type Announcement={message_id:number;title:string;body:string;source_url:string;posted_at:string;edited_at:string|null;has_media:boolean};
type Feed={items:Announcement[];total:number;configured:boolean;channel_title:string;last_synced_at:string|null;sync_status:string};

export default function TelegramFeed(){
 const [feed,setFeed]=useState<Feed|null>(null),[query,setQuery]=useState(''),[offset,setOffset]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0);
 useEffect(()=>{
  let active=true;
  async function load(){
   try{
    const data=await api<Feed>('/telegram/announcements?'+new URLSearchParams({q:query,offset:String(offset)}));
    if(active){setFeed(data);setError('');}
   }catch(e){if(active)setError((e as Error).message)}finally{if(active)setLoading(false)}
  }
  setLoading(true);
  const initial=setTimeout(load,250),interval=setInterval(load,60000);
  return()=>{active=false;clearTimeout(initial);clearInterval(interval)};
 },[query,offset,refresh]);
 return <section aria-label="Telegram hackathon announcements">
  <div className="row space-between"><div><span className="eyebrow">FROM TELEGRAM</span><h2>{feed?.channel_title||'College hackathon announcements'}</h2><p>Announcements from your selected college channel, with their original wording and source links.</p></div></div>
  <div className="filters"><input aria-label="Search channel announcements" placeholder="Search channel announcements…" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0)}}/><button className="button secondary small" onClick={()=>setRefresh(x=>x+1)}>Refresh</button></div>
  <ErrorBox error={error}/>
  {feed?.last_synced_at&&<p className="small-text">Last updated: {date(feed.last_synced_at)}. Announcement dates below are posting dates; confirm event deadlines in the original post.</p>}
  {feed?.sync_status&&['sync_failed','authorization_required','channel_access_required'].includes(feed.sync_status)&&<div className="notice">Channel updates are temporarily unavailable. Previously saved announcements remain below.</div>}
  {loading&&!feed?<Loading/>:feed?.items.length?<div className="cards">{feed.items.map(post=><article className="card" key={post.message_id}>
   <div className="card-top"><span className="tag">CHANNEL ANNOUNCEMENT</span>{post.edited_at&&<span className="small-text">Edited</span>}</div>
   <h3 style={{overflowWrap:'anywhere'}}>{post.title}</h3><p className="small-text">Posted: {date(post.posted_at)}</p>
   {post.body&&<p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{post.body.length>1800?post.body.slice(0,1800)+'…':post.body}</p>}
   {post.has_media&&<p className="small-text">This post includes an attachment. Open Telegram to view the poster or file.</p>}
   <div className="card-actions"><a className="button small" href={post.source_url} target="_blank" rel="noopener noreferrer">Open original post</a></div>
  </article>)}</div>:!error&&<Empty title={feed?.configured?'No announcements match this view':'Your channel connection is being set up'}><p>{feed?.configured?'New hackathon and project-competition posts will appear after the next channel update.':'Your administrator is completing the Telegram connection. You do not need to post announcements yourself.'}</p></Empty>}
  {feed&&feed.total>0&&<div className="pagination"><button className="button secondary small" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-20))}>Previous</button><span className="small-text">{feed.total} announcements</span><button className="button secondary small" disabled={offset+20>=feed.total||loading} onClick={()=>setOffset(offset+20)}>Next</button></div>}
 </section>;
}

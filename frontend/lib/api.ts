import {createClient,SupabaseClient} from '@supabase/supabase-js';
let client:SupabaseClient|undefined;
export function supabase(){
 const url=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
 if(!url||!key)throw new Error('Authentication is not configured. Set the Supabase environment variables.');
 return client??=(createClient(url,key));
}
export async function api<T=any>(path:string,init:RequestInit={}):Promise<T>{
 const {data:{session}}=await supabase().auth.getSession();
 if(!session)throw new Error('Sign in to continue.');
 const headers=new Headers(init.headers);headers.set('Authorization','Bearer '+session.access_token);
 if(init.body && !(init.body instanceof FormData))headers.set('Content-Type','application/json');
 let response:Response;
 try{response=await fetch((process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000')+'/api/v1'+path,{...init,headers,cache:'no-store'});}catch{throw new Error('Cannot reach HackConnect API. Check the backend connection and try again.');}
 const data=await response.json().catch(()=>({detail:'Unexpected server response'}));
 if(!response.ok){const d=data.detail;throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map((x:any)=>x.msg).join('; '):JSON.stringify(d));}
 return data;
}
export const send=(method:string,body?:unknown):RequestInit=>({method,...(body===undefined?{}:{body:JSON.stringify(body)})});
export function date(value:string|undefined|null){return value?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'Not confirmed';}

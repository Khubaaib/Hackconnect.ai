import {test,expect} from '@playwright/test';
test.skip(!!process.env.TEST_BASE_URL,'Synthetic admin tests use the local build.');
const students=Array.from({length:65},(_,i)=>({id:'private-id-'+i,display_name:'Synthetic Student '+String(i).padStart(2,'0'),email:'student'+i+'@example.com',roll_number:i?'R'+i:null,institution:i?'Fixture College':'',skills:[{name:'Python',category:'technical',proficiency:null},{name:'React',category:'technical',proficiency:null},{name:'SQL',category:'technical',proficiency:null},{name:'Presentation',category:'nontechnical',proficiency:null}],claimed_by:i%3===0?'registered-id':null,import_job_id:'internal-import',created_at:'2026-11-04T00:00:00Z'}));
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('sb-fixture-auth-token',JSON.stringify({access_token:'fixture.access.token',refresh_token:'fixture-only',token_type:'bearer',expires_at:Math.floor(Date.now()/1000)+3600,user:{id:'00000000-0000-0000-0000-000000000001',email:'fixture@example.com'}})));
 await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'fixture-admin',display_name:'Fixture admin',onboarding_complete:true,is_admin:true}}));
 await page.route('**/api/v1/admin/overview',route=>route.fulfill({json:{user_profiles:8,imported_students:65,hackathons:2,teams:3,abuse_reports:0,integrations:{grok_configured:true,telegram_configured:true},ai_usage:{requests:5,input_tokens:120,output_tokens:80}}}));
 await page.route('**/api/v1/admin/imported-students',route=>route.fulfill({json:students}));
 await page.route('**/api/v1/admin/students',route=>route.fulfill({json:[{id:'registered',display_name:'Registered Builder',institution:'Fixture College',roles:['Backend Developer'],discoverable:true,onboarding_complete:true,open_to_invitations:true,created_at:'2026-11-04T00:00:00Z'}]}));
});
test('readable directory supports all records, search, filtering and private detail dialogs',async({page})=>{
 let writes=0;page.on('request',r=>{if(r.url().includes('/api/v1/admin/')&&['POST','PUT','PATCH','DELETE'].includes(r.method()))writes++});
 await page.goto('/admin');await expect(page.getByRole('heading',{name:'Workspace overview',exact:true})).toBeVisible();
 await expect(page.locator('pre')).toHaveCount(0);
 await page.getByRole('button',{name:'Student records',exact:true}).click();
 const table=page.getByRole('table',{name:'Imported student records'});
 await expect(table.locator('tbody tr')).toHaveCount(10);
 await expect(page.getByText('1–10 of 65 students',{exact:true})).toBeVisible();
 await expect(page.getByText('student0@example.com',{exact:true})).toHaveCount(0);
 await expect(page.getByText('internal-import',{exact:true})).toHaveCount(0);
 await expect(page.locator('pre')).toHaveCount(0);
 await page.getByRole('button',{name:'Next page',exact:true}).click();await expect(page.getByText('11–20 of 65 students',{exact:true})).toBeVisible();
 await page.getByLabel('Rows per page').selectOption('50');await page.getByRole('button',{name:'Next page',exact:true}).click();
 await expect(page.getByText('51–65 of 65 students',{exact:true})).toBeVisible();await expect(table.locator('tbody tr')).toHaveCount(15);
 await page.getByLabel('Search student records',{exact:true}).fill('Synthetic Student 01');await expect(table.locator('tbody tr')).toHaveCount(1);
 await page.getByRole('button',{name:'View Synthetic Student 01',exact:true}).click();
 const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();await expect(dialog.getByText('student1@example.com',{exact:true})).toBeVisible();
 await expect(dialog.getByText('Presentation',{exact:true})).toBeVisible();await expect(dialog.getByText('private-id-1',{exact:true})).toHaveCount(0);
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
 await page.getByLabel('Search student records',{exact:true}).fill('');await page.getByLabel('Filter student status').selectOption('claimed');
 await expect(page.getByText('1–22 of 22 students',{exact:true})).toBeVisible();
 await page.getByLabel('Search student records',{exact:true}).fill('NoSuchStudent');await expect(page.getByRole('heading',{name:'No students match this view'})).toBeVisible();
 expect(writes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});
test('registered profiles have a separate table',async({page})=>{
 await page.goto('/admin?tab=imported-students');await expect(page.getByRole('table',{name:'Imported student records'})).toBeVisible();
 await page.getByRole('button',{name:'Registered students',exact:true}).click();
 await expect(page.getByRole('table',{name:'Registered student profiles'})).toBeVisible();await expect(page.getByRole('button',{name:'Registered Builder',exact:true})).toBeVisible();
 await expect(page.getByText('Synthetic Student 00',{exact:true})).toHaveCount(0);await expect(page.locator('pre')).toHaveCount(0);
});
test('spreadsheet preview is readable and import requires authorization',async({page})=>{
 await page.route('**/api/v1/admin/import/preview',route=>route.fulfill({json:{columns:['Name','Email','Skills'],mapping:{display_name:'Name',email:'Email',skills:'Skills'},valid:[students[1]],invalid:[{row:3,reason:'Invalid email'}],duplicates:[],skipped:0,digest:'internal-digest'}}));
 await page.goto('/admin?tab=imported-students');await page.getByRole('button',{name:'Upload students',exact:true}).click();
 await page.getByLabel('CSV or Excel file').setInputFiles({name:'synthetic.csv',mimeType:'text/csv',buffer:Buffer.from('Name,Email,Skills\nSynthetic Student 01,student1@example.com,Python\n')});
 await expect(page.getByRole('button',{name:'Import valid students'})).toBeDisabled();await page.getByRole('button',{name:'Preview rows',exact:true}).click();
 await expect(page.getByRole('table',{name:'Student import preview'})).toBeVisible();await expect(page.getByText('internal-digest',{exact:true})).toHaveCount(0);await expect(page.locator('pre')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Import valid students'})).toBeDisabled();await page.getByRole('checkbox').check();await expect(page.getByRole('button',{name:'Import valid students'})).toBeEnabled();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});
test('non administrators cannot load the workspace',async({page})=>{
 await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'fixture-student',display_name:'Student',onboarding_complete:true,is_admin:false}}));
 await page.goto('/admin');await expect(page.getByRole('alert').filter({hasText:'Administrator access required.'})).toHaveText('Administrator access required.');await expect(page.getByRole('navigation',{name:'Admin sections'})).toHaveCount(0);
});

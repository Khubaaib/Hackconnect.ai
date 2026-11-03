import {test,expect} from '@playwright/test';
test.skip(!!process.env.TEST_BASE_URL,'Synthetic search tests use only the local build.');
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('sb-fixture-auth-token',JSON.stringify({access_token:'fixture.access.token',refresh_token:'fixture-only',token_type:'bearer',expires_at:Math.floor(Date.now()/1000)+3600,user:{id:'00000000-0000-0000-0000-000000000001',email:'fixture@example.com'}})));
 await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'00000000-0000-0000-0000-000000000001',display_name:'Test builder',onboarding_complete:true,is_admin:false}}));
});
test('searches real profile results and refreshes newly discoverable students',async({page})=>{
 let fresh=false;
 await page.route('**/api/v1/teammates/search',async route=>{
  const body=route.request().postDataJSON();
  const items=fresh||body.query?[{profile:{id:'candidate',display_name:'Synthetic React Builder',bio:'Builds interfaces',roles:['Frontend Developer'],skills:[{name:'React',proficiency:2}]},score:100,explanation:'Profile evidence: react',unknown_proficiency:[]}]:[];
  await route.fulfill({json:{items,total:items.length,searchable_profiles:items.length,mode:body.query?'ai':'profile',notice:'',criteria:{},bounded:false,score_label:'Profile relevance'}});
 });
 await page.goto('/dashboard?tab=teammates');
 await expect(page.getByRole('heading',{name:'No discoverable teammates yet'})).toBeVisible();
 fresh=true;
 await page.getByRole('button',{name:'Refresh profiles'}).click();
 await expect(page.getByRole('heading',{name:'Synthetic React Builder'})).toBeVisible();
 await page.getByLabel('Search teammates',{exact:true}).fill('Find React frontend developer');
 await page.getByRole('button',{name:'Find teammates',exact:true}).click();
 await expect(page.getByRole('status').filter({hasText:'AI-assisted search'})).toBeVisible();
 await expect(page.getByRole('link',{name:'Choose a hackathon'})).toHaveAttribute('href','/dashboard?tab=opportunities');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});
test('shows fallback notice when AI is unavailable',async({page})=>{
 await page.route('**/api/v1/teammates/search',route=>route.fulfill({json:{items:[],total:0,searchable_profiles:4,mode:'keyword',notice:'AI search is temporarily unavailable. Showing matches from profile keywords instead.',criteria:{},bounded:false,score_label:'Profile relevance'}}));
 await page.goto('/dashboard?tab=teammates');
 await expect(page.getByText('AI search is temporarily unavailable.',{exact:false})).toBeVisible();
 await expect(page.getByRole('heading',{name:'No profiles match this search'})).toBeVisible();
});

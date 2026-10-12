import {test,expect} from '@playwright/test';
test.skip(!!process.env.TEST_BASE_URL,'Synthetic feed tests run only against the local CI build.');
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('sb-fixture-auth-token',JSON.stringify({access_token:'fixture.access.token',refresh_token:'fixture-only',token_type:'bearer',expires_at:Math.floor(Date.now()/1000)+3600,user:{id:'00000000-0000-0000-0000-000000000001',email:'fixture@example.com'}})));
 await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'00000000-0000-0000-0000-000000000001',display_name:'Test builder',onboarding_complete:true,is_admin:false}}));
});
test('discovery shows channel posts and opens original source without treating it as a verified event',async({page})=>{
 await page.route('**/api/v1/telegram/announcements?*',route=>route.fulfill({json:{items:[{message_id:12,title:'College Hackathon',body:'Original announcement. Deadline not supplied.',source_url:'https://t.me/c/1111222333/12',posted_at:'2026-10-12T12:00:00Z',edited_at:null,has_media:true}],total:1,configured:true,channel_title:'Test college channel',last_synced_at:'2026-10-12T12:01:00Z',sync_status:'synced'}}));
 await page.goto('/dashboard');
 await expect(page.getByRole('heading',{name:'Test college channel'})).toBeVisible();
 await expect(page.getByText('Original announcement. Deadline not supplied.')).toBeVisible();
 await expect(page.getByRole('link',{name:'Open original post'})).toHaveAttribute('href','https://t.me/c/1111222333/12');
 await expect(page.getByText('This post includes an attachment.',{exact:false})).toBeVisible();
 await expect(page.getByText(/% fit/)).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});
test('a missing session configuration gives a clear setup state',async({page})=>{
 await page.route('**/api/v1/telegram/announcements?*',route=>route.fulfill({json:{items:[],total:0,configured:false,channel_title:'College channel',last_synced_at:null,sync_status:'not_configured'}}));
 await page.goto('/dashboard');
 await expect(page.getByRole('heading',{name:'Your channel connection is being set up'})).toBeVisible();
});

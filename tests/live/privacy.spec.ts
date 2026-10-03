import {test,expect} from '@playwright/test';
import policy from '../../backend/foodsave/static/privacy-policy.json';
test('App displays the full approved policy without claiming activation',async({page})=>{
  await page.goto('/privacy/');
  for(const section of policy.sections){
    await expect(page.getByRole('heading',{name:section.title,exact:true})).toBeVisible();
    for(const paragraph of section.paragraphs){
      await expect(page.getByText(paragraph,{exact:true})).toBeVisible();
    }
  }
  await expect(page.getByText(/註冊可用性以App的即時後端檢查為準/)).toBeVisible();
});

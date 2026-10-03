import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests/live',use:{baseURL:'http://127.0.0.1:4174',viewport:{width:390,height:844},launchOptions:{executablePath:'/usr/bin/chromium',args:['--no-sandbox']}},webServer:{command:'python3 -m http.server 4174 --directory out',url:'http://127.0.0.1:4174',reuseExistingServer:false}});

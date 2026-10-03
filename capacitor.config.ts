import type { CapacitorConfig } from '@capacitor/cli';
const config: CapacitorConfig = { appId: process.env.FOODSAVE_APPLICATION_ID || 'tw.foodsave.demo', appName: '食在可惜', webDir: 'out', android: { adjustMarginsForEdgeToEdge: 'auto', backgroundColor: '#f5f8f3' } };
export default config;

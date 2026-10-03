import policy from '../backend/foodsave/static/privacy-policy.json';
export const operatorName=process.env.NEXT_PUBLIC_OPERATOR_NAME||'HUANG';
export const privacyContact=process.env.NEXT_PUBLIC_PRIVACY_CONTACT||'413637629@o365.tku.edu.tw';
export const retentionSummary=process.env.NEXT_PUBLIC_RETENTION_SUMMARY||policy.summary;
// Approved policy direction is not proof that backup/erasure operations are ready.
export const privacyReady=Boolean(operatorName&&privacyContact&&retentionSummary&&process.env.NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE==='true');

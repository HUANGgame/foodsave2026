export const operatorName=process.env.NEXT_PUBLIC_OPERATOR_NAME||'';
export const privacyContact=process.env.NEXT_PUBLIC_PRIVACY_CONTACT||'';
export const retentionSummary=process.env.NEXT_PUBLIC_RETENTION_SUMMARY||'';
export const privacyReady=Boolean(operatorName&&privacyContact&&retentionSummary);

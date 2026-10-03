export const operatorName=process.env.NEXT_PUBLIC_OPERATOR_NAME||'HUANG';
export const privacyContact=process.env.NEXT_PUBLIC_PRIVACY_CONTACT||'413637629@o365.tku.edu.tw';
export const retentionSummary=process.env.NEXT_PUBLIC_RETENTION_SUMMARY||'刪帳申請受理後立即停用登入，30天內清除可識別個資。必須保留的業務紀錄，須另行明列原因與期限，不默默永久保存。';
// Approved policy direction is not proof that backup/erasure operations are ready.
export const privacyReady=Boolean(operatorName&&privacyContact&&retentionSummary&&process.env.NEXT_PUBLIC_PRIVACY_POLICY_COMPLETE==='true');

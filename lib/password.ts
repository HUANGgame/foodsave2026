// Match Python/Pydantic Unicode code-point lengths; do not normalize secrets.
export function passwordLength(value:string){return Array.from(value).length;}
export function passwordLengthError(value:string,min:number){const n=passwordLength(value);return n<min||n>128?`請輸入${min}至128字元的密碼。`:'';}

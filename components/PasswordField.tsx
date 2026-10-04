'use client';
import {useState} from 'react';
import {passwordLengthError} from '../lib/password';
export default function PasswordField({name,label,min=15,newPassword=false}:{name:string;label:string;min?:number;newPassword?:boolean}){
 const [visible,setVisible]=useState(false);
 function validate(input:HTMLInputElement){input.setCustomValidity(passwordLengthError(input.value,min));}
 return <div className="password-field"><label>{label}<input name={name} type={visible?'text':'password'} required autoComplete={newPassword?'new-password':'current-password'} autoCapitalize="none" spellCheck={false} onInput={e=>validate(e.currentTarget)} onBlur={e=>validate(e.currentTarget)}/></label><button type="button" className="password-toggle" aria-label={visible?'隱藏輸入內容':'顯示輸入內容'} aria-pressed={visible} onClick={()=>setVisible(v=>!v)}>{visible?'隱藏':'顯示'}</button></div>;
}

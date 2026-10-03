/** Original FoodSave mascot. Decorative; feedback is always provided in text. */
export default function Frog({harvest=false}:{harvest?:boolean}){
 return <svg className={`foodsave-frog${harvest?' frog-harvest':''}`} viewBox="0 0 128 112" aria-hidden="true" focusable="false">
  <ellipse cx="65" cy="103" rx="39" ry="5" fill="#174f3b" opacity=".1"/>
  <g className="frog-body" stroke="#225f48" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
   <ellipse cx="64" cy="80" rx="32" ry="25" fill="#79cfa1"/>
   <ellipse cx="64" cy="84" rx="19" ry="17" fill="#f7f7dc" stroke="none"/>
   <path d="M34 82Q17 86 25 98Q38 103 44 94M94 82Q111 86 103 98Q90 103 84 94" fill="#79cfa1"/>
   <path d="M29 49C21 30 34 15 47 22Q63 14 80 22C96 12 108 29 99 49Q110 77 65 77Q20 78 29 49Z" fill="#89dca6"/>
   <ellipse cx="43" cy="36" rx="9" ry="11" fill="#fffce9" stroke="none"/>
   <ellipse cx="86" cy="36" rx="9" ry="11" fill="#fffce9" stroke="none"/>
   <path d="M44 35V40M85 35V40" strokeWidth="4"/>
   <ellipse cx="37" cy="54" rx="7" ry="4" fill="#efb8a4" stroke="none"/>
   <ellipse cx="92" cy="54" rx="7" ry="4" fill="#efb8a4" stroke="none"/>
   <path d="M49 56Q64 70 80 56" fill="none"/>
   <path d="M63 81Q74 71 82 78Q81 91 65 91Z" fill="#37936a" stroke="none"/>
   <path d="M65 89L76 81" stroke="#fffce9" strokeWidth="1.5"/>
  </g>
  {harvest&&<g className="frog-leaf"><path d="M13 12Q32 6 33 24Q14 29 13 12" fill="#3c9f6d"/><path d="M17 16L32 29" stroke="#225f48" strokeWidth="2"/></g>}
 </svg>;
}

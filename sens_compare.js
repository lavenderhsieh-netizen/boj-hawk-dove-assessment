/* Shared renderer: official vs own sensitivity comparison. Usage: renderSensCompare('containerId','japan') — expects ./sensitivity_studies.json.
   Data schema + how to add a country: see inflation-sensitivity-studies/README.md */
(function(){
const COL={'Central bank':'#d9a441','Other official':'#3eb87a','Private / broker':'#8a97b3','Ours':'#6fa8ff'};
const v=(n,fb)=>`var(${n},${fb})`;
const fmt=x=>(x>=0?'+':'')+x.toFixed(2);
function effText(r){ if(r.path) return r.path.map(x=>fmt(x)).join(' / ')+(r.approx?' ≈':''); if(r.low===r.high) return fmt(r.low)+(r.approx?' ≈':''); return fmt(r.low)+' to '+fmt(r.high)+(r.approx?' ≈':''); }
window.renderSensCompare=async function(id,country){
  const el=document.getElementById(id); if(!el) return;
  try{
    const D=await (await fetch('./sensitivity_studies.json?_='+Date.now())).json(); const C=D.countries[country];
    const rows=C.studies.concat(C.ours); let html='';
    ['oil','fx','admin','combined'].forEach(sh=>{
      const R=rows.filter(r=>r.shock===sh); if(!R.length) return;
      const order={'Central bank':0,'Other official':1,'Private / broker':2,'Ours':3};
      R.sort((a,b)=>(a.measure>b.measure?-1:a.measure<b.measure?1:0)||order[a.kind]-order[b.kind]);
      const max=Math.max(...R.map(r=>r.high),0.1)*1.1;
      html+=`<h3 style="font-size:.9rem;margin:1rem 0 .3rem;color:${v('--strong','#e8f0ff')}">${C.shock_labels[sh]}${(sh==='combined'||sh==='admin')?'':' — effect on CPI, pp'}</h3>
      <div style="overflow-x:auto"><table style="width:100%;font-size:.76rem;border-collapse:collapse"><thead><tr><th style="text-align:left">Source</th><th>Measure</th><th>Horizon</th><th>Effect</th><th style="width:150px">Range</th></tr></thead><tbody>`+
      R.map(r=>{const c=COL[r.kind]||'#888', l=Math.max(0,r.low)/max*100, w=Math.max(1.2,(r.high-Math.max(0,r.low))/max*100);
        const src=r.url?`<a href="${r.url}" target="_blank" style="color:inherit;text-decoration:underline dotted">${r.source}</a>`:r.source;
        return `<tr style="border-top:1px solid ${v('--border',v('--line','#1e2d45'))}"><td style="padding:.35rem .4rem .1rem 0"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${c};margin-right:6px"></span><b style="color:${c}">${r.kind}</b> · ${src} ${r.date?`<span style="color:${v('--muted','#5a7399')}">(${r.date})</span>`:''}</td><td style="text-align:center">${C.measure_labels[r.measure]||r.measure}</td><td style="color:${v('--muted','#5a7399')}">${r.horizon||''}</td><td style="text-align:center;font-weight:700;white-space:nowrap">${effText(r)}${r.unit?' '+r.unit:''}</td><td><div style="position:relative;height:10px;background:rgba(120,140,180,.12);border-radius:3px"><div style="position:absolute;left:${l}%;width:${w}%;height:10px;background:${c};border-radius:3px"></div></div></td></tr>
        <tr><td colspan="5" style="padding:0 0 .35rem 14px;color:${v('--muted','#5a7399')};font-size:.7rem">${r.note||''}</td></tr>`}).join('')+`</tbody></table></div>`;
    });
    html+=`<h3 style="font-size:.9rem;margin:1rem 0 .3rem;color:${v('--strong','#e8f0ff')}">Other official findings (qualitative / not comparable per +10%)</h3><ul style="font-size:.76rem;margin:0;padding-left:1.1rem;line-height:1.5">`+C.qualitative.map(q=>`<li>${q}</li>`).join('')+`</ul>`;
    html+=`<p style="font-size:.7rem;color:${v('--muted','#5a7399')};margin:.7rem 0 0">Scale note: bars share a scale within each block. “≈” = read off a published chart or pro-rated from a different shock size (linear scaling is an assumption). Paths show successive horizons; single numbers are the stated figure. Effects are on the CPI <i>level</i> relative to baseline unless “pt yoy” is shown. Compiled Oct 2026 from the linked primary documents; secondary citations are labelled.</p>`;
    el.innerHTML=html;
  }catch(e){ el.textContent='Sensitivity comparison unavailable'; console.error('sens_compare',e); }
};
})();

// ── theme toggle
(function(){
  const html=document.documentElement;
  const btn=document.querySelector('[data-theme-toggle]');
  let theme=localStorage.getItem('sk_theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
  html.setAttribute('data-theme',theme);
  if(btn) btn.addEventListener('click',()=>{
    theme=theme==='dark'?'light':'dark';
    html.setAttribute('data-theme',theme);
    localStorage.setItem('sk_theme',theme);
  });
})();

// ── helpers
const getBase=()=>document.getElementById('base-url').value.replace(/\/+$/,'');
function scoreClass(s){return s>=80?'strong':s>=50?'partial':'fail';}

// ── health check
async function checkHealth(){
  const badge=document.getElementById('health-badge');
  badge.className='badge badge--checking'; badge.textContent='checking...';
  try{
    const res=await fetch(getBase()+'/api/v1/health');
    if(res.ok){
      const data=await res.json();
      badge.className='badge badge--ok';
      badge.textContent='\u25cf API online v'+(data.version||'?');
    } else throw new Error();
  } catch{
    badge.className='badge badge--error';
    badge.textContent='\u25cf API offline';
  }
}
checkHealth();
document.getElementById('base-url').addEventListener('change',checkHealth);

// ── file input
const fileInput=document.getElementById('file-input');
const dropZone=document.getElementById('drop-zone');
const fileNameEl=document.getElementById('file-name');
const submitBtn=document.getElementById('submit-btn');
let selectedFile=null;

function setFile(f){
  if(!f) return;
  selectedFile=f;
  fileNameEl.textContent=f.name;
  submitBtn.disabled=false;
}
fileInput.addEventListener('change',()=>setFile(fileInput.files[0]));
dropZone.addEventListener('click',()=>fileInput.click());
dropZone.addEventListener('dragover',e=>{e.preventDefault();dropZone.classList.add('drag-over');});
dropZone.addEventListener('dragleave',()=>dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop',e=>{
  e.preventDefault(); dropZone.classList.remove('drag-over'); setFile(e.dataTransfer.files[0]);
});

// ── status
function setStatus(msg,type){
  const bar=document.getElementById('status-bar');
  bar.textContent=msg; bar.className='status-bar '+type;
}
function hideStatus(){document.getElementById('status-bar').className='status-bar hidden';}

// ── submit
let lastResponse=null, allRows=[];

submitBtn.addEventListener('click',async()=>{
  if(!selectedFile) return;
  const topN=parseInt(document.getElementById('top-n').value)||3;
  submitBtn.disabled=true; hideStatus();
  document.getElementById('summary-section').classList.add('hidden');
  document.getElementById('results-section').classList.add('hidden');
  setStatus('Uploading and parsing\u2026 this may take a few seconds.','loading');
  const form=new FormData();
  form.append('file',selectedFile);
  try{
    const res=await fetch(`${getBase()}/api/v1/parse/match?top_n=${topN}`,{method:'POST',body:form});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail||'Server error '+res.status);
    lastResponse=data;
    setStatus(`Done! ${data.summary.total_items} items parsed and matched.`,'success');
    renderSummary(data.summary);
    renderResults(data.tables);
  } catch(err){
    setStatus('Error: '+err.message,'error');
  } finally{
    submitBtn.disabled=false;
  }
});

// ── summary
function renderSummary(s){
  document.getElementById('summary-grid').innerHTML=`
    <div class="summary-tile tile--total">
      <div class="value">${s.total_items}</div><div class="label">Total Items</div></div>
    <div class="summary-tile tile--strong">
      <div class="value">${s.matched_above_80}</div><div class="label">\u2265 80% Match</div></div>
    <div class="summary-tile tile--partial">
      <div class="value">${s.matched_above_50}</div><div class="label">50\u201379% Match</div></div>
    <div class="summary-tile tile--fail">
      <div class="value">${s.unmatched}</div><div class="label">Unmatched</div></div>`;
  document.getElementById('summary-section').classList.remove('hidden');
}

// ── results
function renderResults(tables){
  allRows=[];
  for(const tableData of Object.values(tables)) allRows.push(...tableData.rows);
  renderRows(allRows);
  document.getElementById('results-section').classList.remove('hidden');
}

function renderRows(rows){
  const container=document.getElementById('results-container');
  container.innerHTML='';
  if(!rows.length){
    container.innerHTML='<p style="color:var(--text-muted);font-size:13px;padding:12px 0">No items match the current filter.</p>';
    return;
  }
  rows.forEach(row=>{
    const best=row.matches&&row.matches.length?row.matches[0].score_pct:0;
    const cls=scoreClass(best);
    const metaChips=[
      row.unit_of_measurement&&`<span class="meta-chip">${row.unit_of_measurement}</span>`,
      row.category&&`<span class="meta-chip">${row.category}</span>`,
      row.skrt_code&&`<span class="meta-chip">${row.skrt_code}</span>`,
      row.remarks&&`<span class="meta-chip">\uD83D\uDCDD ${row.remarks}</span>`,
    ].filter(Boolean).join('');
    const matchRows=(row.matches||[]).map((m,i)=>{
      const mc=scoreClass(m.score_pct);
      return `<tr>
        <td><span class="rank-badge ${i===0?'rank-1':''}}">${m.rank}</span></td>
        <td>${m.product_name}</td>
        <td>${m.category||'\u2014'}</td>
        <td>${m.brand||'\u2014'}</td>
        <td>${m.unit||'\u2014'}</td>
        <td>
          <div class="score-bar-wrap">
            <div class="score-bar"><div class="score-bar-fill fill--${mc}" style="width:${m.score_pct}%"></div></div>
            <span class="score-val score--${mc}">${m.score_pct}%</span>
          </div>
        </td>
      </tr>`;
    }).join('');
    const div=document.createElement('div');
    div.className='item-row';
    div.innerHTML=`
      <div class="item-header" onclick="toggleRow(this)">
        <span class="item-num">${row.sr_no||'\u2014'}</span>
        <span class="item-name">${row.items||row.description||'\u2014'}</span>
        <span class="item-qty">${row.quantity!=null?row.quantity+' '+(row.unit_of_measurement||''):''}</span>
        <span class="item-score score--${cls}">${best.toFixed(1)}%</span>
        <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </div>
      ${metaChips?`<div class="item-meta sk-collapsible" style="display:none">${metaChips}</div>`:''}
      <div class="matches-wrap sk-collapsible" style="display:none">
        <table class="matches-table">
          <thead><tr><th>#</th><th>Product Name</th><th>Category</th><th>Brand</th><th>Unit</th><th>Score</th></tr></thead>
          <tbody>${matchRows}</tbody>
        </table>
      </div>`;
    container.appendChild(div);
  });
}

function toggleRow(header){
  const row=header.parentElement;
  const open=row.classList.toggle('open');
  row.querySelectorAll('.sk-collapsible').forEach(el=>{el.style.display=open?'':'none';});
}

// ── filter / search
function applyFilters(){
  if(!allRows.length) return;
  const q=document.getElementById('search-input').value.toLowerCase();
  const sf=document.getElementById('score-filter').value;
  const filtered=allRows.filter(row=>{
    const name=(row.items||row.description||'').toLowerCase();
    const best=row.matches&&row.matches.length?row.matches[0].score_pct:0;
    const qOk=!q||name.includes(q);
    const sOk=sf==='all'?true:sf==='80'?best>=80:sf==='50'?best>=50&&best<80:best<50;
    return qOk&&sOk;
  });
  renderRows(filtered);
}
document.getElementById('search-input').addEventListener('input',applyFilters);
document.getElementById('score-filter').addEventListener('change',applyFilters);

// ── download JSON
document.getElementById('download-btn').addEventListener('click',()=>{
  if(!lastResponse) return;
  const blob=new Blob([JSON.stringify(lastResponse,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='shipskart-parse-result.json'; a.click();
});
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

// ── state
let lastResponse=null, allRows=[];
// selections: rowIndex -> match object (or null = no selection)
const selections={};

// ── submit
submitBtn.addEventListener('click',async()=>{
  if(!selectedFile) return;
  const topN=parseInt(document.getElementById('top-n').value)||3;
  const advanced=document.getElementById('advanced-toggle').checked;
  const useLev=document.getElementById('use-levenshtein').checked;
  const useTfidf=document.getElementById('use-tfidf').checked;
  const useInv=document.getElementById('use-inverted-index').checked;

  const params=new URLSearchParams({top_n:String(topN)});
  params.set('advanced',String(advanced));
  params.set('use_levenshtein',String(useLev));
  params.set('use_tfidf',String(useTfidf));
  params.set('use_inverted_index',String(useInv));

  submitBtn.disabled=true; hideStatus();
  document.getElementById('summary-section').classList.add('hidden');
  document.getElementById('results-section').classList.add('hidden');
  setStatus('Uploading and parsing\u2026 this may take a few seconds.','loading');
  const form=new FormData();
  form.append('file',selectedFile);
  try{
    const res=await fetch(`${getBase()}/api/v1/parse/match?${params.toString()}`,{method:'POST',body:form});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail||'Server error '+res.status);
    lastResponse=data;
    // reset selections
    Object.keys(selections).forEach(k=>delete selections[k]);
    setStatus(`Done! ${data.summary.total_items} items parsed and matched.`,'success');
    let totalAmount=null;
    for(const tableData of Object.values(data.tables||{})){
      if(tableData.total_amount!=null) totalAmount=(totalAmount||0)+tableData.total_amount;
    }
    renderSummary(data.summary,totalAmount);
    renderResults(data.tables);
  } catch(err){
    setStatus('Error: '+err.message,'error');
  } finally{
    submitBtn.disabled=false;
  }
});

// ── summary
function renderSummary(s,totalAmount){
  const fmtAmount=(v)=>{
    if(v==null) return null;
    return new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(v);
  };
  const amountFormatted=fmtAmount(totalAmount);
  const amountTile=amountFormatted
    ?`<div class="summary-tile tile--amount">
        <div class="label">Total Amount (INR)</div>
        <div class="amount-value">${amountFormatted}</div>
      </div>`
    :'';
  document.getElementById('summary-grid').innerHTML=`
    <div class="summary-tile tile--total"><div class="value">${s.total_items}</div><div class="label">Total Items</div></div>
    <div class="summary-tile tile--strong"><div class="value">${s.matched_above_80}</div><div class="label">\u2265 80% Match</div></div>
    <div class="summary-tile tile--partial"><div class="value">${s.matched_above_50}</div><div class="label">50\u201379% Match</div></div>
    <div class="summary-tile tile--fail"><div class="value">${s.unmatched}</div><div class="label">Unmatched</div></div>
    ${amountTile}`;
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

  // find global index of each row in allRows (so selections key stays stable)
  rows.forEach(row=>{
    const globalIdx=allRows.indexOf(row);
    const best=row.matches&&row.matches.length?row.matches[0].score_pct:0;
    const cls=scoreClass(best);
    const currentSel=selections[globalIdx]; // match obj or undefined
    const selName=currentSel?currentSel.product_name:null;

    // Build the selection panel — one card per match candidate
    const optionCards=(row.matches||[]).map(m=>{
      const mc=scoreClass(m.score_pct);
      const isSel=currentSel&&currentSel.product_id===m.product_id;
      return `<div class="match-option ${isSel?'selected':''}" data-gidx="${globalIdx}" data-rank="${m.rank}"
                   data-pid="${m.product_id}" data-name="${m.product_name.replace(/"/g,'&quot;')}"
                   data-cat="${(m.category||'').replace(/"/g,'&quot;')}" data-brand="${(m.brand||'').replace(/"/g,'&quot;')}" data-unit="${m.unit||''}">
        <div class="match-option-radio">${isSel?'\u2022':''}</div>
        <div class="match-option-body">
          <span class="match-option-name">${m.product_name}</span>
          <span class="match-option-meta">${m.category||'\u2014'} &middot; ${m.brand||'\u2014'} &middot; ${m.unit||'\u2014'}</span>
        </div>
        <div class="match-option-score score--${mc}">${m.score_pct}%</div>
      </div>`;
    }).join('');

    // Selected label shown in collapsed header
    const selLabel=selName
      ?`<span class="item-sel-tag">\u2713 ${selName}</span>`
      :`<span class="item-sel-tag item-sel-tag--none">No selection</span>`;

    const metaChips=[
      row.unit_of_measurement&&`<span class="meta-chip">${row.unit_of_measurement}</span>`,
      row.category&&`<span class="meta-chip">${row.category}</span>`,
      row.skrt_code&&`<span class="meta-chip">${row.skrt_code}</span>`,
    ].filter(Boolean).join('');

    const div=document.createElement('div');
    div.className='item-row';
    div.dataset.gidx=globalIdx;
    div.innerHTML=`
      <div class="item-header" onclick="toggleRow(this)">
        <span class="item-num">${row.sr_no||'\u2014'}</span>
        <span class="item-name">${row.items||row.description||'\u2014'}</span>
        <span class="item-qty">${row.quantity!=null?row.quantity+' '+(row.unit_of_measurement||''):''}</span>
        <div class="item-header-right">
          ${selLabel}
          <span class="item-score score--${cls}">${best.toFixed(1)}%</span>
          <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </div>
      ${metaChips?`<div class="item-meta sk-collapsible" style="display:none">${metaChips}</div>`:''}
      <div class="selection-panel sk-collapsible" style="display:none">
        <p class="selection-hint">Click a product to select it for this item:</p>
        <div class="match-options">${optionCards}</div>
        <div class="selection-clear-wrap">
          <button class="btn btn--ghost btn--sm" onclick="clearSelection(${globalIdx})">Clear selection</button>
        </div>
      </div>`;
    container.appendChild(div);
  });

  // Attach click handlers for match-option cards
  container.querySelectorAll('.match-option').forEach(card=>{
    card.addEventListener('click',()=>{
      const gidx=parseInt(card.dataset.gidx);
      const match={
        product_id:   parseInt(card.dataset.pid),
        product_name: card.dataset.name,
        category:     card.dataset.cat,
        brand:        card.dataset.brand,
        unit:         card.dataset.unit,
        score_pct:    parseFloat(card.querySelector('.match-option-score').textContent),
      };
      selections[gidx]=match;
      // Re-render just this row's item-row div
      refreshRowUI(gidx);
    });
  });
}

function clearSelection(gidx){
  delete selections[gidx];
  refreshRowUI(gidx);
}

function refreshRowUI(gidx){
  // Re-render only the affected row without rebuilding the whole list
  const row=allRows[gidx];
  const div=document.querySelector(`.item-row[data-gidx="${gidx}"]`);
  if(!div) return;
  const wasOpen=div.classList.contains('open');
  const best=row.matches&&row.matches.length?row.matches[0].score_pct:0;
  const currentSel=selections[gidx];
  const selName=currentSel?currentSel.product_name:null;
  const selTagEl=div.querySelector('.item-sel-tag');
  if(selTagEl){
    selTagEl.textContent=selName?('\u2713 '+selName):'No selection';
    selTagEl.className='item-sel-tag'+(selName?'':' item-sel-tag--none');
  }
  div.querySelectorAll('.match-option').forEach(card=>{
    const isSel=currentSel&&parseInt(card.dataset.pid)===currentSel.product_id;
    card.classList.toggle('selected',isSel);
    card.querySelector('.match-option-radio').textContent=isSel?'\u2022':'';
  });
  if(wasOpen){
    div.classList.add('open');
    div.querySelectorAll('.sk-collapsible').forEach(el=>el.style.display='');
  }
}

function toggleRow(header){
  const row=header.parentElement;
  const open=row.classList.toggle('open');
  row.querySelectorAll('.sk-collapsible').forEach(el=>{el.style.display=open?'':'none';});
}

// ── auto-select all ≥80%
document.getElementById('auto-select-btn').addEventListener('click',()=>{
  allRows.forEach((row,idx)=>{
    if(row.matches&&row.matches.length){
      const best=row.matches[0];
      if(best.score_pct>=80) selections[idx]=best;
    }
  });
  document.querySelectorAll('.item-row').forEach(div=>{
    const gidx=parseInt(div.dataset.gidx);
    if(!isNaN(gidx)) refreshRowUI(gidx);
  });
  const count=Object.keys(selections).length;
  setStatus(`Auto-selected ${count} item${count!==1?'s':''} with \u2265 80% match.`,'success');
});

// ── save selections
document.getElementById('save-btn').addEventListener('click',()=>{
  if(!allRows.length){ setStatus('No results to save.','error'); return; }
  const output=allRows.map((row,idx)=>{
    const sel=selections[idx]||null;
    return {
      sr_no:              row.sr_no||null,
      requested_item:     row.items||row.description||null,
      quantity:           row.quantity||null,
      unit_of_measurement:row.unit_of_measurement||null,
      category:           row.category||null,
      selected_product:   sel,
      all_matches:        row.matches||[],
    };
  });
  const totalSelected=Object.keys(selections).length;
  const blob=new Blob([JSON.stringify({selections:output,meta:{total_items:allRows.length,total_selected:totalSelected,generated_at:new Date().toISOString()}},null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='shipskart-selections.json';
  a.click();
  setStatus(`Saved ${totalSelected} selection${totalSelected!==1?'s':''} out of ${allRows.length} items.`,'success');
});

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

// ── download raw JSON
document.getElementById('download-btn').addEventListener('click',()=>{
  if(!lastResponse) return;
  const blob=new Blob([JSON.stringify(lastResponse,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='shipskart-parse-result.json'; a.click();
});

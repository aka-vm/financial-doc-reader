'use strict';
const $ = id => document.getElementById(id);
let files = [], jobId = null, report = null, polling = false;
const headers = {'X-Brief-Request': '1'};
function node(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent=text; if(cls) n.className=cls; return n; }
function show(view) { for(const id of ['welcome','loading','workspace']) $(id).hidden = id !== view; }
function error(message) { $('upload-error').textContent=message; $('upload-error').hidden=!message; }
async function api(url, options={}) {
  const response=await fetch(url, {...options, credentials:'same-origin', headers:{...headers,...options.headers}});
  const data=await response.json();
  if(!response.ok){const err=new Error(data.error || 'The request failed. Please retry.');err.status=response.status;throw err;}
  return data;
}
function forgetBrief(){jobId=null;sessionStorage.removeItem('ledger-job');}
function unavailableBrief(){
  forgetBrief();show('welcome');$('generate').disabled=!files.length;
  error('Your previous brief is no longer available in this browser. Briefs expire after one hour. Use the same browser and address as before, or upload your files again.');
}
function addFiles(incoming) {
  error('');
  const merged=[...files]; for(const file of incoming) if(!merged.some(f=>(f.webkitRelativePath||f.name)===(file.webkitRelativePath||file.name)&&f.size===file.size)) merged.push(file);
  const deal=$('report-mode').value==='deal';
  if(merged.length>(deal?100:5)) return error(deal?'Choose up to 100 documents per deal.':'Choose up to 5 documents, or choose ABS deal report for a deal folder.');
  if(merged.reduce((sum,f)=>sum+f.size,0)>(deal?300:16)*1024*1024) return error(deal?'Your deal exceeds 300 MB.':'Your documents exceed 16 MB. Choose ABS deal report for a deal bundle.');
  if(merged.some(f=>!(/\.(pdf|txt|html?|csv|xml|zip|json)$/i.test(f.name)))) return error('Choose PDF, TXT, HTML, CSV, XML, or ZIP files.');
  files=merged; renderFiles();
}
function renderFiles(){ $('file-list').replaceChildren(); files.forEach((f,i)=>{ const li=node('li');li.append(node('span',f.webkitRelativePath||f.name),node('small',`${Math.max(1,Math.round(f.size/1024))} KB`));const remove=node('button','×');remove.type='button';remove.setAttribute('aria-label',`Remove ${f.name}`);remove.onclick=()=>{files.splice(i,1);renderFiles();};li.append(remove);$('file-list').append(li);});$('generate').disabled=!files.length; }

$('report-mode').onchange=()=>{$('generate').textContent=$('report-mode').value==='deal'?'Build deal report':'Generate brief';$('upload-limits').textContent=$('report-mode').value==='deal'?'PDF, TXT, HTML, CSV, XML, ZIP · 100 files · 300 MB total':'PDF, TXT, HTML, CSV, XML, ZIP · 5 files · 16 MB total';};
$('choose-folder').onclick=()=>$('folder-files').click();
$('folder-files').onchange=e=>{
  $('report-mode').value='deal';$('report-mode').onchange();
  const selected=Array.from(e.target.files).filter(f=>!(f.webkitRelativePath||f.name).split('/').some(p=>p.startsWith('.')||p==='__MACOSX')&&/\.(pdf|txt|html?|csv|xml|zip)$/i.test(f.name));
  addFiles(selected);e.target.value='';
};
$('files').onchange=e=>{addFiles(e.target.files);e.target.value='';};
$('dropzone').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('files').click();}};
for(const event of ['dragover','dragenter']) $('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.add('drag');});
for(const event of ['dragleave','drop']) $('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('drag');if(event==='drop')addFiles(e.dataTransfer.files);});
$('generate').onclick=async()=>{error('');$('generate').disabled=true;try{const form=new FormData();form.append('mode',$('report-mode').value);for(const f of files)form.append('files',f,f.webkitRelativePath||f.name);const result=await api('/api/briefs',{method:'POST',body:form});jobId=result.id;sessionStorage.setItem('ledger-job',jobId);show('loading');poll();}catch(e){error(e.message);$('generate').disabled=false;}};
async function poll(){
  if(polling)return;polling=true;
  try{
    while(jobId){
      const requestedId=jobId;let job;
      try{job=await api(`/api/briefs/${requestedId}`);}
      catch(e){
        if(jobId!==requestedId)continue;
        if(e.status===404 || e.status===403){unavailableBrief();break;}
        $('progress-label').textContent='Connection interrupted. Reconnecting to your brief…';
        await new Promise(r=>setTimeout(r,3000));continue;
      }
      if(jobId!==requestedId)continue;
      if(job.status==='error'){forgetBrief();show('welcome');error(job.error);$('generate').disabled=!files.length;break;}
      if(job.status==='done'){report=job.report;renderReport();show('workspace');break;}
      show('loading');$('progress-label').textContent=job.progress.label;
      $('progress').value=Math.round(100*job.progress.done/Math.max(1,job.progress.total));
      await new Promise(r=>setTimeout(r,1800));
    }
  }finally{polling=false;}
}
function citations(ids){const span=node('span',undefined,'citations');for(const id of ids){const button=node('button',id,'citation');button.type='button';button.setAttribute('aria-label',`View evidence ${id}`);button.onclick=()=>evidence([id]);span.append(button);}return span;}
function evidence(ids){$('evidence-content').replaceChildren();for(const id of ids){const f=[...report.facts,...(report.source_evidence||[]),...(report.subjects||[])].find(f=>f.id===id);if(!f)continue;const card=node('section',undefined,'evidence-card');card.append(node('p',`${f.id} / ${f.file} · ${f.page ? `Page ${f.page}` : `Extracted section ${f.section}`}`,'small'),node('h3',f.label),node('blockquote',f.quote),node('p','Quotation matched to extracted source text. Interpretation and accounting accuracy are not independently verified.','evidence-note'));if(f.context_quote){card.append(node('p','Column headings / scope','small'),node('blockquote',f.context_quote));}if(f.context_problem)card.append(node('p',`Context review flagged this interpretation: ${f.context_problem}`,'error'));$('evidence-content').append(card);}$('evidence-dialog').showModal();}
$('close-evidence').onclick=()=>$('evidence-dialog').close();
$('evidence-dialog').onclick=e=>{if(e.target===$('evidence-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}};
function renderReport(){
if(report.type==='deal'){renderDeal();return;}
document.querySelector('.sidebar').hidden=false;
$('question-form').closest('section').hidden=false;
$('ask').disabled=false;$('question').disabled=false;$('delete').disabled=false;const target=$('report');target.replaceChildren();const heading=node('div',undefined,'report-heading');heading.append(node('span','LEDGER / FINANCIAL BRIEF','eyebrow'),node('span','SOURCE-LINKED','tag'));target.append(heading);const subjects=report.subjects||[];const distinctSubjects=[...new Map(subjects.map(subject=>[subject.name.toLocaleLowerCase(),subject])).values()];
if(distinctSubjects.length===1){const subject=distinctSubjects[0];const identity=node('div',undefined,'company-identity');identity.append(node('h1',subject.name));if(subject.ticker)identity.append(node('span',subject.ticker,'company-ticker'));identity.append(citations(subjects.map(s=>s.id)));target.append(identity,node('p',report.title,'report-description'));}
else{target.append(node('h1',report.title));if(subjects.length){for(const subject of subjects){const identity=node('p',`${subject.name}${subject.ticker?' · '+subject.ticker:''} — ${subject.file}`,'company-list');identity.append(citations([subject.id]));target.append(identity);}}else target.append(node('p','Company / entity not identified in the extracted text.','small'));}
target.append(node('p',report.subtitle,'subtitle'));const overview=node('section');for(const c of report.overview){const p=node('p',c.text,'claim');p.append(citations(c.evidence));overview.append(p);}target.append(overview);
const numeric=report.facts.filter(f=>report.display_fact_ids ? report.display_fact_ids.includes(f.id) : /\d/.test(f.value)).slice(0,6);if(numeric.length){const sec=node('section');sec.append(node('h2','THE FIGURES TO KNOW'));const grid=node('div',undefined,'facts');for(const f of numeric){const card=node('div',undefined,'fact');card.append(node('p',f.label,'fact-label'),node('p',f.value,'fact-value'),node('span',[f.period,f.unit].filter(Boolean).join(' · '),'fact-context'),citations([f.id]));grid.append(card);}sec.append(grid);target.append(sec);}
renderDataViews(target);
for(const [key,label] of [['highlights','WHAT MATTERS'],['risks','WHAT DESERVES A CLOSER LOOK']]){if(!report[key].length)continue;const sec=node('section');sec.append(node('h2',label));for(const c of report[key]){const p=node('p',c.text,'claim');p.append(citations(c.evidence));sec.append(p);}target.append(sec);}
if(report.questions.length){const sec=node('section');sec.append(node('h2','QUESTIONS WORTH ASKING'));const ul=node('ul');report.questions.slice(0,3).forEach(q=>ul.append(node('li',q)));sec.append(ul);target.append(sec);}
const notes=node('div',undefined,'report-notes');notes.append(node('strong',`${report.coverage.files} document${report.coverage.files===1?'':'s'} · ${report.coverage.sections} reading sections · ${report.facts.length} source-matched facts`),node('p',report.check_note));if(report.omitted_metadata)notes.append(node('p',`${report.omitted_metadata} period or unit labels were omitted because they were not supported by their quoted passages.`));if(report.rejected)notes.append(node('p',`${report.rejected} extracted facts or statements were withheld after source checks.`));if(report.warnings.length){const details=node('details');details.append(node('summary',`${report.warnings.length} coverage warning(s)`));for(const w of report.warnings)details.append(node('p',w));notes.append(details);}const all=node('button',`Explore all ${report.facts.length} source passages →`,'text-button');all.onclick=()=>evidence(report.facts.map(f=>f.id));notes.append(all);const printed=node('div',undefined,'print-sources');const used=new Set(['overview','highlights','risks'].flatMap(k=>report[k].flatMap(c=>c.evidence)));numeric.forEach(f=>used.add(f.id));const sourceGroups=new Map();for(const f of report.facts.filter(f=>used.has(f.id))){if(!sourceGroups.has(f.source))sourceGroups.set(f.source,{fact:f,ids:[]});sourceGroups.get(f.source).ids.push(f.id);}for(const {fact,ids} of sourceGroups.values())printed.append(node('p',`${ids.join(', ')}: ${fact.file} — ${fact.page ? `page ${fact.page}` : `extracted section ${fact.section}`}`));notes.append(printed);target.append(notes);
$('suggestions').replaceChildren();for(const q of report.questions.slice(0,3)){const b=node('button',q);b.onclick=()=>{$('question').value=q;$('question-form').requestSubmit();};$('suggestions').append(b);}$('answer').replaceChildren();}
$('question-form').onsubmit=async e=>{e.preventDefault();$('ask').disabled=true;$('answer').textContent='Reading the evidence…';try{const briefId=jobId;const started=await api(`/api/briefs/${briefId}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:$('question').value})});let answerJob;do{await new Promise(resolve=>setTimeout(resolve,1000));if(jobId!==briefId)return;answerJob=await api(`/api/briefs/${briefId}/answers/${started.id}`);}while(answerJob.status==='running');if(answerJob.status==='error')throw new Error(answerJob.error);const data=answerJob.result;report.source_evidence=[...(report.source_evidence||[]),...(data.evidence_details||[])];$('answer').replaceChildren(node('p',data.answer),citations(data.evidence));}catch(err){if(err.status===404 || err.status===403){forgetBrief();$('question').disabled=true;$('delete').disabled=true;for(const b of $('suggestions').querySelectorAll('button'))b.disabled=true;$('answer').textContent='This brief is no longer available on the server. You can still save the brief shown here. Choose New brief to upload again.';}else{$('answer').textContent=err.message;}}finally{$('ask').disabled=!jobId;}};
$('print').onclick=()=>window.print();
$('download').onclick=()=>exportReport($('export-format').value);
$('new-brief').onclick=()=>{jobId=null;report=null;sessionStorage.removeItem('ledger-job');show('welcome');$('generate').disabled=!files.length;error('');};
$('delete').onclick=async()=>{try{await api(`/api/briefs/${jobId}`,{method:'DELETE'});$('new-brief').click();}catch(e){$('answer').textContent=e.message;}};
const previous=sessionStorage.getItem('ledger-job');if(previous){jobId=previous;show('loading');poll();}

function renderDeal(){
  document.querySelector('.sidebar').hidden=false;
  $('question-form').closest('section').hidden=true;
  const target=$('report');target.replaceChildren();
  let table=null,list=null;
  const clean=text=>text.replace(/\*\*/g,'').replace(/`/g,'');
  for(const line of report.markdown.split('\n')){
    if(line.startsWith('|')){
      if(/^\|[ :|\-]+\|$/.test(line))continue;
      if(!table){table=node('table');target.append(table);}
      const row=node('tr');for(const cell of line.slice(1,-1).split('|'))row.append(node('td',clean(cell.trim())));table.append(row);continue;
    }
    table=null;
    if(!line.trim()){list=null;continue;}
    const heading=line.match(/^(#{1,3}) (.*)$/);
    if(heading){target.append(node('h'+heading[1].length,clean(heading[2])));list=null;}
    else if(line.startsWith('- ')){if(!list){list=node('ul');target.append(list);}list.append(node('li',clean(line.slice(2))));}
    else{target.append(node('p',clean(line)));list=null;}
  }
}

loadExamples();

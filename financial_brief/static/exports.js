'use strict';
function exportReport(format){
  const subjects=[...new Set((report.subjects||[]).map(s=>s.name+(s.ticker?` (${s.ticker})`:'')))];
  const title=subjects.join(' / ')||report.title||'Ledger report';
  const safe=text=>String(text??'').replace(/\|/g,'\\|').replace(/\r?\n/g,' ');
  let text,type,extension;
  if(format==='csv'){
    const rows=[['Company / entity','Metric','Reported value','Period','Unit','Source file','Evidence ID','Source quotation']];
    if(report.type==='deal'){
      for(const month of report.deal.months)for(const [key,value] of Object.entries(month.report))if(value!==null && typeof value!=='object')rows.push([month.report.trust||title,key,value,month.report.period_end,'',month.file,'','']);
      for(const tape of report.deal.tapes)for(const [key,value] of Object.entries(tape))if(value!==null && typeof value!=='object')rows.push([title,key,value,tape.period_end,'',tape.file,'','']);
    }else for(const fact of report.facts)rows.push([(report.subjects||[]).find(s=>s.file===fact.file)?.name||'',fact.label,fact.value,fact.period,fact.unit,fact.file,fact.id,fact.quote]);
    const cell=value=>{let s=String(value??'');if(/^\s*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
    text='\uFEFF'+rows.map(row=>row.map(cell).join(',')).join('\r\n');type='text/csv;charset=utf-8';extension='csv';
  }else if(format==='markdown'){
    if(report.type==='deal')text=report.markdown;
    else{
      const parts=[`# ${safe(title)}`,safe(report.title),safe(report.subtitle)];
      for(const [key,label] of [['overview','Overview'],['highlights','Highlights'],['risks','Needs a closer look']]){if(report[key]?.length){parts.push(`\n## ${label}`);for(const claim of report[key])parts.push(`${safe(claim.text)} [${claim.evidence.join(', ')}]`);}}
      parts.push('\n## Reported figures','| Metric | Value | Period / unit | Source |','|---|---|---|---|');
      for(const fact of report.facts)parts.push(`| ${safe(fact.label)} | ${safe(fact.value)} | ${safe([fact.period,fact.unit].filter(Boolean).join(' · '))} | ${safe(fact.file)} [${fact.id}] |`);
      parts.push('\n## Source evidence');for(const fact of report.facts)parts.push(`\n**${fact.id} — ${safe(fact.file)}**\n> ${safe(fact.quote)}`);
      for(const subject of report.subjects||[])parts.push(`\n**${subject.id} — ${safe(subject.file)}: ${safe(subject.name)}**\n> ${safe(subject.quote)}`);
      parts.push('\n## Reading notes',safe(report.check_note),...(report.warnings||[]).map(safe));text=parts.join('\n\n');
    }
    type='text/markdown;charset=utf-8';extension='md';
  }else{text=JSON.stringify(report,null,2);type='application/json';extension='json';}
  const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download='ledger-report.'+extension;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

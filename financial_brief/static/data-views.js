'use strict';
function svgNode(tag, attributes={}, text) {
  const el=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const [key,value] of Object.entries(attributes))el.setAttribute(key,String(value));
  if(text!==undefined)el.textContent=text;
  return el;
}
function renderDataViews(target){
  const views=report.visuals;
  if(!views || (!views.rows.length && !views.charts.length))return;
  const section=node('section',undefined,'data-views');section.append(node('h2','FIGURES & COMPARISONS'));
  if(views.charts.length)section.append(node('p','Matching metrics and units from the same source section. Values are copied from cited facts; no growth rates or currency conversions are calculated.','small'));
  views.charts.forEach((chart,index)=>{
    const figure=node('figure',undefined,'comparison-chart');figure.append(node('figcaption',`${chart.title} · ${chart.unit}`));
    const svg=svgNode('svg',{viewBox:'0 0 600 230',role:'img','aria-labelledby':`chart-title-${index}`});
    svg.append(svgNode('title',{id:`chart-title-${index}`},`${chart.title}, ${chart.unit}. `+chart.points.map(p=>`${p.period}: ${p.value}`).join('; ')));
    const low=Math.min(0,...chart.points.map(p=>p.number)),high=Math.max(0,...chart.points.map(p=>p.number));
    const span=high-low||1,y=value=>175-(value-low)/span*125,zero=y(0),slot=500/chart.points.length;
    svg.append(svgNode('line',{x1:45,x2:555,y1:zero,y2:zero,class:'chart-baseline'}));
    svg.append(svgNode('text',{x:35,y:zero+4,'text-anchor':'end',class:'chart-axis'},'0'));
    chart.points.forEach((point,i)=>{
      const x=55+i*slot+slot*.2,width=slot*.6,top=Math.min(y(point.number),zero),height=Math.abs(y(point.number)-zero);
      const bar=svgNode('rect',{x,y:top,width,height:Math.max(height,1),rx:2,class:point.number<0?'chart-bar negative':'chart-bar',tabindex:0});
      bar.append(svgNode('title',{},`${point.period}: ${point.value} (${point.evidence.join(', ')})`));svg.append(bar);
      svg.append(svgNode('text',{x:x+width/2,y:point.number<0?y(point.number)+16:top-10,'text-anchor':'middle',class:'chart-value'},point.value));
      svg.append(svgNode('text',{x:x+width/2,y:215,'text-anchor':'middle',class:'chart-axis'},point.period));
    });
    figure.append(svg,node('p',chart.file,'small'));
    for(const point of chart.points){const source=node('span',`${point.period} `,'chart-source');source.append(citations(point.evidence));figure.append(source);}
    section.append(figure);
  });
  if(views.rows.length){
    const details=node('details',undefined,'figures-table');details.open=!views.charts.length;
    details.append(node('summary',`Source-linked figures (${views.total_rows})`));
    const wrap=node('div',undefined,'table-scroll'),table=node('table'),head=node('thead'),row=node('tr');
    for(const label of ['Metric','Reported value','Period / unit','Source']){const th=node('th',label);th.scope='col';row.append(th);}head.append(row);table.append(head);
    const body=node('tbody');for(const fact of views.rows){const tr=node('tr');tr.append(node('td',fact.label),node('td',fact.value),node('td',[fact.period,fact.unit].filter(Boolean).join(' · ')));const source=node('td');source.append(node('span',fact.file),citations([fact.id]));if(fact.context_reviewed===false)source.append(node('small','Source match only; context not reviewed'));tr.append(source);body.append(tr);}table.append(body);wrap.append(table);details.append(wrap);
    if(views.total_rows>views.rows.length)details.append(node('p',`Showing ${views.rows.length} of ${views.total_rows} figures. Explore all source passages below for the full extracted evidence.`,'small'));
    if(!views.charts.length)details.append(node('p','No unambiguous comparison series was found. The reported values remain available in this table.','small'));
    section.append(details);
  }
  target.append(section);
}
let exampleCatalog=[];
function randomExamples(items,count=6){
  const shuffle=values=>{
    const result=[...values];
    for(let i=result.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[result[i],result[j]]=[result[j],result[i]];}
    return result;
  };
  const groups=new Map();
  for(const item of items){
    const type=item.report_type||'Other';
    if(!groups.has(type))groups.set(type,[]);
    groups.get(type).push(item);
  }
  const queues=[...groups.values()].map(shuffle),selected=[];
  // Give every report type equal opportunity, regardless of its catalog size.
  while(selected.length<Math.min(count,items.length)){
    for(const queue of shuffle(queues.filter(group=>group.length))){
      selected.push(queue.pop());
      if(selected.length===Math.min(count,items.length))break;
    }
  }
  return selected;
}
function renderExampleCards(examples){
  const list=$('example-list');list.replaceChildren();
  for(const item of examples){
    const card=node('article',undefined,'example-card');card.dataset.exampleId=item.id;
    const tags=node('div',undefined,'example-tags');
    for(const tag of (item.tags||[item.report_type||item.category]).slice(0,3))tags.append(node('span',tag,'example-tag'));
    card.append(tags,node('h3',item.title),node('span',`${item.category} · ${item.format}`,'example-category'),node('p',item.description),node('span',item.source_kind||'Primary source','example-badge'));
    const downloadSize=item.size_bytes<1024*1024?`${Math.ceil(item.size_bytes/1024)} KB`:`${(item.size_bytes/1024/1024).toFixed(1)} MB`;
    card.append(node('p',`${item.period||''} · ${item.scope||''} · ${downloadSize} download`,'example-scope'));
    if(item.limitations)card.append(node('p',item.limitations,'example-limitations'));
    const origin=node('a','Original source');origin.href=item.source_url;origin.target='_blank';origin.rel='noopener noreferrer';origin.className='original-source';card.append(origin);
    const actions=node('div',undefined,'example-actions'),source=node('a',item.name.endsWith('.zip')?'Download bundle':'View full document');source.href=item.url;source.target='_blank';source.rel='noopener';
    const load=node('button','Load example','text-button');load.type='button';
    load.onclick=async()=>{
      load.disabled=true;error('');
      try{
        const response=await fetch(item.url);if(!response.ok)throw new Error('Example unavailable. Please try another.');
        const file=new File([await response.blob()],item.name);
        files=[];$('report-mode').value=item.mode;$('report-mode').onchange();addFiles([file]);
        $('generate').scrollIntoView({behavior:'smooth',block:'center'});
      }catch(e){error(e.message);}finally{load.disabled=false;}
    };
    actions.append(source,load);card.append(actions);list.append(card);
  }
}
async function loadExamples(){
  try{
    exampleCatalog=await api('/api/examples');
    $('examples-count').textContent='6 random';
    renderExampleCards(randomExamples(exampleCatalog));
    $('shuffle-examples').onclick=()=>renderExampleCards(randomExamples(exampleCatalog));
  }catch(e){$('example-list').replaceChildren(node('p','Examples could not be loaded. You can still upload your own documents.','small'));$('shuffle-examples').disabled=true;}
}

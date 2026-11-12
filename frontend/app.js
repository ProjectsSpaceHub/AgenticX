
 // Agentic X real integration: progress comes from real Python agent evaluations.
const $ = id => document.getElementById(id);
const agentNames = ['Creative','Finance','Operations','Safety'];
const agentColors = {Creative:'#d4a2ff',Finance:'#ffd099',Operations:'#99d1ff',Safety:'#a2f2b0'};
const scenarioMeta = {
 'Screen Failure':{title:'Screen Failure',impact:'High'},
 'Budget Overrun':{title:'Budget Overrun',impact:'High'},
 'Safety Conflict':{title:'Safety Conflict',impact:'Critical'}
};
let scenarioGroups=[], baseCase=null, caseRequestSerial=0;
let activeJob=null, polling=null, messages=[], cursor=0, agentsState={}, latestResult=null, selectedAgent=null;
let agentSpeech={}, replayReady=false, agentClickProgress={}, agentRoundLabel={};

const text = (id, value) => $(id).textContent = String(value);

function resetStatuses(){
 agentsState=Object.fromEntries(agentNames.map(n=>[n,'Idle']));
 agentSpeech={};agentClickProgress={};agentRoundLabel={};
}
function compactReason(value){
 const clean=String(value||'').replace(/\s+/g,' ').trim();
 const first=clean.match(/^.{1,120}?(?:[.!?](?=\s|$)|$)/)?.[0]||clean;
 return first.length>116?first.slice(0,113).trimEnd()+'…':first;
}
function safeMessageElement(message,index){
 const r=document.createElement('div');
 r.className='row';
 r.style.setProperty('--c',agentColors[message.sender]||'#ded0ff');
 const num=document.createElement('span');
 num.textContent=String(index+1).padStart(2,'0');
 const sender=document.createElement('strong');
 sender.textContent=message.sender;
 const details=document.createElement('span');
 details.textContent=`${message.receiver} · ${message.performative} · R${message.round}`;
 const content=document.createElement('span');
 content.className='msg';
 content.textContent=message.content;
 r.append(num,sender,details,content);
 return r;
}
function renderLog(){
 const log=$('log');log.replaceChildren();
 if(!messages.length){
  const e=document.createElement('div');e.className='empty';
  e.textContent=activeJob?'Running real agents...':'Run a scenario to see the recorded ACL negotiation.';
  log.append(e);return;
 }
 messages.forEach((m,i)=>log.append(safeMessageElement(m,i)));
}
function renderAgents(){
 const root=$('agents');root.replaceChildren();
 agentNames.forEach(name=>{
  const holder=document.createElement('div');
  holder.className='agent';
  if(selectedAgent===name)holder.classList.add('selected');
  holder.classList.add((agentsState[name]||'Idle').toLowerCase());
  const bubble=document.createElement('div');bubble.className='bubble';
  bubble.textContent=agentSpeech[name]||(
   agentsState[name]==='Evaluating'?'Reviewing the proposal…':
   agentsState[name]==='Idle'?(replayReady?'Click me to hear my evaluation':'Ready to evaluate.'):
   agentsState[name]
  );
  bubble.title=agentSpeech[name]||'';
  const btn=document.createElement('button');
  btn.type='button';btn.setAttribute('aria-label',`Select ${name} Agent`);
  const robot=document.createElement('div');robot.className='robot';
  const label=document.createElement('span');label.className='name';
  label.textContent=`${name} Agent`;
  const state=document.createElement('div');state.className='state';
  state.textContent='● '+(agentsState[name]||'Idle')+
    (agentRoundLabel[name]?' · '+agentRoundLabel[name]:'');
  btn.append(robot,label,state);
  btn.addEventListener('click',()=>handleAgentClick(name));
  holder.append(bubble,btn);root.append(holder);
 });
}
function controls(){
 updateChanged();
 text('budgetOut',Number($('budget').value||0).toLocaleString('en-US')+' SAR');
 text('timeOut',$('time').value+' minutes');
 text('equipmentOut',$('equipment').value==='available'?'Available':'Unavailable');
}
function formatSar(value){
 return Number(value||0).toLocaleString('en-US')+' SAR';
}
function originalBudget(c){return Number(c.initial_budget_sar ?? c.budget_sar ?? 0);}
function originalTime(c){return Number(c.time_left_min ?? 0);}
function originalEquipment(c){return Boolean(c.backup_available);}
function renderCaseOptions(options){
 const container=$('scenarioOptions');container.replaceChildren();
 (options||[]).forEach(o=>{
  const card=document.createElement('div');card.className='scenario-option';
  const heading=document.createElement('strong');
  heading.textContent=(o.option_id||'')+' · '+(o.option_name||'');
  const facts=document.createElement('span');facts.className='option-facts';
  facts.textContent=`Cost: ${formatSar(o.cost_sar)} · Duration: ${o.duration_min ?? '—'} min · Quality: ${o.quality_score ?? '—'}`;
  const backup=document.createElement('span');backup.className='option-backup';
  const needsBackup=o.needs_backup===true||o.needs_backup===1||
    String(o.needs_backup).toLowerCase()==='true';
  backup.textContent='Backup Equipment: '+(needsBackup?'Required':'Not required');
  card.append(heading,facts,backup);container.append(card);
 });
}
function showScenario(){
 const c=baseCase?.case;const type=$('scenarioType').value;
 text('scenarioTitle',scenarioMeta[type]?.title||type);
 text('scenarioDescription',c?.incident||'Loading scenario data…');
}
function updateChanged(){
 if(!baseCase)return;
 const c=baseCase.case;
 const altered=Number($('budget').value)!==originalBudget(c)||
  Number($('time').value)!==originalTime(c)||
  ($('equipment').value==='available')!==originalEquipment(c);
 text('changeIndicator',altered?'Modified test conditions':'Original dataset values');
}
function resetOriginal(){
 if(!baseCase||activeJob)return;
 const c=baseCase.case;
 $('budget').value=originalBudget(c);
 $('time').value=originalTime(c);
 $('equipment').value=originalEquipment(c)?'available':'unavailable';
 controls();updateChanged();
}
async function selectCase(){
 if(activeJob)return;
 const serial=++caseRequestSerial;
 const id=$('scenario').value;baseCase=null;
 text('scenarioOriginal','Loading case details…');
 text('scenarioDescription','Loading case data…');
 $('run').disabled=true;
 try{
  const r=await fetch('/api/case/'+encodeURIComponent(id));
  if(!r.ok)throw Error('Could not load case data');
  const data=await r.json();
  if(serial!==caseRequestSerial)return;
  baseCase=data;const c=data.case;
  text('scenarioOriginal',`Case ${c.case_id} · Budget: ${formatSar(originalBudget(c))} · Time: ${originalTime(c)} min · Equipment: ${originalEquipment(c)?'Available':'Unavailable'} · Minimum quality: ${c.required_quality_min ?? '—'}/100`);
  renderCaseOptions(data.options);
  resetOriginal();reset();showScenario();
 }catch(err){
  if(serial!==caseRequestSerial)return;
  text('scenarioOriginal','Could not load original case values: '+err.message);
  text('status','DATA ERROR');text('explanation',err.message);
  $('run').disabled=true;
 }
}
async function selectType(){
 const type=$('scenarioType').value;
 const records=scenarioGroups.find(g=>g.type===type)?.cases||[];
 const select=$('scenario');select.replaceChildren();
 records.forEach(c=>{
  const o=document.createElement('option');
  o.value=c.case_id;o.textContent=c.case_id;select.append(o);
 });
 if(records.length){
  $('catalogNotice').style.display='none';
  await selectCase();
 }else{
  const o=document.createElement('option');
  o.value='';o.textContent='No cases found';select.append(o);
  $('catalogNotice').textContent='No cases found for this scenario. Check the dataset and restart FastAPI.';
  $('catalogNotice').style.display='block';$('run').disabled=true;
 }
}
async function initCatalog(){
 try{
  const r=await fetch('/api/scenarios');
  if(!r.ok)throw Error('Catalog unavailable');
  scenarioGroups=await r.json();await selectType();
 }catch(err){
  text('scenarioOriginal','Case catalog error: '+err.message);
  const s=$('scenario');s.replaceChildren();
  const o=document.createElement('option');
  o.value='';o.textContent='Could not load cases';s.append(o);
  $('catalogNotice').textContent='Cannot load the case list from Python API. Restart the FastAPI cell in Colab, then refresh this page. ('+err.message+')';
  $('catalogNotice').style.display='block';$('run').disabled=true;
 }
}
function showDecision(result){
 latestResult=result;
 const agreed=result.status==='AGREED';
 text('status',agreed?'AGREED':result.status);
 $('status').className=agreed?'decision':'';
 text('explanation',`${result.reason} · ${result.rounds} round(s) · ${result.evaluations.length} evaluations`);
 text('solution',result.selected_option_name||result.selected_option_id||
  'No approved solution — human escalation');
 text('cost',result.selected_option?.cost_sar!=null?
  Number(result.selected_option.cost_sar).toLocaleString('en-US')+' SAR':'—');
 text('duration',result.selected_option?.duration_min!=null?
  result.selected_option.duration_min+' minutes':'—');
 text('safety',agreed?'Approved by Safety Agent':'No approved final solution');
 showScenario();
}
function stopPolling(){
 if(polling){clearInterval(polling);polling=null;}
}
async function pollJob(jobId){
 try{
  const r=await fetch('/api/job/'+encodeURIComponent(jobId));
  const j=await r.json();
  if(!r.ok)throw Error(j.detail||'Polling failed');
  if(activeJob!==jobId)return;
  if(!replayReady){
   agentNames.forEach(name=>{
    const status=j.agent_status?.[name];
    if(status==='Evaluating')agentsState[name]='Evaluating';
   });
  }
  renderAgents();
  if(j.status==='COMPLETED'){
   stopPolling();activeJob=null;
   messages=j.result.messages||[];
   cursor=0;latestResult=j.result;replayReady=true;
   resetStatuses();selectedAgent=null;
   agentNames.forEach(name=>{
    const evaluations=evaluationsFor(name);
    if(!evaluations.length){
     agentsState[name]='Idle';agentSpeech[name]='No evaluation recorded';return;
    }
    const last=evaluations[evaluations.length-1];
    agentsState[name]=last.approved?'Accepted':'Rejected';
    agentRoundLabel[name]='R'+evaluations.length+' · '+last.option_id;
    agentSpeech[name]=name==='Finance'?financeSummary(last):
      `${last.approved?'✓ Accepted':'✕ Rejected'} · Round ${evaluations.length} · ${last.option_id}`;
   });
   showDecision(j.result);
   $('run').disabled=false;renderAgents();renderLog();
  }else if(j.status==='ERROR'){
   stopPolling();activeJob=null;
   text('status','EXECUTION ERROR');
   text('explanation',j.error||'See Python backend logs');
   $('run').disabled=false;renderLog();
  }else{
   text('status','Running real agents');
   text('explanation','Waiting for actual evaluations. Gemini API calls may take time.');
  }
 }catch(err){
  stopPolling();activeJob=null;
  text('status','CONNECTION ERROR');text('explanation',err.message);
  $('run').disabled=false;
 }
}
async function run(){
 if(activeJob||!baseCase)return;
 stopPolling();resetStatuses();selectedAgent=null;
 messages=[];cursor=0;latestResult=null;replayReady=false;
 $('run').disabled=true;
 text('status','Starting run');
 text('explanation','Sending scenario inputs to the real Python multi-agent system...');
 renderAgents();renderLog();
 const body={
  case_id:$('scenario').value,
  budget_sar:Number($('budget').value),
  time_left_min:Number($('time').value),
  equipment_available:$('equipment').value==='available'
 };
 try{
  const r=await fetch('/api/start',{
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify(body)
  });
  const j=await r.json();
  if(!r.ok)throw Error(j.detail||'Run rejected');
  activeJob=j.job_id;
  await pollJob(activeJob);
  if(activeJob)polling=setInterval(()=>pollJob(activeJob),1200);
 }catch(err){
  activeJob=null;text('status','RUN FAILED');
  text('explanation',err.message);$('run').disabled=false;
 }
}
function evaluationsFor(name){
 return (latestResult?.evaluations||[]).filter(e=>e.agent===name);
}
function financeSummary(evaluation){
 const info=latestResult?.finance_breakdown?.[evaluation.option_id];
 if(!info)return compactReason(evaluation.reason);
 const amount=x=>Number(x).toLocaleString('en-US',{
  minimumFractionDigits:0,maximumFractionDigits:2
 });
 const remaining=Number(info.remaining_sar);
 const balance=remaining>=0?
  `Remaining: ${amount(remaining)} SAR`:
  `Over budget: ${amount(-remaining)} SAR`;
 return `R${evaluationsFor('Finance').indexOf(evaluation)+1} · ${evaluation.option_id} | Budget: ${amount(info.current_budget_sar)} · Cost: ${amount(info.option_cost_sar)} · ${balance}`;
}
function handleAgentClick(name){
 selectedAgent=name;
 if(activeJob){
  agentSpeech[name]='Still evaluating the real scenario…';
  renderAgents();return;
 }
 if(!replayReady||!latestResult){
  renderAgents();return;
 }
 const evaluations=evaluationsFor(name);
 if(!evaluations.length){
  agentSpeech[name]='No evaluation recorded for this agent.';
  renderAgents();return;
 }
 const idx=(agentClickProgress[name]||0)%evaluations.length;
 const evaluation=evaluations[idx];
 agentsState[name]=evaluation.approved?'Accepted':'Rejected';
 agentRoundLabel[name]=`R${idx+1} · ${evaluation.option_id}`;
 agentSpeech[name]=name==='Finance'?financeSummary(evaluation):
  `R${idx+1} · ${evaluation.option_id}: ${compactReason(evaluation.reason)}`;
 agentClickProgress[name]=idx+1;renderAgents();
}
function reset(){
 stopPolling();activeJob=null;messages=[];
 cursor=0;selectedAgent=null;latestResult=null;replayReady=false;
 resetStatuses();
 $('run').disabled=!baseCase;
 text('status','Awaiting Simulation');
 text('explanation','Run a real scenario using the Python backend.');
 ['solution','cost','duration','safety'].forEach(id=>text(id,'—'));
 renderAgents();renderLog();showScenario();
}
$('run').addEventListener('click',run);
$('reset').addEventListener('click',reset);
['budget','time','equipment'].forEach(id=>$(id).addEventListener('input',controls));
$('scenario').addEventListener('change',selectCase);
$('scenarioType').addEventListener('change',selectType);
$('resetOriginal').addEventListener('click',resetOriginal);
resetStatuses();reset();controls();initCatalog();

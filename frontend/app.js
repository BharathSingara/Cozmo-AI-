'use strict';
const $=id=>document.getElementById(id);
const state={id:null,stream:null,active:false,paused:false,busy:false,finished:false,voice:false,recognizer:null,speaking:false,packet:null,tab:'books',timer:null,framesTimer:null,pollTimer:null,startMs:null};
const regions={IN:'INR',US:'USD',GB:'GBP',CA:'CAD',AU:'AUD',DE:'EUR',FR:'EUR'};
const headers=()=>({'x-access-key':$('access').value.trim()});
async function api(path,opts={}){const r=await fetch(path,{...opts,headers:{...headers(),...(opts.headers||{})}});if(!r.ok){const detail=await r.text();throw Error(`HTTP ${r.status}: ${detail.slice(0,200)}`)}return r.headers.get('content-type')?.includes('application/json')?r.json():r;}
const say=(s)=>{const t=$('transcript');t.textContent=(t.textContent+'\n'+s).slice(-2000);t.scrollTop=t.scrollHeight};
const warning=e=>{$('errors').textContent=String(e);console.warn(e)};
const status=s=>{$('status').textContent=s;$('connection').classList.toggle('on',state.active&&!state.paused)};
const mny=v=>Number.isFinite(v)?`${v.toLocaleString(undefined,{maximumFractionDigits:2})} ${state.packet?.sweep.currency||''}`:'Unpriced';
function speak(text){say('Agent: '+text);if(!('speechSynthesis' in window))return;try{window.speechSynthesis.cancel();state.speaking=true;state.recognizer?.stop();const u=new SpeechSynthesisUtterance(text);u.rate=1.02;u.onend=()=>{state.speaking=false;startListening()};u.onerror=()=>{state.speaking=false;startListening()};window.speechSynthesis.speak(u)}catch(e){warning(e)}}
function startListening(){if(!state.voice||!state.active||state.paused||state.speaking)return;try{state.recognizer?.start()}catch(e){/* already listening */}}
function setVoice(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){speak('Voice transcription is not supported in this browser. You can type corrections instead.');return}state.voice=!state.voice;$('mic').textContent=state.voice?'🎙 Stop listening':'🎙 Enable voice';$('mic-state').textContent=state.voice?'Listening (when not speaking)':'Not listening';if(state.voice){const rec=new SR();rec.lang='en-IN';rec.continuous=true;rec.interimResults=false;rec.onresult=e=>{for(let i=e.resultIndex;i<e.results.length;i++)if(e.results[i].isFinal)runCommand(e.results[i][0].transcript)};rec.onend=()=>{if(state.voice&&!state.speaking&&state.active&&!state.paused)setTimeout(startListening,500)};rec.onerror=e=>say('Microphone: '+e.error);state.recognizer=rec;startListening()}else state.recognizer?.stop()}
function screen(){let packet=state.packet;if(!packet)return;
const booksCount=packet.books.filter(b=>!b.excluded).length;
const itemsCount=packet.items.filter(i=>!i.excluded).length;
const reviewCount=packet.review_queue.length;
$('book-count').textContent=packet.totals.book_count;$('item-count').textContent=itemsCount;$('review-count').textContent=reviewCount;$('count-state').textContent=`${packet.books.length+packet.items.length} saved`;$('new-value').textContent=mny(packet.totals.books_replacement_cost);$('used-value').textContent=mny(packet.totals.books_used_value);$('items-value').textContent=`${mny(packet.totals.items_replacement_cost_low)} – ${mny(packet.totals.items_replacement_cost_high)}`;$('area').textContent=`Room floor: ${packet.room.floor_area_m2??'unavailable'} m²; walls: ${packet.room.wall_area_m2??'unavailable'} m²`;
const tabBooks=document.querySelector('[data-tab="books"]');
const tabItems=document.querySelector('[data-tab="items"]');
const tabReviews=document.querySelector('[data-tab="reviews"]');
if(tabBooks)tabBooks.textContent=`Books (${booksCount})`;
if(tabItems)tabItems.textContent=`Other items (${itemsCount})`;
if(tabReviews)tabReviews.textContent=`Review queue (${reviewCount})`;
let data=state.tab==='books'?packet.books:state.tab==='items'?packet.items:packet.review_queue;let list=$('records');list.replaceChildren();if(!data.length){const p=document.createElement('p');p.className='muted';p.textContent='No entries yet.';list.append(p);return}
for(const d of data.slice(-100)){const box=document.createElement('div');box.className='record';const title=document.createElement('strong'),meta=document.createElement('small');if(state.tab==='books'){title.textContent=`${d.excluded?'[Excluded] ':''}${d.title||'Unidentified spine candidate'}`;meta.textContent=`${d.shelf} #${d.position} · ${d.status} · ID confidence ${Math.round(d.id_confidence*100)}% · ${d.spine_height_cm??'?'} × ${d.spine_thickness_cm??'?'} cm`;}
else if(state.tab==='items'){title.textContent=`${d.excluded?'[Excluded] ':''}${d.description}`;meta.textContent=`${d.category} · ${d.status} · ${d.brand_model||'Brand unavailable'}`;}
else{title.textContent=d.ref_id;meta.textContent=d.reason}box.append(title,meta);
if(state.tab!=='reviews'){const evid=document.createElement('button');evid.textContent='View evidence';evid.onclick=()=>download(`/api/sessions/${state.id}/evidence/${d.frame_ref.split('/')[1]}`,'evidence.jpg',true);box.append(evid);const excl=document.createElement('button');excl.textContent='Exclude';excl.onclick=()=>correction('exclude_item',d.id);box.append(excl);if(state.tab==='books'){const first=document.createElement('button');first.textContent='First edition claim';first.onclick=()=>correction('first_edition',d.id);box.append(first)}else if(d.category.includes('artwork')){const pr=document.createElement('button');pr.textContent='This is a print';pr.onclick=()=>correction('art_print',d.id);box.append(pr)}}list.append(box)}}
async function correction(command,ref_id=null,value=null,shelf=null){if(!state.id)return;try{state.packet=await api(`/api/sessions/${state.id}/corrections`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({command,ref_id,value,shelf})});screen();say('Correction preserved: '+command)}catch(e){warning(e)}}
async function runCommand(raw){
    const text=raw.trim(),lower=text.toLowerCase();
    if(!text)return;
    say('You: '+text);
    let item=state.packet?.items.find(i=>i.category.includes('artwork'));
    let lastBook=state.packet?.books.filter(b=>!b.excluded).at(-1);
    if(lower.includes('skip')&&lower.includes('shelf')) {
        await correction('exclude_shelf',null,null,$('shelf').value);
    } else if(lower.includes('first edition')||lower.includes('rare edition')) {
        if(lastBook) await correction('first_edition',lastBook.id);
        else say('No book available to mark; select one from the inventory.');
    } else if((lower.includes('painting')||lower.includes('art'))&&lower.includes('print')) {
        if(item) await correction('art_print',item.id);
        else say('No artwork item active to mark as print.');
    } else if(lower.includes('missed')||lower.includes('bottom shelf')) {
        await correction('missed_shelf');
        speak('Please capture the missed shelf or corner before finishing.');
    } else if(lower.includes('next shelf')) {
        nextShelf();
    } else if(lower.startsWith('title is ') || lower.startsWith('title: ')) {
        const title=text.replace(/^title (?:is|:)\s*/i,'').trim();
        if(lastBook && title) {
            await correction('correct_title',lastBook.id,title);
            say(`Title updated to "${title}". Verification scheduled.`);
        } else say('No book available to update title.');
    } else if(lower.includes('exclude book')||lower.includes('remove book')) {
        if(lastBook) await correction('exclude_item',lastBook.id);
        else say('No book available to exclude.');
    } else {
        say('Noted: "'+text+'". Use item actions to attach corrections to a specific record.');
    }
}
function nextShelf(){const el=$('shelf'),m=el.value.match(/^(.*?)([A-Z])$/);el.value=m?m[1]+String.fromCharCode(Math.min(m[2].charCodeAt(0)+1,90)):'Shelf '+(Date.now()%1000);speak(`Showing ${el.value}. Move slowly across the entire shelf.`)}
async function capture(){if(!state.active||state.paused||state.busy||!state.stream)return;state.busy=true;try{const v=$('camera');if(!v.videoWidth)throw Error('Camera has no frames');const c=document.createElement('canvas'),scale=Math.min(1,1100/v.videoWidth);c.width=Math.round(v.videoWidth*scale);c.height=Math.round(v.videoHeight*scale);c.getContext('2d').drawImage(v,0,0,c.width,c.height);const blob=await new Promise(r=>c.toBlob(r,'image/jpeg',.78));if(!blob)throw Error('Canvas returned no image');let url=`/api/sessions/${state.id}/frames?shelf=${encodeURIComponent($('shelf').value)}`;const cm=Number($('refcm').value),px=Number($('refpx').value);if(cm>0&&px>0)url+=`&reference_cm=${cm}&reference_px=${px}`;const response=await api(url,{method:'POST',headers:{'content-type':'image/jpeg'},body:blob});state.packet=response.packet;screen();const q=response.quality;$('quality').textContent=q.warnings.length?q.warnings.join(' • '):`Frame saved · ${response.new_books} new book candidates`;if(q.warnings.length&&Math.random()<.4)speak(q.warnings[0]);}catch(e){warning(e)}finally{state.busy=false}}
async function refresh(){if(!state.id||state.finished)return;try{state.packet=await api(`/api/sessions/${state.id}`);screen()}catch(e){warning(e)}}
async function start(){try{const health=await api('/api/health');if(!health.remote_vision_enabled) say('Notice: remote visual identification is OFF; local contour detector is limited.');const res=await api('/api/sessions',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({country:$('country').value,currency:$('currency').value,device:navigator.userAgent.slice(0,120)})});state.id=res.id;state.packet=res.packet;state.stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});const v=$('camera');v.srcObject=state.stream;await v.play();state.active=true;state.startMs=Date.now();$('cam-placeholder').hidden=true;$('start').disabled=true;$('pause').disabled=false;$('finish').disabled=false;$('mic').disabled=false;$('save-room').disabled=false;$('country').disabled=true;$('currency').disabled=true;status('Live sweep');screen();state.framesTimer=setInterval(capture,2300);state.pollTimer=setInterval(refresh,3500);state.timer=setInterval(()=>{const sec=Math.floor((Date.now()-state.startMs)/1000);$('clock').textContent=`${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;if(sec===155)speak('Approaching three minutes. Please cover any missed corners and finish when ready.')},1000);speak(`Welcome. Market confirmed: ${$('country').value}, ${$('currency').value}. Walk slowly across all bookshelves, then show the walls, floor, and other belongings. Move closer if a spine is unreadable.`);await capture()}catch(e){warning(e);if(state.stream)state.stream.getTracks().forEach(t=>t.stop());state.active=false;status('Start failed');}}
function togglePause(){state.paused=!state.paused;$('pause').textContent=state.paused?'Resume':'Pause';status(state.paused?'Paused':'Live sweep');if(state.paused)state.recognizer?.stop();else startListening()}
async function finish(){if(!state.id)return;state.active=false;state.voice=false;state.recognizer?.stop();clearInterval(state.framesTimer);clearInterval(state.pollTimer);clearInterval(state.timer);state.stream?.getTracks().forEach(t=>t.stop());$('pause').disabled=true;$('finish').disabled=true;status('Finalizing claim and valuations');speak('Sweep complete. Finishing identification, valuations, evidence checks and claim report.');
const len=$('length').value,wid=$('width').value,hgt=$('height').value;
if(len||wid||hgt){
    try{
        const values={shape:$('shape').value,scale_method:'user_reported_during_sweep'};
        if(len)values.length_m=Number(len);if(wid)values.width_m=Number(wid);if(hgt)values.height_m=Number(hgt);
        if($('shelved-area').value)values.shelved_wall_area_m2=Number($('shelved-area').value);
        await api(`/api/sessions/${state.id}/room`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(values)});
    }catch(e){console.warn('Auto-save room dimensions failed',e);}
}
try{const result=await api(`/api/sessions/${state.id}/finish`,{method:'POST'});state.packet=result.packet;state.finished=true;screen();$('deliveries').hidden=false;status('Claim packet ready');speak(`Claim packet ready. ${state.packet.totals.book_count} detected books, ${state.packet.review_queue.length} review issues. Unknown amounts are excluded.`)}catch(e){warning(e);status('Claim finalization error')}}
async function download(path,name,open=false){try{const resp=await api(path);const data=await resp.blob();const url=URL.createObjectURL(data);if(open){window.open(url,'_blank')}else{const a=document.createElement('a');a.href=url;a.download=name;a.click()}setTimeout(()=>URL.revokeObjectURL(url),30000)}catch(e){warning(e)}}
$('country').onchange=()=>{$('currency').value=regions[$('country').value]};$('start').onclick=start;$('pause').onclick=togglePause;$('finish').onclick=finish;$('mic').onclick=setVoice;$('speak').onclick=()=>speak('Move slowly. Keep book spines in focus, show each shelf from left to right, and capture each wall and corner once.');$('next-shelf').onclick=nextShelf;$('command-form').onsubmit=e=>{e.preventDefault();runCommand($('command').value);$('command').value=''};
for(const el of document.querySelectorAll('[data-tab]'))el.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));el.classList.add('active');state.tab=el.dataset.tab;screen()};
$('save-room').onclick=async()=>{if(!state.id)return;try{const values={shape:$('shape').value,scale_method:'user_reported_during_sweep'};for(const [field,id] of [['length_m','length'],['width_m','width'],['height_m','height'],['shelved_wall_area_m2','shelved-area']])if($(id).value)values[field]=Number($(id).value);await api(`/api/sessions/${state.id}/room`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(values)});await refresh();say('Room observations saved as user-reported, low confidence.')}catch(e){warning(e)}};
function updateLiveRoom(){const l=Number($('length').value),w=Number($('width').value),h=Number($('height').value);if(l>0&&w>0){const fl=Math.round(l*w*100)/100,wl=h>0?Math.round(2*(l+w)*h*100)/100:'?';$('area').textContent=`Calculated floor: ${fl} m²; walls: ${wl} m² (Saved on Finish or click Save)`;}}
['length','width','height','shelved-area','shape'].forEach(id=>{const el=$(id);if(el)el.addEventListener('input',updateLiveRoom);});
$('packet-link').onclick=()=>download(`/api/sessions/${state.id}/packet`,'claim_packet.json');
$('report-link').onclick=()=>download(`/api/sessions/${state.id}/report`,'claim_report.html',true);
$('pdf-link').onclick=()=>download(`/api/sessions/${state.id}/report/pdf`,'claim_report.pdf');
$('archive-link').onclick=()=>download(`/api/sessions/${state.id}/archive`,'claim_with_evidence.zip');
$('delete').onclick=async()=>{if(!state.id||!confirm('Permanently delete this session and all saved evidence?'))return;try{await api(`/api/sessions/${state.id}`,{method:'DELETE'});location.reload()}catch(e){warning(e)}};

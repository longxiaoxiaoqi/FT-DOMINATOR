'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={chips:'M5 5h14v14H5z M9 9h6v6H9z M9 2v3 M15 2v3 M9 19v3 M15 19v3 M2 9h3 M19 9h3 M2 15h3 M19 15h3',factories:'M3 21V9l6 3V6l6 5V3h5v18H3z M7 16h1 M12 16h1 M17 16h1',stocks:'M3 7l9-4 9 4v11l-9 4-9-4V7z M3 7l9 5 9-5 M12 12v10',documents:'M6 3h8l4 4v14H6V3z M14 3v5h4 M9 12h6 M9 16h6',tasks:'M8 4h8v4H8z M8 6H5v15h14V6h-3 M8 14l3 3 5-6',resources:'M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z',users:'M8 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0 M4 22v-3a8 8 0 0 1 16 0v3',audit:'M5 3h14v18H5z M8 7h8 M8 12h8 M8 17h5'};
function icon(k){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[k]||paths.resources}"/></svg>`;}
const labels={chips:'芯片型号',factories:'封装厂',stocks:'库存总览',documents:'图纸中心',tasks:'进度事项',resources:'基础资料',users:'用户管理',audit:'操作记录'};
const roleLabels={admin:'管理员',editor:'编辑人员',viewer:'只读人员'};
const state={user:null,data:{},page:'factories',id:null,tab:'configurations',q:'',kind:'',factory:'',status:'',resource:'',location:'',showInactive:false};
let modalAction=null,toastTimer,modalForm=null;
const factoryList={q:'',activeOnly:false,includeInactive:false};
function formSnapshot(form){return JSON.stringify([...form.elements].filter(e=>e.name&&!['button','submit','reset'].includes(e.type)).map(e=>[e.name,e.type==='file'?[...e.files].map(f=>[f.name,f.size,f.lastModified]):['checkbox','radio'].includes(e.type)?e.checked:e.value]));}
function hasUnsavedChanges(){return !!(modalForm&&$('#dialog').open&&modalForm.form===$('#modal-form')&&formSnapshot(modalForm.form)!==modalForm.baseline);}
function finishModal(){modalForm=null;if($('#dialog').open)$('#dialog').close();}
function closeModal(){
 if(modalForm?.saving){toast('正在保存，请稍候再关闭或离开。');return false;}
 if(hasUnsavedChanges()&&!confirm('表单有尚未保存的修改，确定放弃并离开吗？'))return false;
 finishModal();return true;
}
function rememberForm(form){
 const current={form,baseline:formSnapshot(form),saving:false};modalForm=current;
 // Dependent selectors and stock defaults finish synchronously after modal().
 queueMicrotask(()=>{if(modalForm===current)current.baseline=formSnapshot(form);});
}
window.addEventListener('beforeunload',e=>{if(hasUnsavedChanges()||modalForm?.saving){e.preventDefault();e.returnValue='';}});
$('#dialog').addEventListener('cancel',e=>{e.preventDefault();closeModal();});
$('#dialog').addEventListener('close',()=>{if(!$('#dialog').open)modalForm=null;});
const params=new URLSearchParams(location.hash.slice(1));
let setupKey=params.get('setup')||'';
if(setupKey)history.replaceState(null,'',location.pathname);
const csrf=()=>decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||'');
async function api(url,options={}){
 const headers={'X-CSRFToken':csrf(),...(options.headers||{})};
 if(options.body&&!(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body);}
 const response=await fetch(url,{...options,headers,credentials:'same-origin'});
 let data;try{data=await response.json();}catch{throw Error(response.status===413?'附件总量过大，请分批上传。':response.status===403?'会话校验失败，请刷新后重试。':'服务响应异常，请检查服务是否启动。');}
 if(!response.ok){if(response.status===401&&state.user){if($('#dialog').open&&modalForm)throw Error('登录状态已失效。请保留当前表单，在新标签页登录后重试保存。');state.user=null;finishModal();await boot();}throw Error(data.error||'操作失败');}return data;
}
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4000);}
function get(k,id){return (state.data[k]||[]).find(x=>x.id===Number(id));}
function name(k,id){const r=get(k,id);return r?(r.name||r.title||r.username):'—';}
function res(id){const r=get('resources',id);return r?`${r.name}${r.revision?' · '+r.revision:''}`:'—';}
function ver(id){const v=get('doc_versions',id);return v?`${name('documents',v.document)} · ${v.revision}`:'—';}
function date(v){if(!v)return '—';return v.includes('T')?new Date(v).toLocaleString('zh-CN',{hour12:false}):v;}
function badge(v){const color=['可用','已通过','已完成','已发布','启用'].includes(v)?'green':['验证中','待确认','在途','待验证','待检'].includes(v)?'amber':['已停用','作废','维修中','取消'].includes(v)?'red':'blue';return `<span class="badge ${color}">${esc(v)}</span>`;}
const canEdit=()=>state.user?.role!=='viewer';
function btn(text,action,attrs='',primary=false){return `<button ${primary?'class="primary"':''} data-action="${action}" ${attrs}>${text}</button>`;}
function edit(kind,id){return canEdit()?`<button class="link" data-action="edit" data-kind="${kind}" data-id="${id}">编辑</button>`:'';}
function link(text,action,attrs=''){return `<button class="link" data-action="${action}" ${attrs}>${esc(text)}</button>`;}
function empty(title,text,action=''){return `<div class="empty"><div class="empty-icon">${icon(state.page)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;}
function table(head,rows,emptyText='暂无记录'){if(!rows.length)return empty(emptyText,'录入后，相关资料会显示在这里。');return `<div class="table-wrap"><table><thead><tr>${head.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((v,i)=>`<td data-label="${esc(head[i])}"><div class="cell-value">${v}</div></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function panel(title,content,actions=''){return `<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2><div class="actions">${actions}</div></div>${content}</section>`;}
function currentKind(){if(state.page==='resources'&&state.tab==='locations')return 'locations';if(state.page==='stocks')return ['stocks','transfers','movements'].includes(state.tab)?state.tab:'stocks';if(['factories','chips'].includes(state.page)&&state.id)return state.tab;return state.page;}
function filterQuery(){return new URLSearchParams({q:state.q.trim(),kind:state.kind,factory:state.factory,status:state.status,resource:state.resource,location:state.location,inactive:state.showInactive?'1':'0'}).toString();}
function header(title,sub,actions=''){const kind=currentKind();const exporter=!state.id&&!['users','audit'].includes(kind)?`<a class="export-link" href="/api/export/${kind}?${esc(filterQuery())}">导出筛选结果</a>`:'';return `<div class="page-head"><div><h1>${esc(title)}</h1><p class="subtext">${esc(sub)}</p></div><div class="actions">${exporter}${actions}</div></div>`;}
function newButton(kind,label='新增'){return canEdit()?btn('＋ '+label,'new',`data-kind="${kind}"`,true):'';}
function matches(row){return (state.showInactive||row.active)&&(!state.q.trim()||row.search.includes(state.q.trim().toLowerCase()))&&(!state.kind||row.kind===state.kind)&&(!state.factory||row.factories.includes(Number(state.factory)))&&(!state.status||row.status===state.status)&&(!state.resource||String(row.resource)===state.resource)&&(!state.location||(row.locations||[]).includes(Number(state.location)));}
function filtered(kind){const report=state.data.reports?.[kind];if(!report)return (state.data[kind]||[]).filter(r=>state.showInactive||r.active!==false);const ids=new Set(report.rows.filter(matches).map(r=>r.id));return (state.data[kind]||[]).filter(r=>ids.has(r.id));}
function toolbar(kinds=[]){const kind=currentKind();const rows=state.data.reports?.[kind]?.rows||[];const statuses=[...new Set(rows.map(r=>r.status).filter(Boolean))];const choose=(id,label,items,value)=>`<label class="field"><span>${label}</span><select id="${id}"><option value="">全部</option>${items.map(([v,l])=>`<option value="${esc(v)}" ${String(value)===String(v)?'selected':''}>${esc(l)}</option>`).join('')}</select></label>`;return `<div class="toolbar"><label class="field"><span>搜索关联资料</span><input id="search" placeholder="名称、芯片、资源或负责人" value="${esc(state.q)}"></label>${kinds.length?choose('kind-filter','类型',kinds.map(k=>[k,k]),state.kind):''}${(!state.id||state.page==='chips')&&kind!=='factories'?choose('factory-filter','封装厂',(state.data.factories||[]).map(r=>[r.id,r.name]),state.factory):''}${['stocks','transfers','movements'].includes(kind)?choose('resource-filter','资源型号',(state.data.resources||[]).filter(r=>['LB','Socket','DC线','KIT'].includes(r.kind)).map(r=>[r.id,`${r.kind} · ${res(r.id)}`]),state.resource)+choose('location-filter',kind==='transfers'?'来源或目标地点':'存放地点',(state.data.locations||[]).map(r=>[r.id,r.name]),state.location):''}${statuses.length?choose('status-filter','状态',statuses.map(s=>[s,s]),state.status):''}${!['stocks','transfers','movements'].includes(kind)?`<label class="check-row"><input type="checkbox" id="inactive" ${state.showInactive?'checked':''}>包含停用</label>`:''}${btn('查询','filter', '',true)}${btn('重置','reset')}</div>`;}
function resetFilters(){Object.assign(state,{q:'',kind:'',factory:'',status:'',resource:'',location:'',showInactive:false});}
function navigate(page,id=null){if(!closeModal())return;resetFilters();Object.assign(state,{page,id:id?Number(id):null,tab:page==='stocks'?'stocks':'configurations'});if(page==='factories')Object.assign(factoryList,{q:'',activeOnly:false,includeInactive:!!id&&get('factories',id)?.active===false});render();window.scrollTo(0,0);}
async function refresh(){if(!closeModal())return false;state.data=await api('/api/data');render();return true;}
function render(){
 const title=labels[state.page]||'资源详情';
 $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand"><span class="brand-mark">FT</span><div><strong>资源管理平台</strong><small>TEST RESOURCE CENTER</small></div></div><div class="nav-label">资源工作台</div><nav class="nav">${Object.entries(labels).filter(([k])=>!['users','audit'].includes(k)).map(([k,l])=>`<button data-action="nav" data-page="${k}" class="${state.page===k?'selected':''}">${icon(k)}${l}</button>`).join('')}</nav>${state.user.role==='admin'?`<div class="nav-label">系统管理</div><nav class="nav">${['users','audit'].map(k=>`<button data-action="nav" data-page="${k}" class="${state.page===k?'selected':''}">${icon(k)}${labels[k]}</button>`).join('')}</nav>`:''}<div class="sidebar-bottom"><div class="profile"><span class="avatar">${esc((state.user.name||'用')[0])}</span><div>${esc(state.user.name)}<small>${roleLabels[state.user.role]}</small></div></div>${btn('修改密码','password')}${btn('退出登录','logout')}</div></aside><main class="main"><header class="topbar"><div class="actions">${btn('☰','menu','class="menu-toggle" aria-label="打开导航"')}<span class="crumb">工作台 / <strong>${title}</strong>${state.id&&state.page!=='factories'?' / 详情':''}</span></div><div class="top-actions"><span>共享资料 · 协同维护</span>${btn('刷新','refresh')}</div></header><div class="content" id="content" data-page="${state.page}"></div></main></div>`;
 const renderers={factories:factoriesPage,chips:chipsPage,resources:resourcesPage,stocks:stocksPage,documents:documentsPage,tasks:tasksPage,users:usersPage,audit:auditPage};
 $('#content').innerHTML=renderers[state.page]();
}
function factoryRows(){
 const reports=state.data.reports?.factories?.rows;
 return state.data.factories.filter(f=>(factoryList.includeInactive||f.active)&&(!factoryList.activeOnly||f.active)&&(!factoryList.q.trim()||(reports?.find(r=>r.id===f.id)?.search||[f.name,f.site,f.contact,f.phone].join(' ')).toLowerCase().includes(factoryList.q.trim().toLowerCase())));
}
function factoriesPage(){
 const rows=factoryRows();if(!rows.some(f=>f.id===state.id)){state.id=rows[0]?.id||null;resetFilters();}
 const allCount=state.data.factories.filter(f=>factoryList.includeInactive||f.active).length;
 const enabledCount=state.data.factories.filter(f=>f.active).length;
 const exportQuery=new URLSearchParams({q:factoryList.q.trim(),inactive:factoryList.includeInactive?'1':'0',status:factoryList.activeOnly?'启用':''});
 const pageHead=`<div class="page-head"><div><div class="title-row"><h1>封装厂</h1><span class="record-count">${rows.length} 家</span></div><p class="subtext">选择工厂，连续查阅档案与配套资料</p></div><div class="actions"><a class="export-link" title="按左侧工厂列表的筛选条件导出" href="/api/export/factories?${esc(exportQuery)}">导出筛选结果</a>${newButton('factories','新增封装厂')}</div></div>`;
 const list=`<aside class="factory-list"><div class="factory-list-head"><div class="factory-list-label"><strong>工厂列表</strong><span>${rows.length} 家</span></div><form id="factory-search-form" class="factory-search"><label class="field"><span class="sr-only">搜索封装厂</span><input id="factory-search" value="${esc(factoryList.q)}" placeholder="搜索名称、厂区或联系人"></label><button type="submit" aria-label="查询封装厂">查询</button></form></div><div class="factory-list-tabs"><button data-action="factory-scope" data-scope="all" class="${!factoryList.activeOnly?'selected':''}">全部 ${allCount}</button><button data-action="factory-scope" data-scope="active" class="${factoryList.activeOnly?'selected':''}">启用 ${enabledCount}</button><label><input id="factory-inactive" type="checkbox" ${factoryList.includeInactive?'checked':''}>包含停用</label></div><div class="factory-list-items">${rows.map(f=>{const count=new Set(state.data.configurations.filter(c=>c.factory===f.id&&c.active).map(c=>c.chip)).size;return `<button class="factory-list-item ${f.id===state.id?'selected':''}" data-action="select-factory" data-id="${f.id}" aria-pressed="${f.id===state.id}"><span class="factory-item-title">${icon('factories')}<strong>${esc(f.name)}</strong><span class="factory-state-dot ${f.active?'':'inactive'}" aria-label="${f.active?'启用':'已停用'}"></span></span><span class="factory-item-meta">${esc(f.site||'厂区未填写')} · 关联芯片 ${count}</span></button>`;}).join('')||'<p class="factory-list-empty">没有符合条件的封装厂</p>'}</div><div class="factory-list-footer">已显示 ${rows.length} 家封装厂</div></aside>`;
 return pageHead+`<section class="factory-workbench">${list}<div class="factory-detail">${state.id?factoryDetail():empty(state.data.factories.length?'没有符合条件的工厂':'尚未录入封装厂',state.data.factories.length?'调整搜索条件或勾选包含停用。':'点击右上角新增封装厂，开始建立资料。')}</div></section>`;
}
function tabs(items){return `<div class="tabs">${items.map(([key,l])=>`<button data-action="tab" data-tab="${key}" class="${state.tab===key?'selected':''}">${l}</button>`).join('')}</div>`;}
function configTable(rows,showFactory=false){const resourceLink=id=>id?link(res(id),'resource',`data-id="${id}"`):'—';return table([...(showFactory?['封装厂']:[]),'芯片型号 / 配置','Handler / KIT','测试机','LB','Socket','DC 线','验证状态','操作'],rows.map(c=>[...(showFactory?[link(name('factories',c.factory),'factory',`data-id="${c.factory}"`)]:[]),link(name('chips',c.chip),'chip',`data-id="${c.chip}"`)+`<div class="small muted">${esc(c.name)}</div>`,`<div>${resourceLink(c.handler)}</div><div class="small muted">KIT ${resourceLink(c.kit)}</div>`,resourceLink(c.tester),resourceLink(c.lb),resourceLink(c.socket),resourceLink(c.dc),badge(c.status),link('详情','configuration',`data-id="${c.id}"`)+edit('configurations',c.id)]),'暂无测试配置');}
function factoryDetail(){
 const f=get('factories',state.id);if(!f)return empty('记录不存在','请选择其他工厂。');
 const configs=state.data.configurations.filter(c=>c.factory===f.id);
 const documents=state.data.documents.filter(d=>d.factory===f.id);
 const stocks=state.data.stocks.filter(s=>get('locations',s.location)?.factory===f.id);
 const tasks=state.data.tasks.filter(t=>t.factory===f.id||get('configurations',t.configuration)?.factory===f.id);
 const tools=(rows,kinds=[])=>rows.length?toolbar(kinds):'';
 const add=(kind,label)=>f.active?newButton(kind,label):'';
 let content='';
 if(state.tab==='configurations'){
  const rows=filtered('configurations').filter(c=>c.factory===f.id);
  const body=!configs.length?`<div class="factory-config-empty"><div class="factory-empty-diagram"><span>${icon('factories')}</span><i>→</i><span>${icon('chips')}</span></div><h3>还没有测试配置</h3><p>为这家封装厂关联芯片、设备与配套资源。</p>${btn('查看芯片型号 →','nav','data-page="chips"')}</div>`:tools(configs)+configTable(rows);
  content=panel('芯片型号与测试配置',body,add('configurations','测试配置'));
 }
 if(state.tab==='documents')content=panel('工厂级 LB 规范',tools(documents)+docsTable(filtered('documents').filter(d=>d.factory===f.id)),add('documents','LB 规范'));
 if(state.tab==='stocks')content=panel('工厂库存',tools(stocks,['LB','Socket','DC线','KIT'])+stockTable(filtered('stocks').filter(s=>get('locations',s.location)?.factory===f.id)),add('locations','存放地点'));
 if(state.tab==='tasks')content=panel('工厂进度',tools(tasks)+taskTable(filtered('tasks').filter(t=>t.factory===f.id||get('configurations',t.configuration)?.factory===f.id)),add('tasks','事项'));
 return `<div class="factory-detail-heading"><div class="factory-detail-name"><span class="factory-symbol">${icon('factories')}</span><div><div class="title-row"><h2>${esc(f.name)}</h2>${badge(f.active?'启用':'已停用')}</div><p class="subtext">工厂档案与配套资料</p></div></div>${canEdit()?btn('编辑资料','edit',`data-kind="factories" data-id="${f.id}"`):''}</div><div class="factory-detail-meta"><div><small>厂区</small>${esc(f.site||'未填写')}</div><div><small>联系人</small>${esc(f.contact||'未填写')}</div><div><small>联系方式</small>${esc(f.phone||'未填写')}</div></div>${f.note?`<p class="factory-note">${esc(f.note)}</p>`:''}`+tabs([['configurations',`芯片与配置 <span class="tab-count">${new Set(configs.filter(c=>c.active).map(c=>c.chip)).size}</span>`],['documents','LB 规范'],['stocks','工厂库存'],['tasks','进度事项']])+`<div class="factory-detail-content">${content}</div><p class="factory-detail-footer">同一芯片可以关联不同封装厂，每家工厂可建立多套测试配置。</p>`;
}
function chipsPage(){
 if(state.id)return chipDetail();
 return header('芯片型号','跨封装厂查阅同一芯片的配套资源',newButton('chips','芯片型号'))+panel('芯片档案',toolbar()+table(['芯片型号','封装形式','尺寸','Pin 数','配置数量','状态','操作'],filtered('chips').map(c=>[link(c.name,'chip',`data-id="${c.id}"`),esc(c.package||'—'),esc(c.dimensions||'—'),c.pins??'—',state.data.configurations.filter(x=>x.chip===c.id&&x.active).length,badge(c.active?'启用':'已停用'),edit('chips',c.id)]),'尚未录入芯片型号'));
}
function chipDetail(){
 const c=get('chips',state.id);if(!c)return empty('芯片不存在','请返回列表。');
 const configs=state.data.configurations.filter(x=>x.chip===c.id&&(state.showInactive||x.active)&&(!state.factory||x.factory===Number(state.factory)));
 const resourceIds=new Set(configs.flatMap(x=>['handler','kit','tester','lb','socket','dc'].map(k=>x[k])).filter(Boolean));
 const versionIds=new Set(configs.flatMap(x=>['norm','lb_drawing','socket_drawing','pin_drawing'].map(k=>x[k])).filter(Boolean));
 const documentIds=new Set(state.data.doc_versions.filter(v=>versionIds.has(v.id)).map(v=>v.document));
 let content='';
 if(state.tab==='configurations')content=panel('跨工厂测试配置',toolbar()+configTable(filtered('configurations').filter(x=>x.chip===c.id),true),newButton('configurations','测试配置'));
 if(state.tab==='resources')content=panel('配套资源',toolbar(['LB','Socket','DC线','KIT','测试机','Handler','Pin针'])+table(['类型','型号 / 版本','单位','状态','操作'],filtered('resources').filter(r=>resourceIds.has(r.id)).map(r=>[badge(r.kind),link(res(r.id),'resource',`data-id="${r.id}"`),esc(r.unit),badge(r.active?'启用':'已停用'),edit('resources',r.id)]),'尚无关联资源'));
 if(state.tab==='documents')content=panel('关联图纸与配置采用的规范',toolbar(['LB规范','LB图纸','Socket图纸','Pin针图纸'])+docsTable(filtered('documents').filter(d=>resourceIds.has(d.resource)||documentIds.has(d.id))))+`<p class="footer-note">图纸按配套资源关联，规范按配置实际引用关联；历史版本仍以配置详情为准。</p>`;
 if(state.tab==='tasks')content=panel('芯片进度',toolbar()+taskTable(filtered('tasks').filter(t=>t.chip===c.id||get('configurations',t.configuration)?.chip===c.id)),newButton('tasks','事项'));
 const factories=[...new Set(configs.map(x=>x.factory))];
 return header(c.name,`${c.package||'封装待填写'} · ${c.pins?c.pins+' Pins':'Pin 数待填写'}`,btn('返回芯片列表','nav','data-page="chips"')+edit('chips',c.id))+panel('关联工厂',`<div class="panel-body inline-list">${factories.map(id=>link(name('factories',id),'factory',`data-id="${id}"`)).join('')||'<span class="muted">建立测试配置后显示关联工厂</span>'}</div>`)+tabs([['configurations','测试配置'],['resources','配套资源'],['documents','图纸与规范'],['tasks','进度事项']])+content+(state.tab==='resources'?`<p class="footer-note">同一共用资源只显示一份档案；各地点库存请进入资源详情查看，不按配置重复累计。</p>`:'');
}
function resourcesPage(){
 if(state.id)return resourceDetail();
 const isLocations=state.tab==='locations';
 return header('基础资料','先建立资源型号与地点，再关联到芯片测试配置',newButton(isLocations?'locations':'resources',isLocations?'地点':'资源型号'))+tabs([['configurations','资源型号'],['locations','存放地点']])+panel(isLocations?'存放地点':'资源型号库',toolbar(isLocations?[]:['LB','Socket','DC线','KIT','测试机','Handler','Pin针'])+(isLocations?table(['地点','所属封装厂','备注','状态','操作'],filtered('locations').map(l=>[esc(l.name),esc(name('factories',l.factory)),esc(l.note||'—'),badge(l.active?'启用':'已停用'),edit('locations',l.id)])):table(['类型','型号','版本','单位','规格','状态','操作'],filtered('resources').filter(r=>!state.kind||r.kind===state.kind).map(r=>[badge(r.kind),link(r.name,'resource',`data-id="${r.id}"`),esc(r.revision||'未填写'),esc(r.unit),esc(r.spec||'—'),badge(r.active?'启用':'已停用'),edit('resources',r.id)]),'尚未建立资源型号')));
}
function resourceDetail(){const r=get('resources',state.id);if(!r)return empty('资源不存在','请返回列表。');return header(r.name,`${r.kind} · ${r.revision||'版本待填写'} · ${r.unit}`,btn('返回资源库','nav','data-page="resources"')+edit('resources',r.id))+panel('规格资料',`<div class="panel-body"><p>${esc(r.spec||'暂无规格说明')}</p><p class="subtext">${esc(r.note)}</p></div>`)+panel('各地点库存',stockTable(state.data.stocks.filter(s=>s.resource===r.id)))+panel('关联图纸',docsTable(state.data.documents.filter(d=>d.resource===r.id&&d.active)),r.active&&['LB','Socket','Pin针'].includes(r.kind)?newButton('documents','图纸档案'):'')+panel('关联测试配置',configTable(state.data.configurations.filter(c=>c.active&&['handler','kit','tester','lb','socket','dc'].some(k=>c[k]===r.id)),true))+panel('资源进度事项',taskTable(state.data.tasks.filter(t=>t.active&&t.resource===r.id)),canEdit()&&r.active?newButton('tasks','事项'):'');}
function stockTable(rows){return table(['资源类型','型号 / 版本','地点','状态','数量','单位',...(canEdit()?['操作']:[])],rows.map(s=>[esc(get('resources',s.resource)?.kind||''),link(res(s.resource),'resource',`data-id="${s.resource}"`),esc(name('locations',s.location)),badge(s.state),s.qty,esc(get('resources',s.resource)?.unit),...(canEdit()?[get('resources',s.resource)?.active&&get('locations',s.location)?.active?['transfer','state','count','scrap'].map((op,i)=>link(['调拨','状态调整','盘点','报废'][i],'stock-row',`data-id="${s.id}" data-op="${op}"`)).join(' '):'<span class="muted">关联档案已停用</span>']:[])]),'尚无库存记录');}
function stocksPage(){
 const ts=state.data.transfers;const metrics=[['有库存型号',new Set(state.data.stocks.filter(s=>s.qty>0).map(s=>s.resource)).size,'种'],['库存地点',new Set(state.data.stocks.filter(s=>s.qty>0).map(s=>s.location)).size,'处'],['未收完调拨',ts.filter(t=>t.received<t.qty).length,'单'],['库存流水',state.data.movements.length,'条']];
 let content='';
 const actions=canEdit()?['入库','调拨发出','状态调整','盘点','报废'].map((x,i)=>btn(x,'stock',`data-op="${['in','transfer','state','count','scrap'][i]}"`,i===0)).join(''):'';
 if(state.tab==='stocks')content=panel('分地点库存',toolbar(['LB','Socket','DC线','KIT'])+stockTable(filtered('stocks')));
 if(state.tab==='transfers')content=panel('调拨与签收',toolbar(['LB','Socket','DC线','KIT'])+table(['单号','资源','来源 → 目标','发出','已签收','在途','状态','操作'],filtered('transfers').map(t=>[link(`TR-${String(t.id).padStart(5,'0')}`,'transfer-detail',`data-id="${t.id}"`),esc(res(t.resource)),`${esc(name('locations',t.source))} → ${esc(name('locations',t.target))}`,t.qty,t.received,t.qty-t.received,badge(t.received===t.qty?'已完成':'在途'),canEdit()&&t.received<t.qty?btn('登记签收','receive',`data-id="${t.id}"`):'—'])));
 if(state.tab==='movements')content=panel('库存流水',toolbar(['LB','Socket','DC线','KIT'])+movementTable(filtered('movements')));
 return header('库存总览','库存按资源型号统计，共用资源不按芯片重复累计',actions)+`<div class="metrics">${metrics.map(([l,n,u])=>`<div class="metric"><span>${l}</span><strong>${n}<small>${u}</small></strong></div>`).join('')}</div>`+tabs([['stocks','库存余额'],['transfers','调拨与签收'],['movements','库存流水']])+content+`<p class="footer-note">不同单位的资源分别计量；测试机、Handler 和 Pin 针仅管理资料。</p>`;
}
function movementTable(rows){return table(['时间','资源','地点','状态','操作','数量变更','操作人','原因','关联调拨单'],rows.map(m=>[esc(date(m.created_at)),link(res(m.resource),'resource',`data-id="${m.resource}"`),esc(name('locations',m.location)),badge(m.state),esc(m.kind),`${m.delta>0?'+':''}${m.delta}`,esc(name('users',m.created_by)),esc(m.note),m.transfer?link(`TR-${String(m.transfer).padStart(5,'0')}`,'transfer-detail',`data-id="${m.transfer}"`):'—']),'尚无库存流水');}
function transferDetail(id){
 const t=get('transfers',id);if(!t)return toast('调拨单不存在，请刷新资料。');
 if(!closeModal())return;
 const unit=get('resources',t.resource)?.unit||'';
 const values=[['资源',link(res(t.resource),'resource',`data-id="${t.resource}"`)],['来源地点',esc(name('locations',t.source))],['目标地点',esc(name('locations',t.target))],['库存状态',badge(t.state)],['发出数量',`${t.qty} ${esc(unit)}`],['已签收',`${t.received} ${esc(unit)}`],['剩余在途',`${t.qty-t.received} ${esc(unit)}`],['签收状态',badge(t.received===t.qty?'已完成':'在途')],['发出人',esc(name('users',t.created_by))],['发出时间',esc(date(t.created_at))],['发出说明',esc(t.note||'—')]];
 $('#dialog-content').innerHTML=`<div class="dialog-head"><h2>调拨单 TR-${String(t.id).padStart(5,'0')}</h2>${btn('×','close')}</div><div class="panel-body detail-grid">${values.map(([k,v])=>`<div><small>${k}</small>${v}</div>`).join('')}</div>${panel('发出与分批签收记录',movementTable(state.data.movements.filter(m=>m.transfer===t.id)))}<div class="dialog-foot">${canEdit()&&t.received<t.qty?btn('登记签收','receive',`data-id="${t.id}"`,true):''}${btn('关闭','close')}</div>`;
 if(!$('#dialog').open)$('#dialog').showModal();
}
function docsTable(rows){return table(['文档名称','类别','归属','版本数量','适用范围','操作'],rows.map(d=>[link(d.name,'document',`data-id="${d.id}"`),badge(d.kind),esc(d.factory?name('factories',d.factory):res(d.resource)),state.data.doc_versions.filter(v=>v.document===d.id).length,esc(d.scope||'—'),link('版本与附件','document',`data-id="${d.id}"`)+edit('documents',d.id)]),'尚无图纸或规范');}
function fileLinks(files,kind){return files.map(f=>`<span>${esc(f.original_name)} <a href="/api/files/${kind}/${f.id}" target="_blank" rel="noopener">下载</a>${['application/pdf','image/png','image/jpeg','image/webp'].includes(f.content_type)?` · <a href="/api/files/${kind}/${f.id}?preview=1" target="_blank" rel="noopener">预览</a>`:''}</span>`).join('');}
function documentsPage(){
 if(state.id){const d=get('documents',state.id);if(!d)return empty('文档不存在','请返回列表。');return header(d.name,`${d.kind} · ${d.factory?name('factories',d.factory):res(d.resource)}`,btn('返回图纸中心','nav','data-page="documents"')+(canEdit()&&d.active?btn('＋ 上传新版本','upload-version',`data-id="${d.id}"`,true):''))+`<p class="notice">上传新版本会保留旧版附件。测试配置仍引用原来选择的版本。</p>`+panel('版本与附件',table(['版本','状态','变更说明','上传人 / 时间','附件','操作'],state.data.doc_versions.filter(v=>v.document===d.id).map(v=>[esc(v.revision),badge(v.status),esc(v.change_note||'—'),`${esc(name('users',v.created_by))}<div class="small muted">${esc(date(v.created_at))}</div>`,`<div class="file-links">${fileLinks(state.data.attachments.filter(a=>a.doc_version===v.id),'document')}</div>`,canEdit()?(v.status==='草稿'?btn('发布','version-status',`data-id="${v.id}" data-status="已发布"`):'')+(v.status!=='作废'?btn('作废','version-status',`data-id="${v.id}" data-status="作废"`):'—'):'—'])));}
 return header('图纸中心','集中维护 LB、Socket、Pin 针图纸与工厂 LB 规范',newButton('documents','文档档案'))+panel('图纸与规范',toolbar(['LB规范','LB图纸','Socket图纸','Pin针图纸'])+docsTable(filtered('documents').filter(d=>!state.kind||d.kind===state.kind)));
}
function taskContext(t){const c=get('configurations',t.configuration);return {factory:t.factory||c?.factory,chip:t.chip||c?.chip};}
function taskTable(rows){return table(['事项','类别','关联信息','负责人','计划完成','状态','操作'],rows.map(t=>{const context=taskContext(t);return [link(t.title,'task',`data-id="${t.id}"`),esc(t.category),esc([context.factory?name('factories',context.factory):'',context.chip?name('chips',context.chip):'',t.resource?res(t.resource):'',t.configuration?name('configurations',t.configuration):''].filter(Boolean).join(' / ')||'—'),esc(name('users',t.owner)),esc(t.due_date||'未设置'),badge(t.status),edit('tasks',t.id)+(canEdit()&&t.active?link('更新进度','progress',`data-id="${t.id}"`):'')];}))}

function taskAssociation(t){const context=taskContext(t);const items=[['封装厂',context.factory,'factories','factory'],['芯片型号',context.chip,'chips','chip'],['资源',t.resource,'resources','resource'],['测试配置',t.configuration,'configurations','configuration']].filter(([,id])=>id);return `<div class="panel-body inline-list">${items.map(([label,id,kind,action])=>link(`${label}：${kind==='resources'?res(id):name(kind,id)}`,action,`data-id="${id}"`)).join('')||'<span class="muted">未关联档案</span>'}</div>`;}
function tasksPage(){
 if(state.id){const t=get('tasks',state.id);if(!t)return empty('事项不存在','请返回列表。');return header(t.title,`${t.category} · 负责人 ${name('users',t.owner)} · 计划 ${t.due_date||'未设置'}`,btn('返回事项列表','nav','data-page="tasks"')+edit('tasks',t.id)+(canEdit()&&t.active?btn('更新进度','progress',`data-id="${t.id}"`,true):''))+panel('关联资料',taskAssociation(t))+panel('事项说明',`<div class="panel-body">${badge(t.status)}<p>${esc(t.note||'暂无说明')}</p></div>`)+panel('进展时间线',`<div class="panel-body"><ol class="timeline">${state.data.task_updates.filter(u=>u.task===t.id).map(u=>`<li>${badge(u.status)} <span class="small muted">${esc(name('users',u.created_by))} · ${esc(date(u.created_at))}</span><p>${esc(u.text)}</p><div class="file-links">${fileLinks(state.data.task_attachments.filter(a=>a.update===u.id),'task')}</div></li>`).join('')}</ol></div>`);}
 return header('进度事项','记录制作、采购、维修和验证的每次进展',newButton('tasks','事项'))+panel('事项列表',toolbar(['制作','采购','图纸修改','维修','验证','调拨跟进'])+taskTable(filtered('tasks').filter(t=>!state.kind||t.category===state.kind)));
}
function usersPage(){return header('用户管理','内部账号与访问权限',newButton('users','用户'))+panel('内部用户',table(['账号','姓名','角色','状态','操作'],state.data.users.map(u=>[esc(u.username),esc(u.name),roleLabels[u.role],badge(u.active?'启用':'已停用'),edit('users',u.id)])));}
function auditPage(){return header('操作记录','最近 300 条关键操作记录')+panel('操作历史',table(['时间','操作人','操作','对象','记录编号'],(state.data.audit||[]).map(a=>[esc(date(a.created_at)),esc(name('users',a.actor)),esc(a.action),esc(a.entity),a.object_id??'—'])));}

const f=(key,label,type='text',options={})=>({key,label,type,...options});
const schemas={
 factories:[f('name','封装厂名称','text',{required:true}),f('site','厂区'),f('contact','联系人'),f('phone','联系方式'),f('note','备注','textarea')],
 chips:[f('name','芯片型号','text',{required:true}),f('package','封装形式'),f('dimensions','尺寸'),f('pins','Pin 数','number'),f('note','备注','textarea')],
 locations:[f('name','地点名称','text',{required:true}),f('factory','所属封装厂','ref',{ref:'factories'}),f('note','备注','textarea')],
 resources:[f('kind','资源类型','select',{values:['LB','Socket','DC线','KIT','测试机','Handler','Pin针'],required:true}),f('name','型号','text',{required:true}),f('revision','设计版本'),f('unit','单位','text',{required:true,default:'件'}),f('spec','规格说明','textarea'),f('note','备注','textarea')],
 configurations:[f('name','配置名称','text',{required:true}),f('factory','封装厂','ref',{ref:'factories',required:true}),f('chip','芯片型号','ref',{ref:'chips',required:true}),...Object.entries({handler:'Handler',kit:'KIT',tester:'测试机',lb:'LB',socket:'Socket',dc:'DC线'}).map(([key,label])=>f(key,label,'ref',{ref:'resources',kind:label})),f('norm','LB 规范版本','ref',{ref:'doc_versions',docKind:'LB规范'}),f('lb_drawing','LB 图纸版本','ref',{ref:'doc_versions',docKind:'LB图纸'}),f('socket_drawing','Socket 图纸版本','ref',{ref:'doc_versions',docKind:'Socket图纸'}),f('pin_drawing','Pin 针图纸版本','ref',{ref:'doc_versions',docKind:'Pin针图纸'}),f('status','验证状态','select',{values:['待补全','待验证','验证中','已通过','停用']}),f('note','备注','textarea')],
 documents:[f('name','文档名称','text',{required:true}),f('kind','类别','select',{values:['LB规范','LB图纸','Socket图纸','Pin针图纸'],required:true}),f('factory','所属封装厂（LB 规范）','ref',{ref:'factories'}),f('resource','所属资源（图纸）','ref',{ref:'resources'}),f('scope','适用范围'),f('note','备注','textarea')],
 tasks:[f('title','事项标题','text',{required:true}),f('category','类别','select',{values:['制作','采购','图纸修改','维修','验证','调拨跟进']}),f('factory','关联封装厂','ref',{ref:'factories'}),f('chip','关联芯片','ref',{ref:'chips'}),f('resource','关联资源','ref',{ref:'resources'}),f('configuration','关联测试配置','ref',{ref:'configurations'}),f('owner','负责人','ref',{ref:'users'}),f('status','状态','select',{values:['待开始','进行中','待确认','已完成','暂停','取消']}),f('due_date','计划完成日期','date'),f('note','说明','textarea')],
 users:[f('username','账号','text',{required:true}),f('name','姓名'),f('role','角色','select',{values:[['viewer','只读人员'],['editor','编辑人员'],['admin','管理员']]}),f('password','密码（编辑时留空则不更改）','password')]
};
function options(field,selected){
 let list=field.values?.map(v=>Array.isArray(v)?v:[v,v])||[];
 if(field.ref)list=(state.data[field.ref]||[]).filter(r=>(r.active!==false||r.id===Number(selected))&&(!field.kind||r.kind===field.kind)&&(!field.docKind||get('documents',r.document)?.kind===field.docKind)&&(field.ref!=='doc_versions'||r.status!=='作废'||r.id===Number(selected))).map(r=>[r.id,field.ref==='resources'?`${r.kind} · ${res(r.id)}`:field.ref==='doc_versions'?`${ver(r.id)} (${r.status})`:field.ref==='configurations'?`${name('factories',r.factory)} / ${name('chips',r.chip)} / ${r.name}`:r.name||r.username]);
 return `${field.ref?'<option value="">请选择（可稍后补充）</option>':''}${list.map(([v,l])=>`<option value="${esc(v)}" ${String(selected)===String(v)?'selected':''}>${esc(l)}</option>`).join('')}`;
}
function fieldHTML(field,data={}){
 const value=data[field.key]??field.default??'';const attr=`name="${field.key}" ${field.required?'required':''}`;
 let control;
 if(['select','ref'].includes(field.type))control=`<select ${attr}>${options(field,value)}</select>`;
 else if(field.type==='textarea')control=`<textarea ${attr} maxlength="5000">${esc(value)}</textarea>`;
 else if(field.type==='file')control=`<input ${attr} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.dwg,.dxf,.step,.stp,.zip,.xlsx,.xls,.docx,.txt">`;
 else control=`<input ${attr} type="${field.type}" value="${esc(value)}" ${field.type==='number'?'min="0" step="1" max="1000000000"':''} ${field.type==='password'?'autocomplete="new-password"':'maxlength="200"'}>`;
 return `<label class="field ${['textarea','file'].includes(field.type)?'wide':''}"><span>${esc(field.label)}${field.required?' *':''}</span>${control}</label>`;
}
function modal(title,fields,data,submit,extra=''){
 if(!closeModal())return false;
 modalAction=submit;$('#dialog-content').innerHTML=`<div class="dialog-head"><h2>${esc(title)}</h2><button data-action="close" aria-label="关闭">×</button></div><form id="modal-form"><div class="form-grid">${extra?`<div class="wide tip">${extra}</div>`:''}${fields.map(x=>fieldHTML(x,data)).join('')}<div class="form-error wide" id="modal-error" role="alert"></div></div><div class="dialog-foot">${btn('取消','close')}<button class="primary" type="submit">保存</button></div></form>`;
 if(!$('#dialog').open)$('#dialog').showModal();
 const form=$('#modal-form');rememberForm(form);
 form.addEventListener('submit',async e=>{
  e.preventDefault();if(modalForm?.saving)return;
  const current=modalForm,b=e.submitter||form.querySelector('[type=submit]');current.saving=true;b.disabled=true;form.querySelector('#modal-error').textContent='';
  try{
   await submit(new FormData(form));finishModal();
   try{await refresh();toast('已保存');}catch{toast('已保存，但列表刷新失败，请稍后刷新资料。');}
  }catch(err){form.querySelector('#modal-error').textContent=err.message;}
  finally{current.saving=false;b.disabled=false;}
 });
 return true;
}
function openRecord(kind,id=null,prefill={}){
 const data=id?{...get(kind,id)}:{};if(!schemas[kind])return;
 if(!id&&state.id){if(state.page==='factories')data.factory=state.id;if(state.page==='chips')data.chip=state.id;if(state.page==='resources')data.resource=state.id;}
 if(!id)Object.assign(data,prefill);
 if(kind==='documents'&&!id&&state.page==='factories')data.kind='LB规范';
 if(kind==='documents'&&!id&&state.page==='resources'){const r=get('resources',state.id);data.kind=r?.kind==='Socket'?'Socket图纸':r?.kind==='Pin针'?'Pin针图纸':'LB图纸';}
 const fields=[...schemas[kind]];
 if(id)fields.push(f('active','启用状态','select',{values:[['true','启用'],['false','停用']]}));
 const title=`${id?'编辑':'新增'}${{factories:'封装厂',chips:'芯片型号',resources:'资源型号',locations:'地点',documents:'文档档案',configurations:'测试配置',tasks:'事项',users:'用户'}[kind]}`;
 if(!modal(title,fields,data,async form=>{
  const payload=Object.fromEntries(form);
  for(const field of fields){if(field.type==='ref')payload[field.key]=payload[field.key]?Number(payload[field.key]):null;if(field.type==='number')payload[field.key]=payload[field.key]===''?null:Number(payload[field.key]);}
  if(id){payload.version=data.version;payload.active=payload.active==='true';}
  await api(`/api/${kind==='users'?'users':'records/'+kind}${id?'/'+id:''}`,{method:id?'PUT':'POST',body:payload});
 },kind==='configurations'?'可先保存“待补全”配置，再逐步关联设备和资源。关联资源前须先在基础资料中录入型号。':kind==='documents'?'LB 规范选择封装厂；图纸选择资源。档案保存后，进入详情上传文件版本。':''))return;
 bindRelations(kind,data);
}
function bindRelations(kind,original){
 const form=$('#modal-form');
 if(!['configurations','documents','tasks'].includes(kind))return;
 const control=k=>form.elements.namedItem(k);
 const value=k=>Number(control(k)?.value)||null;
 const message=document.createElement('div');message.className='wide tip';message.setAttribute('role','status');message.id='relation-note';
 form.querySelector('.form-grid').insertBefore(message,$('#modal-error'));
 const changed=new Set();
 const label=k=>schemas[kind].find(f=>f.key===k)?.label||k;
 function clear(k){const e=control(k);if(e?.value){e.value='';changed.add(label(k));}}
 function rebuild(k,predicate,hint,enabled=true){
  const field=schemas[kind].find(f=>f.key===k);const el=control(k);const before=el.value;
  const candidates=(state.data[field.ref]||[]).filter(r=>{
   const historical=r.id===Number(original[k]);
   if(r.active===false&&!historical)return false;
   if(field.kind&&r.kind!==field.kind)return false;
   if(field.docKind&&get('documents',r.document)?.kind!==field.docKind)return false;
   if(field.ref==='doc_versions'&&(r.status==='作废'||get('documents',r.document)?.active===false)&&!historical)return false;
   return predicate(r);
  });
  const optionLabel=r=>field.ref==='doc_versions'?`${ver(r.id)} (${r.status})`:field.ref==='resources'?`${r.kind} · ${res(r.id)}`:field.ref==='configurations'?`${name('factories',r.factory)} / ${name('chips',r.chip)} / ${r.name}`:r.name||r.username;
  el.innerHTML=`<option value="">${esc(hint)}</option>`+candidates.map(r=>`<option value="${r.id}">${esc(optionLabel(r))}${r.active===false?'（已停用，仅保留历史引用）':''}</option>`).join('');
  el.disabled=!enabled;
  if(enabled&&candidates.some(r=>String(r.id)===before))el.value=before;
  else if(before)changed.add(label(k));
 }
 function sync(trigger=''){
  changed.clear();
  if(kind==='configurations'){
   if(trigger==='handler')clear('kit');
   if(trigger==='tester')for(const k of ['lb','socket','dc','lb_drawing','socket_drawing','pin_drawing'])clear(k);
   rebuild('kit',()=>true,value('handler')?'选择 KIT（可稍后补充）':'请先选择 Handler',!!value('handler'));
   for(const k of ['lb','socket','dc'])rebuild(k,()=>true,value('tester')?'选择资源（可稍后补充）':'请先选择测试机',!!value('tester'));
   for(const [key,parent,field] of [['norm','factory','factory'],['lb_drawing','lb','resource'],['socket_drawing','socket','resource'],['pin_drawing','socket','resource']]){
    const selected=value(parent);
    rebuild(key,r=>get('documents',r.document)?.[field]===selected,selected?'选择匹配版本（不自动替换）':`请先选择${label(parent)}`,!!selected);
   }
  }
  if(kind==='documents'){
   const docKind=control('kind').value;const isNorm=docKind==='LB规范';
   control('factory').closest('label').hidden=!isNorm;control('factory').disabled=!isNorm;
   control('resource').closest('label').hidden=isNorm;control('resource').disabled=isNorm;
   if(isNorm)clear('resource');else clear('factory');
   if(!isNorm){const allowed={'LB图纸':['LB'],'Socket图纸':['Socket'],'Pin针图纸':['Socket','Pin针']}[docKind]||[];rebuild('resource',r=>allowed.includes(r.kind),'选择图纸对应的资源',true);}
  }
  if(kind==='tasks'){
   if(trigger==='configuration'&&value('configuration')){
    const c=get('configurations',value('configuration'));
    control('factory').value=String(c.factory);control('chip').value=String(c.chip);
   }
   rebuild('configuration',r=>(r.id===Number(original.configuration)||(get('factories',r.factory)?.active!==false&&get('chips',r.chip)?.active!==false))&&(!value('factory')||r.factory===value('factory'))&&(!value('chip')||r.chip===value('chip')),'选择匹配的测试配置');
  }
  message.textContent=changed.size?`已清除当前表单中不再适用的选择：${[...changed].join('、')}。保存后才会修改记录。`:kind==='configurations'?'图纸与规范按归属筛选；资源列表按类型筛选，不代表设备兼容性已经验证。历史版本不会自动升级。':kind==='documents'?'先建立档案，保存后进入详情上传文件版本。':'选择测试配置后，会带入其工厂和芯片；也可保留独立事项。';
 }
 form.addEventListener('change',e=>{if(e.target.tagName==='SELECT')sync(e.target.name);});
 sync();
}
function stockForm(op,prefill={}){
 const labels={in:'登记入库',transfer:'调拨发出',state:'调整库存状态',count:'盘点库存',scrap:'登记报废'};
 const fields=[f('resource','资源型号','ref',{ref:'resources',required:true}),f('location','来源 / 当前地点','ref',{ref:'locations',required:true}),f('state','当前状态','select',{values:['可用','使用中','维修中','待检']})];
 if(op==='transfer')fields.push(f('target','目标地点','ref',{ref:'locations',required:true}));
 if(op==='state')fields.push(f('target_state','目标状态','select',{values:['可用','使用中','维修中','待检']}));
 fields.push(f('qty',op==='count'?'实盘数量':'操作数量','number',{required:true}),f('note','原因 / 说明','textarea',{required:true}));
 const key=crypto.randomUUID(); const stockSnapshot=structuredClone(state.data.stocks);
 if(!modal(labels[op],fields,prefill,async form=>{const data=Object.fromEntries(form);for(const x of ['resource','location','target'])if(data[x])data[x]=Number(data[x]);data.qty=Number(data.qty);data.operation=op;data.key=key;
  if(op==='count')data.expected=stockSnapshot.find(s=>s.resource===data.resource&&s.location===data.location&&s.state===data.state)?.qty||0;
  await api('/api/inventory',{method:'POST',body:data});
 },op==='transfer'?'发出后减少来源库存，数量进入在途。到货后请在“调拨与签收”登记签收。':'仅 LB、Socket、DC 线和 KIT 支持数量操作，单位以资源型号为准。'))return;
 const select=$('#modal-form select[name="resource"]');for(const option of [...select.options])if(option.value&&!['LB','Socket','DC线','KIT'].includes(get('resources',option.value)?.kind))option.remove();
 const form=$('#modal-form');const hint=document.createElement('div');hint.className='wide tip';hint.id='stock-balance';form.querySelector('.form-grid').insertBefore(hint,form.querySelector('#modal-error'));
 function updateBalance(){const resource=Number(form.elements.resource.value),location=Number(form.elements.location.value),current=form.elements.state.value;const qty=stockSnapshot.find(s=>s.resource===resource&&s.location===location&&s.state===current)?.qty||0;hint.textContent=resource&&location?`当前账面库存：${qty} ${get('resources',resource)?.unit||''}（${current}）。保存时仍会校验库存及盘点冲突。`:'选择资源和地点后显示账面库存。';if(op==='count'&&resource&&location)form.elements.qty.value=qty;}
 form.addEventListener('change',e=>{if(['resource','location','state'].includes(e.target.name)){if(op!=='count')form.elements.qty.value='';updateBalance();}});updateBalance();
}
function receiveForm(id){const t=get('transfers',id);const key=crypto.randomUUID();modal('登记签收',[f('qty','本次签收数量','number',{required:true}),f('note','收货说明','textarea',{required:true})],{qty:t.qty-t.received},form=>api('/api/inventory',{method:'POST',body:{operation:'receive',transfer:id,qty:Number(form.get('qty')),note:form.get('note'),key}}),`${esc(res(t.resource))} · 目标 ${esc(name('locations',t.target))} · 剩余 ${t.qty-t.received} ${esc(get('resources',t.resource)?.unit)}`);}
function uploadForm(id){modal('上传文档新版本',[f('revision','版本号','text',{required:true}),f('status','状态','select',{values:['草稿','已发布']}),f('change_note','变更说明','textarea'),f('files','附件（单个不超过 30 MB）','file',{required:true})],{},form=>{form.set('document',id);return api('/api/versions',{method:'POST',body:form});},'同一档案的版本号不能重复；旧附件不会被覆盖。');}
function progressForm(id){const t=get('tasks',id);modal('更新进度',[f('status','当前状态','select',{values:['待开始','进行中','待确认','已完成','暂停','取消']}),f('text','本次进展','textarea',{required:true}),f('files','照片 / 附件','file')],t,form=>{form.set('version',t.version);return api(`/api/tasks/${id}/updates`,{method:'POST',body:form});});}
function versionDetail(id){
 const v=get('doc_versions',id);if(!v)return toast('版本不存在，请刷新资料后重试。');
 const d=get('documents',v.document);if(!d)return toast('文档不存在，请刷新资料后重试。');
 if(!closeModal())return;
 const files=state.data.attachments.filter(a=>a.doc_version===v.id);
 $('#dialog-content').innerHTML=`<div class="dialog-head"><h2>${esc(d.name)} · ${esc(v.revision)}</h2>${btn('×','close')}</div><div class="panel-body">${badge(v.status)}<p>${esc(v.change_note||'暂无变更说明')}</p><p class="subtext">${esc(name('users',v.created_by))} · ${esc(date(v.created_at))}</p><p class="notice">这是配置实际引用的版本；新增版本不会自动替换此引用。</p><div class="file-links">${fileLinks(files,'document')||'<span class="muted">此版本暂无附件</span>'}</div></div><div class="dialog-foot">${link('查看文档全部版本','document',`data-id="${d.id}"`)}${btn('关闭','close')}</div>`;
 if(!$('#dialog').open)$('#dialog').showModal();
}
function configDetail(id){
 const c=get('configurations',id);if(!c)return toast('配置不存在，请刷新资料后重试。');
 if(!closeModal())return;
 const resourceLink=id=>id?link(res(id),'resource',`data-id="${id}"`):'—';
 const versionLink=id=>id?link(ver(id),'version',`data-id="${id}"`)+(get('doc_versions',id)?` ${badge(get('doc_versions',id).status)}`:''):'—';
 const pairs=[['封装厂',link(name('factories',c.factory),'factory',`data-id="${c.factory}"`)],['芯片型号',link(name('chips',c.chip),'chip',`data-id="${c.chip}"`)],...Object.entries({handler:'Handler',kit:'KIT',tester:'测试机',lb:'LB',socket:'Socket',dc:'DC 线'}).map(([key,label])=>[label,resourceLink(c[key])]),...Object.entries({norm:'LB 规范版本',lb_drawing:'LB 图纸版本',socket_drawing:'Socket 图纸版本',pin_drawing:'Pin 针图纸版本'}).map(([key,label])=>[label,versionLink(c[key])]),['验证状态',badge(c.status)],['启用状态',badge(c.active?'启用':'已停用')],['备注',esc(c.note||'—')]];
 const tasks=state.data.tasks.filter(t=>t.configuration===c.id&&t.active);
 $('#dialog-content').innerHTML=`<div class="dialog-head"><h2>${esc(c.name)}</h2>${btn('×','close')}</div><div class="panel-body detail-grid">${pairs.map(([k,v])=>`<div><small>${k}</small>${v}</div>`).join('')}</div>${panel('关联进度事项',taskTable(tasks),canEdit()&&c.active?btn('＋ 新增关联事项','configuration-task',`data-id="${c.id}"`):'')}<div class="dialog-foot">${edit('configurations',id)}${btn('关闭','close')}</div>`;
 if(!$('#dialog').open)$('#dialog').showModal();
}
async function handleAction(el){
 const a=el.dataset.action,id=Number(el.dataset.id);
 if(['tab','filter','reset','logout','select-factory','factory-scope','factory-filter'].includes(a)&&!closeModal())return;
 if(a==='select-factory'){resetFilters();state.id=id;render();return;}
 if(a==='factory-scope'){factoryList.activeOnly=el.dataset.scope==='active';render();return;}
 if(a==='factory-filter'){factoryList.q=$('#factory-search').value;factoryList.includeInactive=$('#factory-inactive').checked;render();return;}
 if(a==='nav')return navigate(el.dataset.page);
 if(a==='menu')return $('.sidebar').classList.toggle('open');
 if(a==='close')return closeModal();
 if(a==='refresh'){if(await refresh())toast('资料已刷新');return;}
 if(a==='filter'){state.q=$('#search').value;state.kind=$('#kind-filter')?.value||'';state.factory=$('#factory-filter')?.value||'';state.status=$('#status-filter')?.value||'';state.resource=$('#resource-filter')?.value||'';state.location=$('#location-filter')?.value||'';state.showInactive=$('#inactive')?.checked||false;return render();}
 if(a==='reset'){resetFilters();return render();}
 if(a==='tab'){state.tab=el.dataset.tab;resetFilters();return render();}
 if(a==='new'||a==='edit')return openRecord(el.dataset.kind,a==='edit'?id:null);
 if(['factory','chip','resource','document','task'].includes(a)){return navigate({factory:'factories',chip:'chips',resource:'resources',document:'documents',task:'tasks'}[a],id);}
 if(a==='configuration')return configDetail(id);
 if(a==='version')return versionDetail(id);
 if(a==='configuration-task'){const c=get('configurations',id);if(!c||!c.active)return toast('配置已停用或不存在，请刷新后重试。');return openRecord('tasks',null,{factory:c.factory,chip:c.chip,configuration:c.id});}
 if(a==='stock')return stockForm(el.dataset.op);
 if(a==='stock-row'){const row=get('stocks',id);if(!row)return toast('库存记录不存在，请刷新。');return stockForm(el.dataset.op,{resource:row.resource,location:row.location,state:row.state});}
 if(a==='transfer-detail')return transferDetail(id);
 if(a==='receive')return receiveForm(id);
 if(a==='upload-version')return uploadForm(id);
 if(a==='progress')return progressForm(id);
 if(a==='version-status'){const v=get('doc_versions',id);if(!confirm(`确定将版本 ${v.revision} 设为“${el.dataset.status}”？历史引用会保留。`))return;await api(`/api/versions/${id}/status`,{method:'POST',body:{status:el.dataset.status,expected:v.status}});await refresh();return toast('状态已更新');}
 if(a==='logout'){await api('/api/logout',{method:'POST',body:{}});state.user=null;return boot();}
 if(a==='password')return modal('修改密码',[f('old_password','原密码','password',{required:true}),f('password','新密码（至少 10 位）','password',{required:true})],{},form=>api('/api/password',{method:'POST',body:Object.fromEntries(form)}));
}
document.addEventListener('click',e=>{const el=e.target.closest('[data-action]');if(!el)return;if(el.closest('form')&&el.tagName==='BUTTON')e.preventDefault();handleAction(el).catch(err=>toast(err.message));});
document.addEventListener('submit',e=>{if(e.target.id==='factory-search-form'){e.preventDefault();handleAction({dataset:{action:'factory-filter'}}).catch(err=>toast(err.message));}});
document.addEventListener('change',e=>{if(e.target.id==='factory-inactive')handleAction({dataset:{action:'factory-filter'}}).catch(err=>toast(err.message));});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='search'){e.preventDefault();handleAction(document.querySelector('[data-action="filter"]')).catch(err=>toast(err.message));}});
async function boot(){
 try{
 const s=await api('/api/session');state.user=s.user;
 if(s.user){await refresh();return;}
 $('#app').innerHTML=`<div class="login-page"><section class="login-intro"><div class="brand"><span class="brand-mark">FT</span><div><strong>资源管理平台</strong><small>TEST RESOURCE CENTER</small></div></div><h1>测试资源<br>统一记录与查阅</h1><p>从封装厂到芯片型号，关联设备、配套资源、库存与图纸，让每一次更新有据可查。</p><div class="login-points"><span>配套配置</span><span>库存流转</span><span>图纸版本</span><span>进度协作</span></div></section><section class="login-area"><div class="login-card"><h2>${s.needs_setup?'创建管理员账号':'登录工作台'}</h2><p class="subtext">${s.needs_setup?'首次使用：创建账号后开始录入资料。':'使用公司内部账号访问资源资料。'}</p><form id="login-form">${s.needs_setup&&!setupKey?fieldHTML(f('key','初始化密钥（见 runtime/initial-setup.txt）','password',{required:true})):''}${fieldHTML(f('username','账号','text',{required:true}))}${s.needs_setup?fieldHTML(f('name','姓名')):''}${fieldHTML(f('password',s.needs_setup?'密码（至少 10 位）':'密码','password',{required:true}))}<div id="login-error" class="form-error" role="alert"></div><button class="primary" type="submit">${s.needs_setup?'创建并进入平台':'登录'}</button></form><p class="footer-note">${s.needs_setup?'初始业务资料为空，由你逐步录入。':'账号由管理员分配，支持电脑与手机浏览器。'}</p></div></section></div>`;
 $('#login-form').addEventListener('submit',async e=>{e.preventDefault();e.submitter.disabled=true;$('#login-error').textContent='';try{const data=Object.fromEntries(new FormData(e.target));if(setupKey)data.key=setupKey;const result=await api(s.needs_setup?'/api/setup':'/api/login',{method:'POST',body:data});state.user=result.user;setupKey='';await refresh();}catch(err){$('#login-error').textContent=err.message;}finally{if(e.submitter)e.submitter.disabled=false;}});
 }catch(err){$('#app').innerHTML=`<div class="loading"><h2>无法连接平台</h2><p>${esc(err.message)}</p><button data-action="reload">重新连接</button></div>`;document.querySelector('[data-action="reload"]').onclick=boot;}
}
boot();

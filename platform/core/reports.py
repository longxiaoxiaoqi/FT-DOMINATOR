"""One human-readable projection shared by table filters and CSV exports."""

def build_reports(data):
    lookup={key:{r['id']:r for r in rows} for key,rows in data.items() if isinstance(rows,list)}
    def obj(kind,id): return lookup.get(kind,{}).get(id,{})
    def name(kind,id):
        r=obj(kind,id)
        return r.get('name') or r.get('title') or r.get('username') or ''
    def resource(id):
        r=obj('resources',id)
        return ' · '.join(filter(None,[r.get('name'),r.get('revision')]))
    def version(id):
        r=obj('doc_versions',id)
        return ' · '.join(filter(None,[name('documents',r.get('document')),r.get('revision')]))
    resource_factories={}
    chip_factories={}
    for c in data.get('configurations',[]):
        if not c.get('active'): continue
        chip_factories.setdefault(c['chip'],set()).add(c['factory'])
        for k in ['handler','kit','tester','lb','socket','dc']:
            if c.get(k): resource_factories.setdefault(c[k],set()).add(c['factory'])
    for s in data.get('stocks',[]):
        factory=obj('locations',s['location']).get('factory')
        if factory and s['qty']>0: resource_factories.setdefault(s['resource'],set()).add(factory)
    def factories(kind,r):
        if kind=='factories': return [r['id']]
        if kind=='chips': return sorted(chip_factories.get(r['id'],[]))
        if kind=='resources': return sorted(resource_factories.get(r['id'],[]))
        if kind=='stocks' or kind=='movements': return [obj('locations',r['location']).get('factory')]
        if kind=='transfers': return [obj('locations',r[k]).get('factory') for k in ['source','target']]
        if kind=='documents' and r.get('resource'): return sorted(resource_factories.get(r['resource'],[]))
        if kind=='tasks': return [r.get('factory'),obj('configurations',r.get('configuration')).get('factory')]
        return [r.get('factory')]
    def joined_factories(kind,r): return ' / '.join(name('factories',f) for f in sorted(set(x for x in factories(kind,r) if x)))
    enabled=lambda r:'启用' if r.get('active',True) else '已停用'
    specs={
      'factories':(['封装厂','厂区','联系人','联系方式','备注','启用状态'],lambda r:[r['name'],r['site'],r['contact'],r['phone'],r['note'],enabled(r)]),
      'chips':(['芯片型号','封装形式','尺寸','Pin 数','关联封装厂','备注','启用状态'],lambda r:[r['name'],r['package'],r['dimensions'],r['pins'],joined_factories('chips',r),r['note'],enabled(r)]),
      'locations':(['存放地点','所属封装厂','备注','启用状态'],lambda r:[r['name'],name('factories',r['factory']),r['note'],enabled(r)]),
      'resources':(['资源类型','型号','设计版本','单位','规格','关联封装厂','备注','启用状态'],lambda r:[r['kind'],r['name'],r['revision'],r['unit'],r['spec'],joined_factories('resources',r),r['note'],enabled(r)]),
      'configurations':(['配置名称','封装厂','芯片型号','Handler','KIT','测试机','LB','Socket','DC线','LB规范版本','LB图纸版本','Socket图纸版本','Pin针图纸版本','验证状态','备注','启用状态'],lambda r:[r['name'],name('factories',r['factory']),name('chips',r['chip']),*[resource(r[k]) for k in ['handler','kit','tester','lb','socket','dc']],*[version(r[k]) for k in ['norm','lb_drawing','socket_drawing','pin_drawing']],r['status'],r['note'],enabled(r)]),
      'documents':(['文档名称','类别','封装厂','资源型号与版本','适用范围','版本数量','备注','启用状态'],lambda r:[r['name'],r['kind'],name('factories',r['factory']),resource(r['resource']),r['scope'],sum(v['document']==r['id'] for v in data.get('doc_versions',[])),r['note'],enabled(r)]),
      'stocks':(['资源类型','型号与版本','存放地点','封装厂','库存状态','数量','单位'],lambda r:[obj('resources',r['resource']).get('kind'),resource(r['resource']),name('locations',r['location']),joined_factories('stocks',r),r['state'],r['qty'],obj('resources',r['resource']).get('unit')]),
      'transfers':(['调拨单号','资源型号与版本','来源地点','目标地点','库存状态','发出数量','已签收数量','在途数量','单位','签收状态','经办人','发出时间','说明'],lambda r:[f"TR-{r['id']:05d}",resource(r['resource']),name('locations',r['source']),name('locations',r['target']),r['state'],r['qty'],r['received'],r['qty']-r['received'],obj('resources',r['resource']).get('unit'),'已完成' if r['received']==r['qty'] else '在途',name('users',r['created_by']),r['created_at'],r['note']]),
      'movements':(['时间','资源型号与版本','地点','封装厂','状态','操作','数量变更','单位','操作人','原因','调拨单号'],lambda r:[r['created_at'],resource(r['resource']),name('locations',r['location']),joined_factories('movements',r),r['state'],r['kind'],r['delta'],obj('resources',r['resource']).get('unit'),name('users',r['created_by']),r['note'],f"TR-{r['transfer']:05d}" if r['transfer'] else '']),
      'tasks':(['事项','类别','关联封装厂','芯片型号','资源型号与版本','测试配置','负责人','状态','计划完成日期','说明','启用状态'],lambda r:[r['title'],r['category'],joined_factories('tasks',r),name('chips',r['chip'] or obj('configurations',r['configuration']).get('chip')),resource(r['resource']),name('configurations',r['configuration']),name('users',r['owner']),r['status'],r['due_date'],r['note'],enabled(r)]),
    }
    reports={}
    for kind,(columns,convert) in specs.items():
        rows=[]
        for r in data.get(kind,[]):
            cells=convert(r)
            text=' '.join('' if v is None else str(v) for v in cells).lower()
            state=r.get('status',r.get('state',''))
            if kind=='transfers': state='已完成' if r['received']==r['qty'] else '在途'
            if not state and 'active' in r: state=enabled(r)
            category=obj('resources',r.get('resource')).get('kind','') if kind in ['stocks','transfers','movements'] else r.get('kind',r.get('category',''))
            locations=[r.get('location')] if kind in ['stocks','movements'] else [r.get('source'),r.get('target')] if kind=='transfers' else []
            rows.append({'id':r['id'],'cells':cells,'search':text,'active':r.get('active',True),'factories':sorted(set(x for x in factories(kind,r) if x)), 'kind':category,'status':state,'resource':r.get('resource'),'locations':[x for x in locations if x]})
        reports[kind]={'columns':columns,'rows':rows}
    return reports

def filter_rows(rows,params):
    query=params.get('q','').strip().lower()
    return [r for r in rows if (params.get('inactive')=='1' or r['active'])
            and (not query or query in r['search'])
            and (not params.get('kind') or r['kind']==params['kind'])
            and (not params.get('status') or r['status']==params['status'])
            and (not params.get('resource') or str(r.get('resource'))==params['resource'])
            and (not params.get('location') or params['location'] in [str(x) for x in r.get('locations',[])])
            and (not params.get('factory') or params['factory'] in [str(x) for x in r['factories']])]

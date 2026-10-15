import csv
import hashlib
import io
import json
import mimetypes
import secrets
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction, IntegrityError, OperationalError
from django.db.models import F
from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import *
from .reports import build_reports, filter_rows
from ft.build import BUILD_ID, INSTANCE_ID

EDITABLE = {
 'factories': (Factory, ['name','site','contact','phone','note','active']),
 'locations': (Location, ['name','factory','note','active']),
 'chips': (Chip, ['name','package','dimensions','pins','note','active']),
 'resources': (Resource, ['kind','name','revision','spec','unit','note','active']),
 'configurations': (Configuration, ['name','factory','chip','handler','kit','tester','lb','socket','dc','norm','lb_drawing','socket_drawing','pin_drawing','status','note','active']),
 'documents': (Document, ['name','kind','factory','resource','scope','note','active']),
 'tasks': (Task, ['title','category','factory','chip','resource','configuration','owner','status','due_date','note','active']),
}
LISTS = {**{k:v[0] for k,v in EDITABLE.items()}, 'stocks':Stock, 'transfers':Transfer, 'movements':Movement, 'doc_versions':DocumentVersion, 'attachments':Attachment, 'task_updates':TaskUpdate, 'task_attachments':TaskAttachment}

class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def body(request):
    try:
        value = json.loads(request.body or '{}')
        if not isinstance(value, dict): raise ValueError()
        return value
    except (ValueError, UnicodeDecodeError):
        raise ApiError('请求格式不正确。')

def role(user):
    return 'admin' if user.is_superuser else 'editor' if user.is_staff else 'viewer'

def user_data(user):
    return {'id':user.id,'username':user.username,'name':user.first_name or user.username,'role':role(user),'active':user.is_active}

def serialize(obj):
    return {f.name: getattr(obj, f.attname) for f in obj._meta.fields if f.name != 'stored_name'}

def audit(request, action, entity, obj=None, detail=None):
    Audit.objects.create(actor=request.user if request.user.is_authenticated else None, action=action, entity=entity, object_id=obj.pk if obj else None, detail=detail or {})

def endpoint(write=False, admin=False, public=False, member=False):
    def decorator(fn):
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            try:
                if not public:
                    if not request.user.is_authenticated: raise ApiError('请先登录。',401)
                    if admin and not request.user.is_superuser: raise ApiError('只有管理员可操作。',403)
                    if not member and (write or request.method not in ['GET','HEAD']) and not request.user.is_staff and not request.user.is_superuser:
                        raise ApiError('当前账号为只读账号。',403)
                return fn(request,*args,**kwargs)
            except ApiError as e:
                return JsonResponse({'error':e.message},status=e.status)
            except ValidationError as e:
                return JsonResponse({'error':'；'.join(e.messages)},status=400)
            except ObjectDoesNotExist:
                return JsonResponse({'error':'记录不存在或已不可用。'},status=404)
            except IntegrityError:
                return JsonResponse({'error':'记录重复或关联不正确，请刷新后重试。'},status=409)
            except OperationalError:
                return JsonResponse({'error':'数据正在更新，请稍后重试。'},status=409)
            except (ValueError, TypeError, OverflowError):
                return JsonResponse({'error':'字段格式不正确，请检查数字、日期和关联。'},status=400)
        return wrapped
    return decorator

def method(request, allowed):
    if request.method not in allowed: raise ApiError('不支持此操作。',405)

@ensure_csrf_cookie
def index(request):
    response = render(request,'index.html',{'build_id':BUILD_ID})
    response['Cache-Control'] = 'no-store'
    response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
    return response

@ensure_csrf_cookie
@endpoint(public=True)
def session(request):
    method(request,['GET'])
    response = JsonResponse({'app':'ft-platform','build':BUILD_ID,'instance':INSTANCE_ID,'user':user_data(request.user) if request.user.is_authenticated else None,'needs_setup':not User.objects.exists()})
    response['Cache-Control'] = 'no-store'
    return response

@endpoint(public=True)
def setup(request):
    method(request,['POST'])
    data=body(request)
    if not secrets.compare_digest(str(data.get('key','')),settings.SETUP_KEY): raise ApiError('初始化密钥不正确，请通过本机启动脚本打开平台。',403)
    with transaction.atomic():
        if User.objects.exists(): raise ApiError('管理员已创建，请登录。',409)
        validate_password(data.get('password',''))
        user=User(username=str(data.get('username','')).strip(),first_name=str(data.get('name','')).strip(),is_superuser=True,is_staff=True)
        user.full_clean(exclude=['password','last_login','date_joined']); user.set_password(data['password']); user.save()
    login(request,user); audit(request,'初始化管理员','users',user)
    return JsonResponse({'user':user_data(user)})

@endpoint(public=True)
def signin(request):
    method(request,['POST']); data=body(request)
    key=hashlib.sha256((request.META.get('REMOTE_ADDR','')+'|'+str(data.get('username',''))).encode()).hexdigest()
    now=timezone.now()
    with transaction.atomic():
        attempt,_=LoginAttempt.objects.get_or_create(key=key,defaults={'since':now})
        if now-attempt.since>timedelta(minutes=10):
            attempt.count=0; attempt.since=now
        if attempt.count>=10: raise ApiError('登录尝试过多，请 10 分钟后重试。',429)
        attempt.count+=1; attempt.save()
    user=authenticate(request,username=data.get('username'),password=data.get('password'))
    if user is None: raise ApiError('账号或密码不正确，或账号已停用。',401)
    LoginAttempt.objects.filter(key=key).delete(); login(request,user); audit(request,'登录','users',user)
    return JsonResponse({'user':user_data(user)})

@endpoint(member=True)
def signout(request):
    method(request,['POST']); logout(request)
    return JsonResponse({'ok':True})

@endpoint(member=True)
def password(request):
    method(request,['POST']); data=body(request)
    if not request.user.check_password(data.get('old_password','')): raise ApiError('原密码不正确。')
    validate_password(data.get('password',''),request.user)
    request.user.set_password(data['password']); request.user.save(); update_session_auth_hash(request,request.user)
    audit(request,'修改密码','users',request.user)
    return JsonResponse({'ok':True})

@endpoint()
def snapshot(request):
    method(request,['GET'])
    result={key:[serialize(x) for x in model.objects.order_by('-id')] for key,model in LISTS.items()}
    result['users']=[user_data(u) for u in User.objects.order_by('id')]
    result['reports']=build_reports(result)
    if request.user.is_superuser:
        result['audit']=[serialize(x) for x in Audit.objects.order_by('-id')[:300]]
    return JsonResponse(result)

def apply_fields(obj, data, fields):
    for key in fields:
        if key not in data: continue
        field=obj._meta.get_field(key); value=data[key]
        if isinstance(field,models.ForeignKey):
            value=None if value in ['',None] else int(value)
            if value:
                related=field.related_model.objects.get(pk=value)
                is_active=related.is_active if isinstance(related,User) else getattr(related,'active',True)
                if not is_active and getattr(obj,field.attname)!=value: raise ApiError('不能关联已停用记录。')
                if isinstance(related,DocumentVersion) and getattr(obj,field.attname)!=value:
                    if related.status=='作废': raise ApiError('不能新增引用已作废的图纸或规范版本。')
                    if not related.document.active: raise ApiError('不能新增引用已停用的文档档案。')
            setattr(obj,field.attname,value)
        else:
            if value == '' and field.null: value=None
            if isinstance(field,models.BooleanField) and not isinstance(value,bool): raise ApiError('启用状态不正确。')
            setattr(obj,key,value)

@endpoint(write=True)
def record(request, kind, pk=None):
    method(request,['POST','PUT'])
    if kind not in EDITABLE: raise ApiError('未知档案类型。',404)
    data=body(request); model,fields=EDITABLE[kind]
    with transaction.atomic():
        obj=model.objects.get(pk=pk) if pk else model()
        before=serialize(obj) if pk else {}
        if pk and data.get('version')!=obj.version: raise ApiError('这条记录已被他人更新，请刷新后重新编辑。',409)
        apply_fields(obj,data,fields)
        # Inventory and historical references keep a resource's identity stable.
        if pk and kind=='resources' and any(before[x]!=getattr(obj,x) for x in ['kind','name','revision','unit']):
            used=Stock.objects.filter(resource=obj).exists() or Movement.objects.filter(resource=obj).exists() or Document.objects.filter(resource=obj).exists() or Configuration.objects.filter(Q(handler=obj)|Q(kit=obj)|Q(tester=obj)|Q(lb=obj)|Q(socket=obj)|Q(dc=obj)).exists()
            if used: raise ApiError('该型号已被使用，不能更改类型、型号、版本或单位；请新增型号版本。')
        if pk and kind=='documents' and DocumentVersion.objects.filter(document=obj).exists() and any(before[x]!=getattr(obj, obj._meta.get_field(x).attname) for x in ['kind','factory','resource']):
            raise ApiError('已有文档版本，不能改变其类别或归属。')
        obj.full_clean()
        if pk:
            update={f.attname:getattr(obj,f.attname) for f in obj._meta.fields if f.name in fields}
            update.update(version=F('version')+1,updated_at=timezone.now())
            if not model.objects.filter(pk=pk,version=data['version']).update(**update): raise ApiError('修改冲突，请刷新。',409)
            obj.refresh_from_db()
        else: obj.save()
        if kind=='tasks' and (not pk or before['status']!=obj.status):
            TaskUpdate.objects.create(task=obj,text='创建事项' if not pk else '修改事项状态',status=obj.status,created_by=request.user)
        audit(request,'编辑' if pk else '新增',kind,obj,{'fields':list(data.keys())})
    return JsonResponse(serialize(obj),status=200 if pk else 201)

@endpoint(admin=True)
def users(request,pk=None):
    method(request,['POST','PUT']); data=body(request)
    with transaction.atomic():
        u=User.objects.get(pk=pk) if pk else User()
        new_role=data.get('role','viewer')
        if new_role not in ['admin','editor','viewer']: raise ApiError('角色不正确。')
        active=data.get('active',True)
        if not isinstance(active,bool): raise ApiError('启用状态不正确。')
        if pk==request.user.pk and (not active or new_role!='admin'): raise ApiError('不能停用或降级当前管理员。')
        u.username=str(data.get('username',u.username)).strip(); u.first_name=str(data.get('name','')).strip()
        u.is_superuser=new_role=='admin'; u.is_staff=new_role in ['admin','editor']; u.is_active=active
        if data.get('password'):
            validate_password(data['password'],u); u.set_password(data['password'])
        elif not pk: raise ApiError('请设置初始密码。')
        u.full_clean(exclude=['password','last_login','date_joined']); u.save()
        audit(request,'编辑用户' if pk else '新增用户','users',u,{'role':new_role,'active':active})
    if u.pk==request.user.pk: update_session_auth_hash(request,u)
    return JsonResponse(user_data(u))

def integer(value, positive=False):
    if isinstance(value,bool) or not str(value).isdigit(): raise ApiError('数量必须为整数。')
    n=int(value)
    if n>1000000000 or (positive and n==0): raise ApiError('数量超出允许范围。')
    return n

def stock_change(request,resource,location,state,delta,kind,note,transfer=None):
    s,_=Stock.objects.get_or_create(resource=resource,location=location,state=state)
    if not Stock.objects.filter(pk=s.pk,qty__gte=max(0,-delta)).update(qty=F('qty')+delta): raise ApiError('库存不足，本次操作未保存。',409)
    Movement.objects.create(resource=resource,location=location,state=state,delta=delta,kind=kind,note=note,transfer=transfer,created_by=request.user)

@endpoint(write=True)
def inventory(request):
    method(request,['POST']); data=body(request)
    key=str(data.get('key','')); uuid.UUID(key)
    fingerprint=hashlib.sha256(json.dumps({'user':request.user.id,'data':data},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with transaction.atomic():
        old=RequestKey.objects.filter(key=key).first()
        if old:
            if old.fingerprint!=fingerprint: raise ApiError('重复请求的内容已改变，请刷新。',409)
            return JsonResponse(old.response)
        operation=data.get('operation'); note=str(data.get('note','')).strip()
        if not note: raise ApiError('请填写操作原因或说明。')
        if operation=='receive':
            t=Transfer.objects.select_for_update().get(pk=data.get('transfer'))
            qty=integer(data.get('qty'),True)
            if not Transfer.objects.filter(pk=t.pk,received__lte=F('qty')-qty).update(received=F('received')+qty): raise ApiError('签收数量超过剩余在途数量。',409)
            stock_change(request,t.resource,t.target,t.state,qty,'签收',note,t)
            result={'ok':True,'transfer':t.id}
        else:
            resource=Resource.objects.get(pk=data.get('resource'),active=True)
            if resource.kind not in ['LB','Socket','DC线','KIT']: raise ApiError('仅 LB、Socket、DC 线和 KIT 管理数量库存。')
            location=Location.objects.get(pk=data.get('location'),active=True)
            state=data.get('state')
            if state not in dict(STATES): raise ApiError('库存状态不正确。')
            qty=integer(data.get('qty'),operation!='count')
            if operation=='transfer':
                target=Location.objects.get(pk=data.get('target'),active=True)
                if location.pk==target.pk: raise ApiError('来源与目标地点不能相同。')
                t=Transfer.objects.create(resource=resource,source=location,target=target,state=state,qty=qty,note=note,created_by=request.user)
                stock_change(request,resource,location,state,-qty,'调拨发出',note,t)
                result={'ok':True,'transfer':t.id}
            elif operation=='state':
                to=data.get('target_state')
                if to not in dict(STATES) or to==state: raise ApiError('请选择不同的目标状态。')
                stock_change(request,resource,location,state,-qty,'状态转出',note)
                stock_change(request,resource,location,to,qty,'状态转入',note)
                result={'ok':True}
            elif operation in ['in','scrap','count']:
                current=Stock.objects.filter(resource=resource,location=location,state=state).first()
                before=current.qty if current else 0
                if operation=='count' and data.get('expected')!=before: raise ApiError('盘点期间库存已变动，请刷新后重新核对。',409)
                delta=qty-before if operation=='count' else -qty if operation=='scrap' else qty
                stock_change(request,resource,location,state,delta,{'in':'入库','scrap':'报废','count':'盘点'}[operation],note)
                result={'ok':True}
            else: raise ApiError('未知库存操作。')
        RequestKey.objects.create(key=key,fingerprint=fingerprint,response=result)
        audit(request,'库存操作','inventory',detail={'operation':operation,'key':key})
    return JsonResponse(result)

def save_upload(upload):
    if upload.size>30*1024*1024: raise ApiError('单个附件不能超过 30 MB。')
    name=Path(upload.name.replace('\\','/')).name[:255]
    if not name: raise ApiError('文件名无效。')
    ext=Path(name).suffix.lower()
    allowed={'.pdf','.png','.jpg','.jpeg','.webp','.dwg','.dxf','.step','.stp','.zip','.xlsx','.xls','.docx','.txt'}
    if ext not in allowed: raise ApiError('不支持此附件格式。')
    mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
    stored=uuid.uuid4().hex+ext
    settings.MEDIA_ROOT.mkdir(parents=True,exist_ok=True)
    path=settings.MEDIA_ROOT/stored
    with path.open('wb') as f:
        for chunk in upload.chunks(): f.write(chunk)
    return {'original_name':name,'stored_name':stored,'size':upload.size,'content_type':mime},path

@endpoint(write=True)
def upload_version(request):
    method(request,['POST']); paths=[]
    try:
        with transaction.atomic():
            doc=Document.objects.get(pk=request.POST.get('document'),active=True)
            files=request.FILES.getlist('files')
            if not files or len(files)>10: raise ApiError('请选择 1 到 10 个附件。')
            version=DocumentVersion(document=doc,revision=request.POST.get('revision','').strip(),status=request.POST.get('status','草稿'),change_note=request.POST.get('change_note',''),created_by=request.user)
            version.full_clean(); version.save()
            for upload in files:
                info,path=save_upload(upload); paths.append(path)
                Attachment.objects.create(doc_version=version,**info)
            audit(request,'新增文档版本','doc_versions',version)
        return JsonResponse(serialize(version),status=201)
    except Exception:
        for path in paths: path.unlink(missing_ok=True)
        raise

@endpoint(write=True)
def version_status(request,pk):
    method(request,['POST']); data=body(request)
    with transaction.atomic():
        obj=DocumentVersion.objects.get(pk=pk)
        if data.get('expected')!=obj.status: raise ApiError('状态已更新，请刷新。',409)
        status=data.get('status')
        if (obj.status,status) not in [('草稿','已发布'),('草稿','作废'),('已发布','作废')]: raise ApiError('只能发布草稿或作废版本。')
        DocumentVersion.objects.filter(pk=pk,status=obj.status).update(status=status)
        audit(request,'文档版本状态','doc_versions',obj,{'before':obj.status,'after':status})
    return JsonResponse({'ok':True})

@endpoint(write=True)
def progress(request,pk):
    method(request,['POST']); paths=[]
    try:
        with transaction.atomic():
            task=Task.objects.get(pk=pk,active=True)
            status=request.POST.get('status'); text=request.POST.get('text','').strip()
            if status not in dict(TASK_STATES) or not text: raise ApiError('请选择状态并填写进展。')
            if str(task.version)!=request.POST.get('version'): raise ApiError('事项已更新，请刷新。',409)
            if not Task.objects.filter(pk=pk,version=task.version).update(status=status,version=F('version')+1,updated_at=timezone.now()): raise ApiError('事项已更新，请刷新。',409)
            update=TaskUpdate.objects.create(task=task,text=text,status=status,created_by=request.user)
            files=request.FILES.getlist('files')
            if len(files)>10: raise ApiError('每次最多 10 个附件。')
            for file in files:
                info,path=save_upload(file); paths.append(path); TaskAttachment.objects.create(update=update,**info)
            audit(request,'更新进度','tasks',task)
        return JsonResponse({'ok':True})
    except Exception:
        for path in paths: path.unlink(missing_ok=True)
        raise

@endpoint()
def download(request,kind,pk):
    method(request,['GET'])
    cls=Attachment if kind=='document' else TaskAttachment if kind=='task' else None
    if cls is None: raise ApiError('未知附件类型。',404)
    obj=cls.objects.get(pk=pk); path=settings.MEDIA_ROOT/obj.stored_name
    if not path.is_file(): raise ApiError('附件文件不存在，请联系管理员恢复。',404)
    preview=request.GET.get('preview')=='1' and obj.content_type in ['application/pdf','image/png','image/jpeg','image/webp']
    response=FileResponse(path.open('rb'),as_attachment=not preview,filename=obj.original_name,content_type=obj.content_type)
    response['Cache-Control']='private, no-store'
    response['Content-Security-Policy']="default-src 'none'; sandbox"
    return response

@endpoint()
def export_csv(request,kind):
    method(request,['GET'])
    data={key:[serialize(x) for x in model.objects.order_by('-id')] for key,model in LISTS.items()}
    data['users']=[user_data(u) for u in User.objects.order_by('id')]
    reports=build_reports(data)
    if kind not in reports: raise ApiError('此类别不支持表格导出。',404)
    report=reports[kind];rows=filter_rows(report['rows'],request.GET)
    buf=io.StringIO();writer=csv.writer(buf);writer.writerow(report['columns'])
    for row in rows:
        values=[]
        for value in row['cells']:
            # Preserve real numbers while treating formula-like text as text in Excel.
            if isinstance(value,(int,float)) and not isinstance(value,bool): values.append(value);continue
            if hasattr(value,'tzinfo') and value.tzinfo: value=timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S')
            v='' if value is None else str(value)
            if v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n')): v="'"+v
            values.append(v)
        writer.writerow(values)
    response=HttpResponse('\ufeff'+buf.getvalue(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{kind}.csv"'
    response['Cache-Control']='private, no-store'
    return response

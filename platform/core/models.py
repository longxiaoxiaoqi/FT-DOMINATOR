from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

class Record(models.Model):
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class Factory(Record):
    name = models.CharField('封装厂名称', max_length=120, unique=True)
    site = models.CharField('厂区', max_length=120, blank=True)
    contact = models.CharField('联系人', max_length=80, blank=True)
    phone = models.CharField('联系方式', max_length=80, blank=True)
    note = models.TextField('备注', blank=True)

class Location(Record):
    name = models.CharField('地点名称', max_length=120, unique=True)
    factory = models.ForeignKey(Factory, on_delete=models.PROTECT, null=True, blank=True)
    note = models.TextField(blank=True)

class Chip(Record):
    name = models.CharField('芯片型号', max_length=120, unique=True)
    package = models.CharField('封装形式', max_length=80, blank=True)
    dimensions = models.CharField('尺寸', max_length=80, blank=True)
    pins = models.PositiveIntegerField('Pin 数', null=True, blank=True)
    note = models.TextField(blank=True)

RESOURCE_TYPES = [(x, x) for x in ['LB', 'Socket', 'DC线', 'KIT', '测试机', 'Handler', 'Pin针']]
class Resource(Record):
    kind = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    name = models.CharField('型号', max_length=120)
    revision = models.CharField('设计版本', max_length=40, blank=True)
    spec = models.TextField('规格', blank=True)
    unit = models.CharField('计量单位', max_length=12, default='件')
    note = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind', 'name', 'revision'], name='unique_resource_revision')]

class Document(Record):
    name = models.CharField('文档名称', max_length=160)
    kind = models.CharField(max_length=20, choices=[(x,x) for x in ['LB规范', 'LB图纸', 'Socket图纸', 'Pin针图纸']])
    factory = models.ForeignKey(Factory, on_delete=models.PROTECT, null=True, blank=True)
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, null=True, blank=True)
    scope = models.CharField('适用范围', max_length=200, blank=True)
    note = models.TextField(blank=True)
    def clean(self):
        if self.kind == 'LB规范':
            if not self.factory_id or self.resource_id:
                raise ValidationError('LB 规范必须关联封装厂，不能关联资源。')
        else:
            if not self.resource_id or self.factory_id:
                raise ValidationError('图纸必须关联资源，不能直接关联工厂。')
            expected = {'LB图纸':['LB'], 'Socket图纸':['Socket'], 'Pin针图纸':['Pin针','Socket']}
            if self.resource.kind not in expected.get(self.kind, []):
                raise ValidationError('图纸类别与资源类型不匹配。')

class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.PROTECT)
    revision = models.CharField('文档版本', max_length=40)
    status = models.CharField(max_length=20, choices=[(x,x) for x in ['草稿','已发布','作废']], default='草稿')
    change_note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['document','revision'], name='unique_document_version')]

class Attachment(models.Model):
    doc_version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT)
    original_name = models.CharField(max_length=255)
    stored_name = models.CharField(max_length=100, unique=True)
    size = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

class Configuration(Record):
    name = models.CharField('配置名称', max_length=120)
    factory = models.ForeignKey(Factory, on_delete=models.PROTECT)
    chip = models.ForeignKey(Chip, on_delete=models.PROTECT)
    handler = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    kit = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    tester = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    lb = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    socket = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    dc = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    norm = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    lb_drawing = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    socket_drawing = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    pin_drawing = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    status = models.CharField(max_length=20, choices=[(x,x) for x in ['待补全','待验证','验证中','已通过','停用']], default='待补全')
    note = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['factory','chip','name'], name='unique_configuration')]
    def clean(self):
        for field, kind in {'handler':'Handler','kit':'KIT','tester':'测试机','lb':'LB','socket':'Socket','dc':'DC线'}.items():
            r = getattr(self,field)
            if r and r.kind != kind:
                raise ValidationError(f'{field} 的资源类型必须是 {kind}。')
        if self.kit_id and not self.handler_id:
            raise ValidationError('请先选择 KIT 对应的 Handler。')
        if any([self.lb_id,self.socket_id,self.dc_id]) and not self.tester_id:
            raise ValidationError('请先选择配套资源对应的测试机。')
        if self.norm_id:
            doc = self.norm.document
            if doc.kind != 'LB规范' or doc.factory_id != self.factory_id:
                raise ValidationError('LB 规范必须属于当前封装厂。')
        for key,kind,res in [('lb_drawing','LB图纸',self.lb_id),('socket_drawing','Socket图纸',self.socket_id),('pin_drawing','Pin针图纸',self.socket_id)]:
            v = getattr(self,key)
            if v and (v.document.kind != kind or v.document.resource_id != res):
                raise ValidationError(f'{kind} 必须关联当前配置的对应资源。')
        if self.status == '已通过' and not all([self.handler_id,self.kit_id,self.tester_id,self.lb_id,self.socket_id,self.dc_id]):
            raise ValidationError('已通过配置需要补齐 Handler、KIT、测试机、LB、Socket 和 DC 线。')

STATES = [(x,x) for x in ['可用','使用中','维修中','待检']]
class Stock(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    state = models.CharField(max_length=20, choices=STATES)
    qty = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['resource','location','state'], name='unique_stock'), models.CheckConstraint(condition=Q(qty__gte=0), name='nonnegative_stock')]

class Transfer(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT)
    source = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='+')
    target = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='+')
    state = models.CharField(max_length=20, choices=STATES)
    qty = models.PositiveIntegerField()
    received = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(qty__gt=0) & Q(received__lte=models.F('qty')), name='valid_transfer_quantity')]

class Movement(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    state = models.CharField(max_length=20)
    delta = models.IntegerField()
    kind = models.CharField(max_length=20)
    note = models.TextField()
    transfer = models.ForeignKey(Transfer, on_delete=models.PROTECT, null=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class RequestKey(models.Model):
    key = models.CharField(max_length=64, unique=True)
    fingerprint = models.CharField(max_length=64)
    response = models.JSONField(default=dict)

TASK_STATES = [(x,x) for x in ['待开始','进行中','待确认','已完成','暂停','取消']]
class Task(Record):
    title = models.CharField('事项标题', max_length=200)
    category = models.CharField(max_length=20, choices=[(x,x) for x in ['制作','采购','图纸修改','维修','验证','调拨跟进']])
    factory = models.ForeignKey(Factory, on_delete=models.PROTECT, null=True, blank=True)
    chip = models.ForeignKey(Chip, on_delete=models.PROTECT, null=True, blank=True)
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, null=True, blank=True)
    configuration = models.ForeignKey(Configuration, on_delete=models.PROTECT, null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=TASK_STATES, default='待开始')
    due_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    def clean(self):
        if self.configuration_id:
            if self.factory_id and self.configuration.factory_id != self.factory_id:
                raise ValidationError('事项工厂与配置不一致。')
            if self.chip_id and self.configuration.chip_id != self.chip_id:
                raise ValidationError('事项芯片与配置不一致。')

class TaskUpdate(models.Model):
    task = models.ForeignKey(Task, on_delete=models.PROTECT)
    text = models.TextField()
    status = models.CharField(max_length=20, choices=TASK_STATES)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class TaskAttachment(models.Model):
    update = models.ForeignKey(TaskUpdate, on_delete=models.PROTECT)
    original_name = models.CharField(max_length=255)
    stored_name = models.CharField(max_length=100, unique=True)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()

class Audit(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=40)
    entity = models.CharField(max_length=40)
    object_id = models.PositiveBigIntegerField(null=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    since = models.DateTimeField()

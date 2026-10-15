import csv
import io
import json
import tempfile
import uuid
from pathlib import Path
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import *

class PlatformTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('owner',password='Valid-test-389',is_superuser=True,is_staff=True)
        self.client.force_login(self.admin)
        self.factory=Factory.objects.create(name='测试工厂')
        self.chip=Chip.objects.create(name='TEST-CHIP')
        self.a=Location.objects.create(name='仓库')
        self.b=Location.objects.create(name='工厂仓库',factory=self.factory)
        self.lb=Resource.objects.create(kind='LB',name='TEST-LB',unit='件')
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.override=override_settings(MEDIA_ROOT=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)

    def post(self,url,data):
        return self.client.post(url,json.dumps(data),content_type='application/json')

    def inv(self,**data):
        return self.post('/api/inventory',{'key':str(uuid.uuid4()),'resource':self.lb.id,'location':self.a.id,'state':'可用','note':'测试操作',**data})

    def test_no_business_seed(self):
        self.assertEqual(Resource.objects.count(),1)
        self.assertEqual(Stock.objects.count(),0)

    def test_local_build_identity_and_uncached_entry(self):
        from ft.build import BUILD_ID, INSTANCE_ID
        client=Client()
        session=client.get('/api/session')
        self.assertEqual(session.json()['build'],BUILD_ID)
        self.assertEqual(session.json()['instance'],INSTANCE_ID)
        self.assertNotIn('runtime',session.content.decode())
        self.assertEqual(session['Cache-Control'],'no-store')
        index=client.get('/')
        self.assertContains(index,'/static/app.js?v='+BUILD_ID)
        self.assertContains(index,'/static/app.css?v='+BUILD_ID)
        self.assertEqual(index['Cache-Control'],'no-store')

    def test_authentication_csrf_and_private_paths(self):
        anon=Client(enforce_csrf_checks=True)
        self.assertEqual(anon.get('/api/data').status_code,401)
        self.assertEqual(anon.post('/api/login',{}).status_code,403)
        for url in ['/runtime/ft.sqlite3','/uploads/secret.pdf','/core/api.py','/static/../runtime/ft.sqlite3']:
            self.assertIn(anon.get(url).status_code,[400,404])

    def test_viewer_cannot_write_but_can_logout_and_change_password(self):
        viewer=User.objects.create_user('viewer',password='Viewer-389-valid')
        self.client.force_login(viewer)
        self.assertEqual(self.post('/api/records/factories',{'name':'禁止'}).status_code,403)
        self.assertEqual(self.post('/api/password',{'old_password':'Viewer-389-valid','password':'Updated-valid-382'}).status_code,200)
        self.assertEqual(self.post('/api/logout',{}).status_code,200)

    def test_record_edit_conflict(self):
        payload={'name':'新工厂','version':1}
        first=self.client.put(f'/api/records/factories/{self.factory.id}',json.dumps(payload),content_type='application/json')
        self.assertEqual(first.status_code,200,first.content)
        again=self.client.put(f'/api/records/factories/{self.factory.id}',json.dumps(payload),content_type='application/json')
        self.assertEqual(again.status_code,409)

    def test_transfer_partial_receipt_and_idempotency(self):
        self.assertEqual(self.inv(operation='in',qty=8).status_code,200)
        key=str(uuid.uuid4())
        sent=self.inv(operation='transfer',qty=5,target=self.b.id,key=key)
        self.assertEqual(sent.status_code,200,sent.content)
        self.assertEqual(self.inv(operation='transfer',qty=5,target=self.b.id,key=key).status_code,200)
        self.assertEqual(Transfer.objects.count(),1)
        self.assertEqual(Stock.objects.get(location=self.a).qty,3)
        self.assertFalse(Stock.objects.filter(location=self.b).exists())
        t=sent.json()['transfer']; key2=str(uuid.uuid4())
        self.assertEqual(self.inv(operation='receive',transfer=t,qty=2,key=key2).status_code,200)
        self.assertEqual(self.inv(operation='receive',transfer=t,qty=2,key=key2).status_code,200)
        self.assertEqual(Stock.objects.get(location=self.b).qty,2)
        self.assertEqual(self.inv(operation='receive',transfer=t,qty=4).status_code,409)
        self.assertEqual(Transfer.objects.get(pk=t).received,2)
        self.assertEqual(self.inv(operation='receive',transfer=t,qty=3).status_code,200)
        self.assertEqual(Stock.objects.get(location=self.b).qty,5)

    def test_insufficient_stock_rolls_back_transfer(self):
        self.assertEqual(self.inv(operation='transfer',qty=2,target=self.b.id).status_code,409)
        self.assertFalse(Transfer.objects.exists()); self.assertFalse(Movement.objects.exists())

    def test_state_count_and_scrap(self):
        self.inv(operation='in',qty=4)
        self.assertEqual(self.inv(operation='state',qty=2,target_state='维修中').status_code,200)
        self.assertEqual(Stock.objects.get(state='维修中').qty,2)
        self.assertEqual(self.inv(operation='count',qty=1,expected=4).status_code,409)
        self.assertEqual(self.inv(operation='count',qty=1,expected=2).status_code,200)
        self.assertEqual(self.inv(operation='scrap',qty=2).status_code,409)
        self.assertEqual(self.inv(operation='scrap',qty=1).status_code,200)

    def test_configuration_types_and_factory_scope(self):
        payload={'name':'草稿','factory':self.factory.id,'chip':self.chip.id,'handler':self.lb.id}
        self.assertEqual(self.post('/api/records/configurations',payload).status_code,400)
        payload.pop('handler'); self.assertEqual(self.post('/api/records/configurations',payload).status_code,201)
        other=Factory.objects.create(name='另一工厂')
        doc=Document.objects.create(name='另一厂规范',kind='LB规范',factory=other)
        v=DocumentVersion.objects.create(document=doc,revision='A',created_by=self.admin)
        payload.update(name='错误规范',norm=v.id)
        self.assertEqual(self.post('/api/records/configurations',payload).status_code,400)

    def test_version_history_upload_permission_and_duplicate(self):
        doc=Document.objects.create(name='板图',kind='LB图纸',resource=self.lb)
        for revision in ['A','B']:
            r=self.client.post('/api/versions',{'document':doc.id,'revision':revision,'status':'已发布','files':SimpleUploadedFile('board.pdf',b'%PDF-1.4\n test',content_type='application/pdf')})
            self.assertEqual(r.status_code,201,r.content)
        old=DocumentVersion.objects.get(revision='A')
        tester=Resource.objects.create(kind='测试机',name='Tester')
        config=Configuration.objects.create(name='配置',factory=self.factory,chip=self.chip,tester=tester,lb=self.lb,lb_drawing=old)
        self.assertEqual(config.lb_drawing.revision,'A')
        attachment=Attachment.objects.filter(doc_version=old).get()
        response=self.client.get(f'/api/files/document/{attachment.id}')
        self.assertEqual(response.status_code,200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
        response.close()
        self.assertEqual(Client().get(f'/api/files/document/{attachment.id}').status_code,401)
        r=self.client.post('/api/versions',{'document':doc.id,'revision':'A','files':SimpleUploadedFile('same.pdf',b'%PDF')})
        self.assertEqual(r.status_code,400)
        self.assertEqual(len(list(Path(self.temp.name).iterdir())),2)

    def test_task_progress_history_and_conflict(self):
        task=Task.objects.create(title='测试验证',category='验证',owner=self.admin)
        first=self.client.post(f'/api/tasks/{task.id}/updates',{'status':'进行中','text':'开始验证','version':1,'files':SimpleUploadedFile('note.txt',b'ok')})
        self.assertEqual(first.status_code,200,first.content)
        self.assertEqual(self.client.post(f'/api/tasks/{task.id}/updates',{'status':'已完成','text':'完成','version':1}).status_code,409)
        self.assertEqual(self.client.post(f'/api/tasks/{task.id}/updates',{'status':'已完成','text':'完成','version':2}).status_code,200)
        self.assertEqual(TaskUpdate.objects.count(),2);self.assertEqual(TaskAttachment.objects.count(),1)

    def test_used_resource_identity_cannot_be_changed(self):
        self.inv(operation='in',qty=1)
        r=self.client.put(f'/api/records/resources/{self.lb.id}',json.dumps({'version':1,'unit':'套'}),content_type='application/json')
        self.assertEqual(r.status_code,400)

    def test_last_admin_protection(self):
        r=self.client.put(f'/api/users/{self.admin.id}',json.dumps({'role':'viewer','active':True}),content_type='application/json')
        self.assertEqual(r.status_code,400)

    def test_editor_cannot_manage_users(self):
        editor=User.objects.create_user('editor',password='Editor-valid-382',is_staff=True)
        self.client.force_login(editor)
        self.assertEqual(self.post('/api/users',{'username':'unauthorized'}).status_code,403)

    def test_reused_key_different_payload_rejected(self):
        key=str(uuid.uuid4());self.inv(operation='in',qty=2,key=key)
        self.assertEqual(self.inv(operation='in',qty=4,key=key).status_code,409)
        self.assertEqual(Stock.objects.get().qty,2)

    def test_human_export_and_related_factory_search(self):
        Configuration.objects.create(name='配套方案',factory=self.factory,chip=self.chip)
        result=self.client.get('/api/export/chips',{'q':self.factory.name,'factory':self.factory.id})
        self.assertEqual(result.status_code,200)
        text=result.content.decode('utf-8-sig')
        self.assertTrue(text.startswith('芯片型号,封装形式'))
        self.assertIn(self.chip.name,text);self.assertIn(self.factory.name,text)
        self.assertNotIn('created_at',text)
        report=self.client.get('/api/data').json()['reports']['chips']
        self.assertIn(self.factory.name,report['rows'][0]['search'])

    def test_export_combined_filters_and_inactive(self):
        Task.objects.create(title='查找目标',category='验证',factory=self.factory,status='进行中',active=False)
        Task.objects.create(title='别的事项',category='制作',status='待开始')
        params={'factory':self.factory.id,'kind':'验证','status':'进行中','q':'查找'}
        text=self.client.get('/api/export/tasks',params).content.decode('utf-8-sig')
        self.assertEqual(len(text.splitlines()),1)
        text=self.client.get('/api/export/tasks',{**params,'inactive':'1'}).content.decode('utf-8-sig')
        self.assertIn('查找目标',text);self.assertNotIn('别的事项',text)

    def test_stock_export_names_and_quantity_are_not_ids(self):
        self.inv(operation='in',qty=8,location=self.b.id)
        text=self.client.get('/api/export/stocks',{'factory':self.factory.id,'status':'可用','kind':'LB'}).content.decode('utf-8-sig')
        self.assertIn('TEST-LB',text);self.assertIn('工厂仓库',text)
        self.assertIn('测试工厂',text);self.assertIn(',8,件',text)
        self.assertEqual(len(self.client.get('/api/export/stocks',{'factory':'999'}).content.decode('utf-8-sig').splitlines()),1)

    def test_export_formula_escaping_and_negative_numbers(self):
        self.factory.name='=SUM(1,2)';self.factory.save()
        text=self.client.get('/api/export/factories').content.decode('utf-8-sig')
        self.assertIn("'=SUM(1,2)",text)
        self.inv(operation='in',qty=3);self.inv(operation='scrap',qty=2)
        text=self.client.get('/api/export/movements').content.decode('utf-8-sig')
        self.assertIn(',-2,',text);self.assertNotIn("'-2",text)

    def test_task_factory_can_come_from_configuration(self):
        config=Configuration.objects.create(name='配置关联',factory=self.factory,chip=self.chip)
        Task.objects.create(title='继承工厂',category='验证',configuration=config,owner=self.admin)
        text=self.client.get('/api/export/tasks',{'factory':self.factory.id,'q':self.factory.name}).content.decode('utf-8-sig')
        self.assertIn('继承工厂',text)
        self.assertEqual(Client().get('/api/export/tasks').status_code,401)

    def test_retired_document_reference_rejected_but_history_preserved(self):
        doc=Document.objects.create(name='规范',kind='LB规范',factory=self.factory)
        version=DocumentVersion.objects.create(document=doc,revision='A',status='作废',created_by=self.admin)
        payload={'name':'新配置','factory':self.factory.id,'chip':self.chip.id,'norm':version.id}
        self.assertEqual(self.post('/api/records/configurations',payload).status_code,400)
        self.assertEqual(Configuration.objects.count(),0)
        config=Configuration.objects.create(name='历史配置',factory=self.factory,chip=self.chip,norm=version)
        response=self.client.put(f'/api/records/configurations/{config.id}',json.dumps({'version':1,'norm':version.id,'note':'保留历史'}),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        config.refresh_from_db();self.assertEqual(config.norm_id,version.id)
        version.status='已发布';version.save();doc.active=False;doc.save()
        self.assertEqual(self.post('/api/records/configurations',payload).status_code,400)

    def test_task_configuration_factory_mismatch_rejected(self):
        config=Configuration.objects.create(name='配置',factory=self.factory,chip=self.chip)
        other=Factory.objects.create(name='其他工厂')
        response=self.post('/api/records/tasks',{'title':'错误关联','category':'验证','configuration':config.id,'factory':other.id})
        self.assertEqual(response.status_code,400)
        self.assertEqual(Task.objects.count(),0)

    def test_inventory_resource_and_location_filters_match_export(self):
        self.inv(operation='in',qty=8)
        self.inv(operation='transfer',qty=3,target=self.b.id)
        other=Resource.objects.create(kind='LB',name='OTHER-LB')
        self.inv(operation='in',resource=other.id,qty=4)
        data=self.client.get('/api/data').json()
        from .reports import filter_rows
        for kind in ['stocks','transfers','movements']:
            params={'resource':str(self.lb.id),'location':str(self.a.id)}
            selected=filter_rows(data['reports'][kind]['rows'],params)
            self.assertTrue(selected)
            self.assertTrue(all(r['resource']==self.lb.id and self.a.id in r['locations'] for r in selected))
            rows=list(csv.reader(io.StringIO(self.client.get('/api/export/'+kind,params).content.decode('utf-8-sig'))))
            self.assertEqual(len(rows)-1,len(selected))
            self.assertNotIn('OTHER-LB',str(rows))
        transfers=filter_rows(data['reports']['transfers']['rows'],{'location':str(self.b.id)})
        self.assertEqual(len(transfers),1)  # Destination is also a location match.
        self.assertEqual(filter_rows(data['reports']['stocks']['rows'],{'location':'999'}),[])

    def test_task_configuration_chip_is_searchable_and_exported(self):
        config=Configuration.objects.create(name='芯片关联配置',factory=self.factory,chip=self.chip)
        Task.objects.create(title='间接芯片事项',category='验证',configuration=config)
        response=self.client.get('/api/export/tasks',{'q':self.chip.name})
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),2)
        self.assertIn(self.chip.name,rows[1])
        self.assertIn('间接芯片事项',rows[1])

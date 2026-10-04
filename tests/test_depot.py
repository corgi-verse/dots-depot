import copy
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from depot.core import (DepotError, MAX_ARCHIVE, MAX_FILE, archive_bytes, bind, canonical,
                        document, entries_checked, load_json, path_label, regular_bytes,
                        tree_digest, unpack, inspect_git, git)
from depot.catalog import build, load_catalog
from depot.client import stage, verify
from scripts.make_demo import create_demo
from scripts.publish_package import approve, approval_token
from scripts.build_site import build_site

class DepotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=tempfile.TemporaryDirectory(prefix='depot-tests-')
        cls.base=Path(cls.work.name)/'fixtures';cls.pin=create_demo(cls.base)
    @classmethod
    def tearDownClass(cls):cls.work.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='depot-case-');self.root=Path(self.temp.name)
        self.mirror=self.base/'catalog';self.package='fixture.inert-tool'
        self.manifest_data=(self.mirror/'packages'/self.package/'0.1.0.json').read_bytes()
        self.audit_data=(self.mirror/'audits'/self.package/'0.1.0.json').read_bytes()
        self.manifest=json.loads(self.manifest_data);self.audit=json.loads(self.audit_data)
    def tearDown(self):self.temp.cleanup()
    def fail_package(self,m):
        with self.assertRaises(DepotError):document(canonical(m),'package')
    def staged(self):return stage(self.mirror,self.package,'0.1.0',self.root/'private',self.pin,True)
    def cloned(self):
        dest=self.root/'mirror';shutil.copytree(self.mirror,dest);return dest
    def test_valid_documents(self):
        self.assertEqual(document(self.manifest_data,'package')['id'],self.package)
        self.assertEqual(bind(self.manifest_data,self.audit_data,True)[1]['audit']['status'],'synthetic')
    def test_every_object_rejects_unknown_fields(self):
        def objects(v,path=()):
            if isinstance(v,dict):
                yield path
                for k,item in v.items():yield from objects(item,path+(k,))
        for kind,data in [('package',self.manifest_data),('audit',self.audit_data)]:
            original=json.loads(data)
            for path in objects(original):
                value=copy.deepcopy(original);obj=value
                for key in path:obj=obj[key]
                obj['unexpected']=True
                with self.subTest(kind=kind,path=path),self.assertRaises(DepotError):document(canonical(value),kind)
    def test_every_required_package_field(self):
        for key in self.manifest:
            m=copy.deepcopy(self.manifest);del m[key];self.fail_package(m)
    def test_duplicate_and_nonfinite_json(self):
        for data in [b'{"a":1,"a":2}',b'{"n":NaN}',b'{"n":Infinity}',b'{"n":1e999}',b'\xef\xbb\xbf{}',b'{}garbage',b'\xff']:
            with self.subTest(data=data),self.assertRaises(DepotError):load_json(data)
    def test_json_limits(self):
        for data in [b' '*131073,b'['*20+b'0'+b']'*20,b'['*3000+b'0'+b']'*3000]:
            with self.assertRaises(DepotError):load_json(data)
    def test_bad_schema_version_and_fields(self):
        for key,value in [('schema','dots-depot-package/2'),('type','permission'),('version','main'),('id','../x'),('executables',['../run']),('audit','../../private')]:
            m=copy.deepcopy(self.manifest);m[key]=value;self.fail_package(m)
    def test_source_requires_exact_hashes(self):
        for key,value in [('commit','main'),('commit','a'*41),('subtree','HEAD'),('path','a/../b'),('repository','file:///private'),('repository','https://github.com/a/b?secret=x')]:
            m=copy.deepcopy(self.manifest);m['source'][key]=value;self.fail_package(m)
    def test_request_paths_and_types(self):
        for value in ['/tmp/**','../private/**','safe/../../x','safe/*/secret','safe\\x','safe/.git/config','']:
            m=copy.deepcopy(self.manifest);m['requests']['workspace_write']=[value];self.fail_package(m)
        for key,value in [('paid_services',1),('network',['http://evil.example']),('credentials',['lowercase']),('workspace_write',['a','a'])]:
            m=copy.deepcopy(self.manifest);m['requests'][key]=value;self.fail_package(m)
    def test_audit_exact_binding(self):
        for field,value in [('version','0.1.1'),('tree_sha256','0'*64),('manifest_sha256','0'*64),('package','fixture.other')]:
            audit=copy.deepcopy(self.audit);audit[field]=value
            with self.assertRaises(DepotError):bind(self.manifest_data,canonical(audit),True)
        audit=copy.deepcopy(self.audit);audit['permissions']['paid_services']=True
        with self.assertRaises(DepotError):bind(self.manifest_data,canonical(audit),True)
    def test_invalid_audit_datetime_and_count(self):
        for timestamp in ['2026-02-30T00:00:00Z','2026-01-01T00:00:00+01:00','yesterday']:
            audit=copy.deepcopy(self.audit);audit['audit']['reviewed_at']=timestamp
            with self.assertRaises(DepotError):document(canonical(audit),'audit')
        for n in [-1,True,'18']:
            audit=copy.deepcopy(self.audit);audit['verification']['tests_passed']=n
            with self.assertRaises(DepotError):document(canonical(audit),'audit')
    def test_synthetic_cannot_be_human(self):
        with self.assertRaises(DepotError):bind(self.manifest_data,self.audit_data)
        with self.assertRaises(DepotError):load_catalog(self.mirror,self.pin)
        with self.assertRaises(DepotError):build(self.base/'mirror',self.base/'approvals',self.root/'public')
    def test_no_approval_no_catalog(self):
        empty=self.root/'empty';empty.mkdir()
        pin=build(self.base/'mirror',empty,self.root/'public')
        self.assertEqual(load_catalog(self.root/'public',pin)[0]['packages'],[])
        self.assertFalse((self.root/'public/packages').exists())
    def test_approval_digest_mismatch(self):
        store=self.root/'approvals';shutil.copytree(self.base/'approvals',store)
        path=next(store.iterdir());a=json.loads(path.read_bytes());a['audit_sha256']='0'*64;path.write_bytes(canonical(a))
        with self.assertRaises(DepotError):build(self.base/'mirror',store,self.root/'public',True)
        self.assertFalse((self.root/'public').exists())
    def test_approval_wrong_commit_subtree_manifest_tree(self):
        for field in ['commit','subtree','manifest_sha256','tree_sha256']:
            with self.subTest(field=field):
                store=self.root/field;shutil.copytree(self.base/'approvals',store)
                p=next(store.iterdir());a=json.loads(p.read_bytes());a[field]='0'*len(a[field]);p.write_bytes(canonical(a))
                with self.assertRaises(DepotError):build(self.base/'mirror',store,self.root/('out-'+field),True)
    def test_submission_and_receipt_privacy(self):
        mirror=self.root/'source';shutil.copytree(self.base/'mirror',mirror)
        (mirror/'.depot').mkdir();(mirror/'.depot/receipt.json').write_text('PRIVATE CANARY')
        (mirror/'submissions').mkdir();(mirror/'submissions/not-approved.json').write_text('PRIVATE CANARY')
        build(mirror,self.base/'approvals',self.root/'public',True)
        for path in (self.root/'public').rglob('*'):
            if path.is_file():self.assertNotIn(b'PRIVATE CANARY',path.read_bytes())
        self.assertFalse((self.root/'public/.depot').exists())
    def test_immutable_output_and_releases(self):
        with self.assertRaises(DepotError):build(self.base/'mirror',self.base/'approvals',self.mirror,True)
        packet=self.base/'packets/inert-tool';mdata=(packet/'manifest.json').read_bytes();m=document(mdata,'package')
        with self.assertRaises(DepotError):approve(packet,self.base/'mirror',self.base/'approvals','Synthetic fixture simulator',approval_token(m,mdata,(packet/'report.json').read_bytes(),(packet/'source.tar').read_bytes()),0,True)
    def test_exact_confirmation_required(self):
        with self.assertRaises(DepotError):approve(self.base/'packets/inert-tool',self.root/'mirror',self.root/'approvals','Synthetic','yes',0,True)
        self.assertFalse((self.root/'approvals').exists())
    def test_catalog_pin_required_and_mismatch(self):
        for pin in [None,'0'*64,'main']:
            with self.assertRaises(DepotError):stage(self.mirror,self.package,'0.1.0',self.root/'stage',pin,True)
    def test_unknown_and_new_versions_fail_closed(self):
        for pkg,version in [(self.package,'0.1.1'),('fixture.unknown','0.1.0')]:
            with self.assertRaises(DepotError):stage(self.mirror,pkg,version,self.root/'stage',self.pin,True)
    def test_search_info_stage_verify_cli(self):
        prefix=[sys.executable,'-m','depot','--root',str(self.mirror),'--demo','--catalog-sha256',self.pin]
        for command in [['search','inert'],['info',self.package,'--version','0.1.0'],['stage',self.package,'--version','0.1.0','--destination',str(self.root/'cli')]]:
            result=subprocess.run(prefix+command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            if command[0]=='search':self.assertEqual(json.loads(result.stdout)[0]['id'],self.package)
        staged=self.root/'cli'/(self.package+'@0.1.0')
        result=subprocess.run(prefix+['verify',str(staged)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(json.loads(result.stdout)['executed'])
        bad=subprocess.run(prefix+['stage',self.package,'--version','0.2.0','--destination',str(self.root/'cli')],capture_output=True)
        self.assertEqual(bad.returncode,2)
    def test_stage_never_executes_or_preserves_execute_bits(self):
        path=self.staged();record=verify(self.mirror,path,self.pin,True)
        self.assertFalse(record['executed']);self.assertFalse((path/'content/should-never-exist').exists())
        for p in (path/'content').rglob('*'):
            if p.is_file():self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
    def test_stage_duplicate_fails(self):
        self.staged()
        with self.assertRaises(DepotError):self.staged()
    def test_one_byte_tamper(self):
        path=self.staged();p=path/'content/README.txt';p.write_bytes(p.read_bytes()+b'!')
        with self.assertRaises(DepotError):verify(self.mirror,path,self.pin,True)
    def test_extra_missing_files_and_directory(self):
        for mutation in ['extra','missing','directory']:
            with self.subTest(mutation=mutation):
                path=stage(self.mirror,self.package,'0.1.0',self.root/mutation,self.pin,True)
                if mutation=='extra':(path/'content/extra').write_text('bad')
                elif mutation=='missing':(path/'content/README.txt').unlink()
                else:(path/'content/extra').mkdir()
                with self.assertRaises(DepotError):verify(self.mirror,path,self.pin,True)
    def test_receipt_tampering_all_fields(self):
        for key in ['tree_sha256','manifest_sha256','audit_sha256','catalog_sha256','commit','subtree','package','version','executed','schema']:
            with self.subTest(key=key):
                path=stage(self.mirror,self.package,'0.1.0',self.root/key,self.pin,True)
                p=path/'receipt.json';r=json.loads(p.read_bytes());r[key]=True if key=='executed' else '0'*len(r[key]);p.write_bytes(canonical(r))
                with self.assertRaises(DepotError):verify(self.mirror,path,self.pin,True)
    def test_staging_symlinks_and_hardlinks(self):
        for mutation in ['file','dir','receipt','hardlink']:
            path=stage(self.mirror,self.package,'0.1.0',self.root/mutation,self.pin,True)
            if mutation=='dir':shutil.rmtree(path/'content');(path/'content').symlink_to(self.root)
            elif mutation=='receipt':
                data=(path/'receipt.json').read_bytes();other=self.root/'saved';other.write_bytes(data);(path/'receipt.json').unlink();(path/'receipt.json').symlink_to(other)
            else:
                target=path/'content/README.txt';target.unlink();outside=self.root/('outside-'+mutation);outside.write_text('bad');outside.chmod(0o600)
                if mutation=='file':target.symlink_to(outside)
                else:os.link(outside,target)
            with self.assertRaises(DepotError):verify(self.mirror,path,self.pin,True)
    def test_symlink_stage_parent_rejected(self):
        parent=self.root/'linked';parent.symlink_to(self.root)
        with self.assertRaises(DepotError):stage(self.mirror,self.package,'0.1.0',parent,self.pin,True)
    def test_executable_bit_tamper(self):
        path=self.staged();(path/'content/run.sh').chmod(0o700)
        with self.assertRaises(DepotError):verify(self.mirror,path,self.pin,True)
    def test_archive_tamper(self):
        root=self.cloned();p=root/'artifacts'/self.package/'0.1.0.tar';p.write_bytes(p.read_bytes()+b'!')
        with self.assertRaises(DepotError):stage(root,self.package,'0.1.0',self.root/'stage',self.pin,True)
    def test_catalog_document_tamper(self):
        root=self.cloned();p=root/'packages'/self.package/'0.1.0.json';m=json.loads(p.read_bytes());m['summary']='Changed';p.write_bytes(canonical(m))
        with self.assertRaises(DepotError):load_catalog(root,self.pin,True)
    def test_regular_bytes_rejects_symlink_device_size(self):
        p=self.root/'link';p.symlink_to('/etc/hosts')
        with self.assertRaises(DepotError):regular_bytes(p)
        with self.assertRaises(DepotError):regular_bytes('/dev/null')
        p=self.root/'large';p.write_bytes(b'x'*MAX_FILE)
        with self.assertRaises(DepotError):regular_bytes(p,100)
    def test_fifo_rejected_without_blocking(self):
        p=self.root/'fifo';os.mkfifo(p)
        with self.assertRaises(DepotError):regular_bytes(p)
    def test_unsafe_paths(self):
        for value in ['../x','/x','a/../../x','a\\b','a//b','C:/x','a/.git/config','a/.depot/private','é.txt','a\x00b','a/.']:
            with self.subTest(value=value),self.assertRaises(DepotError):path_label(value)
    def test_duplicate_and_case_collision_entries(self):
        for names in [['x','x'],['README','readme'],['A/x','a/y'],['file','file/child']]:
            with self.subTest(names=names),self.assertRaises(DepotError):archive_bytes([(n,0o644,b'x') for n in names])
    def test_modes_and_tree_limits(self):
        for entries in [[('x',0o4777,b'x')],[('x',0o644,b'x'*(MAX_FILE+1))],[(str(n),0o644,b'') for n in range(257)],[],[(str(n),0o644,b'x'*MAX_FILE) for n in range(9)]]:
            with self.assertRaises(DepotError):entries_checked(entries)
    def test_canonical_tree_order_mode_and_content(self):
        a=[('b',0o644,b''),('a',0o755,b'x')]
        self.assertEqual(tree_digest(a),tree_digest(list(reversed(a))))
        self.assertNotEqual(tree_digest(a),tree_digest([('b',0o644,b''),('a',0o644,b'x')]))
        self.assertEqual(unpack(archive_bytes(a)),sorted(a))
    def malicious_archive(self,name='x',kind=tarfile.REGTYPE,mode=0o644,pax=None):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w',format=tarfile.PAX_FORMAT if pax else tarfile.USTAR_FORMAT) as archive:
            item=tarfile.TarInfo(name);item.type=kind;item.mode=mode
            if kind==tarfile.REGTYPE:item.size=1
            if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE):item.linkname='/etc/passwd'
            if pax:item.pax_headers=pax
            archive.addfile(item,io.BytesIO(b'x') if kind==tarfile.REGTYPE else None)
        return stream.getvalue()
    def test_tar_unsafe_types_paths_headers_modes(self):
        cases=[self.malicious_archive(name=n) for n in ['../escape','/absolute','a/../../x','a/.git/config']]
        cases += [self.malicious_archive(kind=t) for t in [tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.FIFOTYPE,tarfile.DIRTYPE]]
        cases += [self.malicious_archive(mode=0o4755),self.malicious_archive(pax={'comment':'hidden'})]
        for data in cases:
            with self.assertRaises(DepotError):unpack(data)
    def test_tar_duplicate_trailing_truncated_compressed(self):
        valid=archive_bytes([('x',0o644,b'x')]);stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as a:
            for _ in range(2):
                t=tarfile.TarInfo('x');t.size=1;t.mode=0o644;a.addfile(t,io.BytesIO(b'x'))
        import gzip
        for data in [stream.getvalue(),valid+b'\0'*512,valid[:-1],valid[:512],gzip.compress(valid),valid+valid,b'x'*(MAX_ARCHIVE+1)]:
            with self.assertRaises(DepotError):unpack(data)
    def test_git_source_symlink_rejected_without_execution(self):
        repo=self.root/'source';repo.mkdir();subprocess.run(['git','init','-q',str(repo)],check=True)
        folder=repo/'parts';folder.mkdir();(folder/'link').symlink_to('/etc/passwd');subprocess.run(['git','-C',str(repo),'add','parts'],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath='+os.devnull,'commit','-qm','symlink'],check=True)
        commit=git(repo,'rev-parse','HEAD').decode().strip();subtree=git(repo,'rev-parse',commit+':parts').decode().strip();source={'commit':commit,'path':'parts','subtree':subtree}
        with self.assertRaises(DepotError):inspect_git(repo,source)
        source['subtree']='0'*40
        with self.assertRaises(DepotError):inspect_git(repo,source)
    def test_catalog_deterministic(self):
        a=build(self.base/'mirror',self.base/'approvals',self.root/'a',True);b=build(self.base/'mirror',self.base/'approvals',self.root/'b',True)
        self.assertEqual(a,b);self.assertEqual(a,self.pin)
    def test_report_integrity_rejects_truncation_and_wrong_types(self):
        for mutation in ['truncate','bool','float','declarations','schema','unknown']:
            packet=self.root/mutation;shutil.copytree(self.base/'packets/inert-tool',packet)
            p=packet/'report.json';r=json.loads(p.read_bytes())
            if mutation=='truncate':r={k:r[k] for k in ['manifest_sha256','tree_sha256','source','synthetic','findings']}
            elif mutation=='bool':r['tests_executed']=0
            elif mutation=='float':r['files'][0]['bytes']=float(r['files'][0]['bytes'])
            elif mutation=='declarations':r['requests']['paid_services']=True
            elif mutation=='schema':r['schema']='dots-depot-inspection/2'
            else:r['unknown']='field'
            p.write_bytes(canonical(r));mdata=(packet/'manifest.json').read_bytes();m=document(mdata,'package')
            token=approval_token(m,mdata,p.read_bytes(),(packet/'source.tar').read_bytes())
            with self.subTest(mutation=mutation),self.assertRaises(DepotError):approve(packet,self.root/('mirror-'+mutation),self.root/('approvals-'+mutation),'Synthetic simulator',token,0,True)
    def test_unverified_test_count_rejected(self):
        packet=self.base/'packets/inert-tool';data=(packet/'manifest.json').read_bytes();m=document(data,'package')
        token=approval_token(m,data,(packet/'report.json').read_bytes(),(packet/'source.tar').read_bytes())
        with self.assertRaises(DepotError):approve(packet,self.root/'mirror',self.root/'approvals','Synthetic simulator',token,999,True)
    def test_confirmation_binds_report_archive_and_test_evidence(self):
        packet=self.base/'packets/inert-tool';data=(packet/'manifest.json').read_bytes();m=document(data,'package');report=(packet/'report.json').read_bytes();archive=(packet/'source.tar').read_bytes()
        original=approval_token(m,data,report,archive)
        self.assertNotEqual(original,approval_token(m,data,report+b' ',archive))
        self.assertNotEqual(original,approval_token(m,data,report,archive+b' '))
        self.assertNotEqual(original,approval_token(m,data,report,archive,b'CI'))
    def test_audit_test_evidence_tuple(self):
        for changes in [{'tests_passed':18},{'tests_status':'human-reviewed-ci'},{'tests_sha256':'0'*64},{'tests_status':'human-reviewed-ci','tests_passed':18}]:
            a=copy.deepcopy(self.audit);a['verification'].update(changes)
            with self.assertRaises(DepotError):document(canonical(a),'audit')
    def test_catalog_rejects_unknown_fields_types_and_mode(self):
        for mutation in ['top','entry','type','mode']:
            root=self.root/mutation;shutil.copytree(self.mirror,root);p=root/'catalog/index.json';c=json.loads(p.read_bytes())
            if mutation=='top':c['unknown']=True
            elif mutation=='entry':c['packages'][0]['unknown']=True
            elif mutation=='type':c['packages'][0]['type']='permission'
            else:c['mode']='trusted'
            p.write_bytes(canonical(c))
            with self.assertRaises(DepotError):load_catalog(root,allow_synthetic=True)
    def test_git_blob_output_is_bounded(self):
        repo=self.root/'large-source';repo.mkdir();subprocess.run(['git','init','-q',str(repo)],check=True)
        payload=b'x'*(MAX_FILE+1)
        blob=subprocess.run(['git','-C',str(repo),'hash-object','-w','--stdin'],input=payload,capture_output=True,check=True).stdout.decode().strip()
        with self.assertRaises(DepotError):git(repo,'cat-file','blob',blob)
    def test_output_overlap_rejected_after_system_alias_normalization(self):
        with self.assertRaises(DepotError):build(self.base/'mirror',self.base/'approvals',self.base/'mirror/public',True)
        self.assertFalse((self.base/'mirror/public').exists())
    def test_long_ustar_name_fails_cleanly(self):
        with self.assertRaises(DepotError):archive_bytes([('x'*101,0o644,b'x')])
    def test_site_build_preserves_approval_gate(self):
        with self.assertRaises(DepotError):build_site(self.root/'public',self.base/'mirror',self.base/'approvals')
        self.assertFalse((self.root/'public').exists())
    def test_site_build_requires_paired_maintainer_inputs(self):
        with self.assertRaises(DepotError):build_site(self.root/'public',self.base/'mirror')
        self.assertFalse((self.root/'public').exists())

if __name__=='__main__':unittest.main()

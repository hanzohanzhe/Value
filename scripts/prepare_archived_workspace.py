"""Prepare a same-Linux-host archived VALUE workspace; never start a Run."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import platform
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from gridform_core.execution_archive import materialize_execution_bundle, verify_execution_bundle
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity
from gridform_core.runtime_paths import user_data_root
from gridform_core.run_policy import resolve_run_policy

class PreparationError(ValueError):
    pass

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def safe(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise PreparationError('Paths must be absolute without traversal')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PreparationError('Symbolic links are not accepted')
    return path

def copy_tree(source, destination):
    source = safe(source)
    if not source.is_dir(): raise PreparationError(f'Missing directory: {source}')
    for path in source.rglob('*'):
        safe(path)
        if not path.is_dir() and not path.is_file(): raise PreparationError('Only regular files are supported')
    shutil.copytree(source, destination)

def read(path):
    safe(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict): raise PreparationError('Expected JSON object')
    return value

def review(*, run_id, data_home):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', run_id): raise PreparationError('Invalid Run ID')
    data_home = safe(Path(data_home))
    root = data_home / 'runs' / run_id
    status = read(root / 'status.json')
    record = read(root / 'execution-bundle.json')
    integrity = verify_frozen_input_integrity(root / 'input-snapshot')
    for key, expected in {'id':run_id, 'project_id':integrity['project']['id'], 'input_snapshot_id':integrity['snapshot_id'], 'input_tree_sha256':integrity['input_tree_sha256']}.items():
        if status.get(key) != expected: raise PreparationError(f'Status identity mismatch: {key}')
    if status.get('status') not in {'completed','failed','cancelled','archived'}: raise PreparationError('Run must be terminal')
    scope=resolve_run_policy(str(status.get('mode') or '')).to_dict(integrity['project'])
    for key in ('mode','start_year','end_year','periods_per_year','total_periods'):
        if (status.get('run_policy') or {}).get(key) != scope.get(key): raise PreparationError('Frozen execution scope mismatch: '+key)
    if not integrity['declaration_evidence']['complete']: raise PreparationError('Historical method declaration evidence is incomplete')
    ref = integrity['project'].get('extensions', {}).get('execution_bundle', {})
    if ref.get('record_sha256') != canonical(record) or ref.get('identity_sha256') != record.get('identity_sha256'):
        raise PreparationError('Frozen execution reference mismatch')
    metadata = record['environment']['metadata']
    if platform.system() != 'Linux' or platform.machine() not in {'x86_64','AMD64'} or metadata.get('machine') != platform.machine() or metadata.get('platform_release') != platform.release() or metadata.get('platform') != 'Linux':
        raise PreparationError('Only matching Linux x86-64 hosts are supported')
    if not all(record.get(k) is True for k in ('identity_complete','native_closure_complete','archive_complete')): raise PreparationError('Complete historical execution archive is required')
    verify_execution_bundle(record, archive_root=data_home / 'execution-archives')
    host = []
    for row in record['environment']['files']:
        if row['path'].startswith('system-libraries/') and str(row['origin']).startswith(('/usr/lib/', '/lib/')):
            path = safe(Path(row['origin']))
            if not path.is_file() or digest(path) != row['sha256']: raise PreparationError(f'Host ELF differs: {path}')
            host.append({'path':str(path),'sha256':row['sha256'],'evidence':'recorded_elf'})
    result={'schema_version':'value.archived-workspace-review/v1','run_id':run_id,'source_snapshot_id':integrity['snapshot_id'],'input_tree_sha256':integrity['input_tree_sha256'],'status_sha256':canonical(status),'record_sha256':canonical(record),'identity_sha256':record['identity_sha256'], 'identity_complete':record['identity_complete'],'native_closure_complete':record['native_closure_complete'],'archive_complete':record['archive_complete'],'limitations':record.get('limitations',[]),'host_dependencies':host,'scope':status.get('run_policy'),'executed':False}
    result['review_sha256']=canonical(result)
    result['execution_record']=record
    return result

def assert_review_matches(expected, actual):
    if expected.get('review_sha256') != actual.get('review_sha256'):
        raise PreparationError('Run or archived evidence changed since review; review again')

BOOTSTRAP = r'''
import json,sys
from pathlib import Path
from backend import server
from backend.frozen_run_recovery import publish_frozen_recovery
root=server.RUNS_ROOT/sys.argv[1]
report,_=server._review_frozen_recovery(root,'strict')
if not report.get('allowed'): raise RuntimeError(json.dumps(report))
result=publish_frozen_recovery(root,{'name':sys.argv[2],'acknowledge':True,'recovery_mode':'strict','review_sha256':report['review_sha256']},review=server._review_frozen_recovery,projects_root=server.PROJECTS_ROOT,packs_root=server.PACKS_ROOT,network_packs_root=server.STATE_ROOT/'data-workbench'/'installed-packs',staging_root=server.STATE_ROOT/'frozen-recovery-staging',registry=server.MODULE_REGISTRY,validate_project=server.validate_project,revision_manifest=server._revision_manifest,is_reserved=lambda sid:server.study_id_is_reserved(sid,projects_root=server.PROJECTS_ROOT,trash_root=server.TRASH_ROOT))
Path(sys.argv[3]).write_text(json.dumps({'review':report,'created':result},indent=2))
'''

def launcher_module():
    path = REPO / 'packaging/linux-local/archived_value.py'
    spec = importlib.util.spec_from_file_location('archived_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def prepare(*, run_id, data_home, destination, node, name, acknowledge_code=False, review_sha256=None):
    if not acknowledge_code: raise PreparationError('prepare requires --acknowledge-code: archived Python and installed methods will execute')
    destination = safe(Path(destination)); node = safe(Path(node))
    if destination.exists(): raise PreparationError('Destination must not exist')
    for protected in (safe(Path(data_home)),REPO):
        if destination.is_relative_to(protected): raise PreparationError('Destination must be outside original state and source repository')
    if not destination.parent.is_dir(): raise PreparationError('Destination parent directory must already exist')
    if not node.is_file(): raise PreparationError('An installed Node executable is required')
    if not name.strip() or len(name) > 160: raise PreparationError('Name must contain 1–160 characters')
    node_probe=subprocess.run([str(node),'-p',"JSON.stringify({version:process.versions.node,platform:process.platform,arch:process.arch})"],capture_output=True,text=True,timeout=15,env={'PATH':'/usr/bin:/bin'})
    if node_probe.returncode: raise PreparationError('Installed Node runtime probe failed')
    node_info=json.loads(node_probe.stdout)
    if node_info.get('platform')!='linux' or node_info.get('arch')!='x64' or tuple(int(x) for x in node_info['version'].split('.')[:2]) < (22,13): raise PreparationError('Node >=22.13 on Linux x64 is required')
    report = review(run_id=run_id, data_home=data_home)
    if not review_sha256 or review_sha256 != report['review_sha256']: raise PreparationError('Required --review-sha256 is missing or stale; review again')
    record = report['execution_record']; source_run = Path(data_home) / 'runs' / run_id
    destination.mkdir()
    try:
        materialization = materialize_execution_bundle(record, archive_root=Path(data_home)/'execution-archives', destination=destination/'capsule')
        state = destination/'state'; run = state/'runs'/run_id; run.mkdir(parents=True)
        for filename in ('status.json','execution-bundle.json'): shutil.copyfile(safe(source_run/filename), run/filename)
        copy_tree(source_run/'input-snapshot', run/'input-snapshot')
        archive_root = state/'execution-archives'
        for kind in ('source','environment'):
            rel = record[kind]['artifact']['path']
            if Path(rel).is_absolute() or '..' in Path(rel).parts: raise PreparationError('Invalid CAS object path')
            target = archive_root/rel; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(safe(Path(data_home)/'execution-archives'/rel),target)
        modules = destination/'capsule/source/modules'
        if modules.exists(): copy_tree(modules,state/'modules')
        assert_review_matches(report,review(run_id=run_id,data_home=state))
        assert_review_matches(report,review(run_id=run_id,data_home=data_home))
        ui = destination/'ui'; ui.mkdir()
        copy_tree(REPO/'dist',ui/'dist')
        for package in ('vinext','react','react-dom','react-server-dom-webpack','scheduler'):
            copy_tree(REPO/'node_modules'/package,ui/'node_modules'/package)
        (ui/'scripts').mkdir()
        for script in ('serve-value-ui.mjs','value-ui-gateway.mjs'): shutil.copyfile(REPO/'scripts'/script,ui/'scripts'/script)
        tools=destination/'tools'; tools.mkdir(); shutil.copyfile(REPO/'packaging/linux-local/archived_value.py',tools/'archived_value.py')
        deps=report['host_dependencies'][:]
        for filename in ('/usr/lib/locale/locale-archive','/usr/lib/locale/C.utf8/LC_CTYPE','/usr/lib/x86_64-linux-gnu/gconv/gconv-modules.cache'):
            path=Path(filename)
            if path.is_file(): deps.append({'path':filename,'sha256':digest(path),'evidence':'prepared_locale'})
        config={'schema_version':'value.archived-workspace/v1','prefix':str(destination),'identity_sha256':record['identity_sha256'],'execution_record':record,'archive_root':str(archive_root),'source_root':materialization['source_root'],'capsule_root':str(destination/'capsule'),'data_home':str(state),'ui_root':str(ui),'python_executable':None,'node_runtime':node_info,'node_executable':str(node),'project_id':None,'api_port':8766,'ui_port':8800,'environment':{'PATH':str(destination/'capsule/environment/runtime/bin')+':/usr/bin:/bin','PYTHONUSERBASE':str(destination/'empty-user-site')},'host_dependencies':deps,'same_host':True,'fully_isolated':False,'control_inventory':[]}
        config['python_executable']=launcher_module().archived_path(record,config['capsule_root'],record['environment']['metadata']['python_executable'])
        config['host_dependencies'].append({'path':str(node),'sha256':digest(node),'evidence':'prepared_ui_runtime'})
        for base in (ui,tools):
            config['control_inventory'] += [{'path':str(p.relative_to(destination)),'sha256':digest(p)} for p in sorted(base.rglob('*')) if p.is_file()]
        (destination/'workspace.json').write_text(json.dumps(config,indent=2)+'\n')
        launcher=launcher_module()
        config['prepared_host_environment']={key:os.environ.get(key) for key in launcher.HOST_ENV}
        (destination/'workspace.json').write_text(json.dumps(config,indent=2)+'\n')
        probe=launcher.probe_workspace(config,check_inputs=False)
        output=destination/'preparation-result.json'
        completed=subprocess.run(launcher.archived_python_command(config,'-c',BOOTSTRAP,run_id,name,str(output)),cwd=config['source_root'],env=launcher.archived_environment(config),capture_output=True,text=True,timeout=180)
        (destination/'preparation.log').write_text(completed.stdout+'\n'+completed.stderr)
        if completed.returncode: raise PreparationError('Archived strict recovery failed; '+completed.stderr[-3000:])
        created=read(output); config['project_id']=created['created']['project']['id']
        bindir=destination/'bin'; bindir.mkdir()
        for action in ('start','stop','diagnose'):
            path=bindir/(''+action+'-archived-value')
            path.write_text('#!/bin/sh\nexec '+shlex_quote(config['python_executable'])+' -B '+shlex_quote(str(tools/'archived_value.py'))+' '+action+' --prefix '+shlex_quote(str(destination))+' "$@"\n'); path.chmod(0o755)
        config['control_inventory']=[]
        for base in (ui,tools,bindir):
            config['control_inventory'] += [{'path':str(p.relative_to(destination)),'sha256':digest(p)} for p in sorted(base.rglob('*')) if p.is_file()]
        config['preparation']={'source_run_id':run_id,'original_identity_sha256':record['identity_sha256'],'probe':probe,'scope':report['scope'],'limitations':report['limitations']+['Compatible same-host ELF and prepared locale resources are required; this is not full isolation.']}
        (destination/'workspace.json').write_text(json.dumps(config,indent=2)+'\n')
        (destination/'README.md').write_text('VALUE archived workspace\n\nSame Linux x86-64 host only. Source and Python bytes are independent; matching host ELF and prepared locale resources are required. This is not a fully isolated environment or cross-OS release. Historical evidence remains unchanged. The UI is a current control surface; scientific code is the archived source.\n\nStart: '+str(bindir/'start-archived-value')+'\nDiagnose: '+str(bindir/'diagnose-archived-value')+'\nStop: '+str(bindir/'stop-archived-value')+'\n\nPreparation created a Study and did not start any service or Run. Do not edit capsule files: diagnosis and strict execution verify the recorded identity.\n')
        return config
    except BaseException:
        shutil.rmtree(destination)
        raise

def shlex_quote(value):
    import shlex
    return shlex.quote(value)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('review','prepare'))
    parser.add_argument('--run-id',required=True); parser.add_argument('--data-home',type=Path,default=user_data_root())
    parser.add_argument('--destination',type=Path); parser.add_argument('--node',type=Path); parser.add_argument('--name',default='Archived recovery')
    parser.add_argument('--acknowledge-code',action='store_true'); parser.add_argument('--review-sha256')
    args=parser.parse_args()
    try:
        if args.action=='review': result=review(run_id=args.run_id,data_home=args.data_home)
        else:
            if args.destination is None or args.node is None: parser.error('prepare needs --destination and --node')
            result=prepare(run_id=args.run_id,data_home=args.data_home,destination=args.destination,node=args.node,name=args.name,acknowledge_code=args.acknowledge_code,review_sha256=args.review_sha256)
        summary={k:result[k] for k in ('schema_version','run_id','review_sha256','source_snapshot_id','input_tree_sha256','status_sha256','record_sha256','identity_sha256','identity_complete','native_closure_complete','archive_complete','scope','limitations','executed','prefix','source_root','data_home','project_id','same_host','fully_isolated') if k in result}
        if 'execution_record' in result:
            summary['archive_bytes']={k:result['execution_record'][k]['artifact']['bytes'] for k in ('source','environment')}
            for key in ('identity_complete','native_closure_complete','archive_complete'):
                summary[key]=result['execution_record'][key]
        if 'preparation' in result:
            summary['scope']=result['preparation']['scope']; summary['limitations']=result['preparation']['limitations']
        if 'prefix' in result: summary['commands']={k:str(Path(result['prefix'])/'bin'/(k+'-archived-value')) for k in ('start','stop','diagnose')}
        print(json.dumps(summary,indent=2))
    except Exception as error:
        print(str(error),file=sys.stderr); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())

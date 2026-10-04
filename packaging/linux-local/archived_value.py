#!/usr/bin/env python3
"""Same-host Linux archive launcher; uses archived backend and Python, never a new scientific runner."""
from __future__ import annotations
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import socket
import subprocess
import time
import urllib.request
import uuid
from urllib.parse import urlencode

HOST_ENV = ('LANG','LANGUAGE','LC_ALL','LC_CTYPE','LC_NUMERIC','LC_TIME','LC_COLLATE','LC_MONETARY','LC_MESSAGES','LC_PAPER','LC_NAME','LC_ADDRESS','LC_TELEPHONE','LC_MEASUREMENT','LC_IDENTIFICATION','LOCPATH','GCONV_PATH')
SCHEMA = "value.archived-workspace/v1"
LOADER = ('LD_LIBRARY_PATH','LD_PRELOAD','LD_AUDIT','LD_BIND_NOW','LD_HWCAP_MASK','LD_ORIGIN_PATH','LD_ASSUME_KERNEL','LD_PREFER_MAP_32BIT_EXEC','GLIBC_TUNABLES','DYLD_LIBRARY_PATH','DYLD_FALLBACK_LIBRARY_PATH','DYLD_INSERT_LIBRARIES','DYLD_FRAMEWORK_PATH','DYLD_FALLBACK_FRAMEWORK_PATH','DYLD_FORCE_FLAT_NAMESPACE')
SEMANTIC = ('PYTHONOPTIMIZE','PYTHONHASHSEED','PYTHONUTF8','PYTHONCOERCECLOCALE','PYTHONINTMAXSTRDIGITS','PYTHONWARNINGS')
THREAD = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','OMP_DYNAMIC','MKL_DYNAMIC','PYTHONHASHSEED')

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while block := handle.read(1024 * 1024): digest.update(block)
    return digest.hexdigest()

def read(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict): raise ValueError('Expected an object: ' + str(path))
    return value

def write(path, value):
    path = Path(path); temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8'); temporary.replace(path)

def regular(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)): raise ValueError('Symbolic link in managed path: ' + str(path))
    return path

def inside(prefix, raw):
    path = regular(raw); path.relative_to(prefix)
    return path

def key(raw):
    if not isinstance(raw, str) or not raw or '\\' in raw or '\0' in raw: raise ValueError('Invalid inventory path')
    value = PurePosixPath(raw)
    if value.is_absolute() or any(part in ('..', '.') for part in raw.split('/')): raise ValueError('Unsafe inventory path')
    return value

def archived_path(record, capsule_root, origin, *, kind='environment'):
    """Map an original absolute file via recorded roots, never guess bin/python."""
    original = Path(origin)
    matches = []
    for row in record[kind]['roots']:
        root = Path(row.get('resolved_origin') or row['origin'])
        try: relative = original.relative_to(root)
        except ValueError: continue
        matches.append((len(root.parts), Path(capsule_root) / kind / key(row['path']) / relative))
    if not matches: raise ValueError('Original path is outside archive roots: ' + str(origin))
    return str(max(matches, key=lambda item: item[0])[1])

def load_workspace(prefix):
    prefix = regular(Path(prefix).absolute())
    config = read(regular(prefix / 'workspace.json'))
    if config.get('schema_version') != SCHEMA or config.get('prefix') != str(prefix): raise ValueError('Workspace identity/prefix mismatch')
    if config.get('same_host') is not True or config.get('fully_isolated') is not False: raise ValueError('Only explicit same-host workspaces are supported')
    if config.get('api_port') != 8766 or config.get('ui_port') not in (8800,18800): raise ValueError('Unsupported service ports')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64','AMD64'): raise ValueError('Archive execution supports Linux x86-64 only')
    for name in ('capsule_root','source_root','data_home','ui_root','archive_root','python_executable'):
        inside(prefix, config[name])
    if Path(config['source_root']) != prefix / 'capsule/source/app' or Path(config['data_home']) != prefix / 'state': raise ValueError('Unexpected workspace layout')
    record = config['execution_record']
    if not isinstance(record, dict) or record.get('identity_sha256') != config.get('identity_sha256') or not all(record.get(field) is True for field in ('identity_complete','native_closure_complete','archive_complete')): raise ValueError('Complete matching execution archive is required')
    metadata = record['environment']['metadata']
    if metadata.get('platform') != platform.system() or metadata.get('machine') != platform.machine() or metadata.get('platform_release') != platform.release(): raise ValueError('Recorded archive requires the same host platform/kernel')
    expected_python = archived_path(record, config['capsule_root'], metadata['python_executable'])
    if config['python_executable'] != expected_python: raise ValueError('Interpreter does not match recorded roots')
    archived_python_command(config, '-c', 'pass')
    return config

def archived_environment(config):
    env = dict(os.environ)
    for name in (*LOADER,*SEMANTIC,*THREAD,'PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE','PYTHONUSERBASE','PYTHONSTARTUP','PYTHONINSPECT','PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE','NODE_OPTIONS','NODE_PATH'):
        env.pop(name, None)
    transport = config.get('environment', {})
    if not isinstance(transport, dict) or set(transport) - {'PYTHONUSERBASE','PATH'}: raise ValueError('Unknown transport environment field')
    for name, value in transport.items():
        if not isinstance(value, str): raise ValueError('Transport environment values must be strings')
        if name == 'PYTHONUSERBASE':
            for part in value.split(os.pathsep):
                if not part: raise ValueError('Empty controlled Python import/home path')
                inside(Path(config['prefix']), part)
        env[name] = value
    host_env = config.get('prepared_host_environment')
    if not isinstance(host_env,dict) or set(host_env) != set(HOST_ENV): raise ValueError('Missing prepared host locale environment')
    for name in HOST_ENV:
        value = host_env[name]
        if value is None: env.pop(name,None)
        elif isinstance(value,str): env[name]=value
        else: raise ValueError('Invalid prepared host environment')
    metadata = config['execution_record']['environment']['metadata']
    imports = metadata.get('import_paths')
    if not isinstance(imports,list) or not all(isinstance(row,dict) for row in imports): raise ValueError('Missing recorded import paths')
    workspace_count = sum(row.get('path') == 'workspace' for row in imports)
    if workspace_count not in (1,2): raise ValueError('Unsupported recorded workspace import multiplicity')
    if workspace_count == 2:
        # -c's empty cwd and -m's absolute cwd both map to workspace. Restore
        # only this recorded duplicate, never accept arbitrary user PYTHONPATH.
        env['PYTHONPATH'] = str(inside(Path(config['prefix']),config['source_root']))
    for field, allowed in (('loader_environment',LOADER),('python_semantic_environment',SEMANTIC),('thread_environment',THREAD)):
        values = metadata.get(field)
        if not isinstance(values, dict) or set(values) - set(allowed): raise ValueError('Invalid recorded environment group: ' + field)
        for name in allowed:
            value = values.get(name)
            if value is not None and not isinstance(value, str): raise ValueError('Invalid recorded environment value')
            if value is None: env.pop(name, None)
            else: env[name] = value
    # A controlled empty home avoids user site imports without changing no_user_site flags.
    home = inside(Path(config['prefix']), Path(config['prefix']) / 'empty-home'); home.mkdir(exist_ok=True)
    env.update(HOME=str(home), VALUE_DATA_HOME=config['data_home'])
    return env

def archived_python_command(config, *arguments):
    flags = config['execution_record']['environment']['metadata'].get('python_semantic_flags')
    if not isinstance(flags, dict): raise ValueError('Missing recorded interpreter flags')
    supported = {'optimize','hash_randomization','utf8_mode','safe_path','isolated','ignore_environment','no_user_site','bytes_warning'}
    if set(flags) - supported: raise ValueError('Unsupported recorded Python flag')
    for name in ('isolated','ignore_environment','safe_path'):
        if flags.get(name) not in (None,0): raise ValueError('Unsupported recorded Python flag: ' + name)
    result = [config['python_executable'],'-B','-X',f"pycache_prefix={Path(config['prefix']) / 'unused-bytecode-cache'}"]
    optimize, utf8, no_site, warning = (flags.get(name) for name in ('optimize','utf8_mode','no_user_site','bytes_warning'))
    if optimize not in (0,1,2) or utf8 not in (0,1) or no_site not in (0,1) or warning not in (0,1,2) or flags.get('hash_randomization') not in (0,1): raise ValueError('Unsupported recorded interpreter flags')
    if optimize: result.append('-' + 'O'*optimize)
    result += ['-X', 'utf8=' + str(utf8)]
    if no_site: result.append('-s')
    if warning: result.append('-' + 'b'*warning)
    return result + list(arguments)

def verify_files(config):
    prefix = Path(config['prefix']); record = config['execution_record']
    for kind in ('source','environment'):
        base = Path(config['capsule_root']) / kind; expected = set()
        for row in record[kind]['files']:
            path = inside(prefix, base / key(row['path'])); expected.add(path)
            if kind == 'source' and row['path'].startswith('modules/'):
                installed = inside(prefix, Path(config['data_home']) / key(row['path']))
                if not installed.is_file() or sha(installed) != row['sha256']: raise ValueError('Archived external source/record differs in independent state')
            if not path.is_file() or path.stat().st_size != row['bytes'] or sha(path) != row['sha256'] or (path.stat().st_mode & 0o777) != row['mode']: raise ValueError('Archive materialization changed: ' + str(path))
        observed = {regular(path) for path in base.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo','.log')}
        if observed != expected: raise ValueError('Unrecorded file in archive materialization')
    inventory = config.get('control_inventory')
    if not isinstance(inventory,list) or not inventory: raise ValueError('Missing UI/control inventory')
    expected = set()
    for row in inventory:
        path = inside(prefix, prefix / key(row['path']))
        if path in expected or not path.is_file() or sha(path) != row['sha256']: raise ValueError('UI/control inventory mismatch')
        expected.add(path)
    for folder in ('ui','tools','bin'):
        observed = {regular(path) for path in (prefix / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo')}
        if not observed.issubset(expected): raise ValueError('Unrecorded UI/control file')
    dependencies = config.get('host_dependencies')
    if not isinstance(dependencies,list): raise ValueError('Missing host dependency evidence')
    pinned = {}
    for row in dependencies:
        if row.get('evidence') not in ('recorded_elf','prepared_locale','prepared_ui_runtime'): raise ValueError('Unknown host dependency evidence')
        path = Path(row['path'])
        if not path.is_absolute() or not path.is_file() or sha(path) != row['sha256']: raise ValueError('Host dependency changed: ' + str(path))
        pinned[(str(path),row['sha256'])] = row['evidence']
    managed_origins = [Path(row.get('resolved_origin') or row['origin']) for row in record['environment']['roots'] if not row['path'].startswith('system-libraries/')]
    for row in record['environment']['files']:
        if row['path'].startswith('system-libraries/') and not any(Path(row['origin']).is_relative_to(origin) for origin in managed_origins) and pinned.get((row['origin'],row['sha256'])) != 'recorded_elf': raise ValueError('Recorded host ELF dependency is not pinned')
    if not any(row['evidence'] == 'prepared_locale' for row in dependencies): raise ValueError('Prepared locale/gconv evidence is required')
    if not any(path == Path(config['node_executable']) for path in expected) and pinned.get((config['node_executable'],sha(config['node_executable']))) is None: raise ValueError('UI Node executable is not pinned')

PROBE = r'''
import json,sys,os,importlib,importlib.util,subprocess
from pathlib import Path
from backend.run_execution import current_execution
from backend.frozen_run_recovery import verify_recovered_configuration,verify_recovered_inputs,recovery_guard
from gridform_core.execution_archive import verify_execution_bundle
c=json.loads(Path(sys.argv[1]).read_text())
verify_execution_bundle(c['execution_record'],archive_root=Path(c['archive_root']))
loaded={}
for name in ('backend.server','backend.model_runner','gridform_core','numpy','scipy','scipy.optimize._highs._highs_wrapper'):
    m=importlib.import_module(name); loaded[name]=str(Path(m.__file__).resolve())
flags=c['execution_record']['environment']['metadata']['python_semantic_flags']
worker_code="import json,sys;print(json.dumps({k:getattr(sys.flags,k,None) for k in " + repr(list(flags)) + "}))"
worker=subprocess.run([sys.executable,'-B','-X','pycache_prefix='+str(Path(c['prefix'])/'unused-bytecode-cache'),'-c',worker_code],cwd=c['source_root'],capture_output=True,text=True,check=True)
worker_flags=json.loads(worker.stdout)
if worker_flags != flags: raise ValueError('Archived backend worker command cannot preserve recorded Python flags')
r=current_execution(source_root=Path(c['source_root']),data_home=Path(c['data_home']))
if r['identity_sha256'] != c['identity_sha256']: raise ValueError('Archived execution identity does not match recorded source/environment')
if sys.argv[2]=='true':
    p=json.loads((Path(c['data_home'])/'projects'/c['project_id']/'project.json').read_text())
    if recovery_guard(p) is None: raise ValueError('Independent Study has no frozen input guard')
    verify_recovered_configuration(p,execution_identity=r['identity_sha256'])
    base=Path(c['data_home'])/'data-packs'/p['data_pack_id']
    server=importlib.import_module('backend.server')
    selection=server.resolve_zonal_pack_selection(p,base_pack_root=base,data_home=Path(c['data_home']))
    verify_recovered_inputs(p,base,selection.network_pack_root)
maps=[]
for line in Path('/proc/self/maps').read_text().splitlines():
    pieces=line.split(None,5)
    if len(pieces)==6 and pieces[5].startswith('/') and pieces[5] not in maps: maps.append(pieces[5])
print(json.dumps({'identity_sha256':r['identity_sha256'],'python_executable':str(Path(sys.executable).resolve()),'sys_prefix':sys.prefix,'sys_base_prefix':sys.base_prefix,'source_root':c['source_root'],'import_paths':sys.path,'loaded_modules':loaded,'loaded_elf_paths':maps,'metadata':r['environment']['metadata'],'worker_python_flags':worker_flags}))
'''

def probe_workspace(config, *, check_inputs=True):
    verify_files(config)
    checked = subprocess.run(archived_python_command(config,'-c',PROBE,str(Path(config['prefix'])/'workspace.json'),'true' if check_inputs else 'false'),cwd=config['source_root'],env=archived_environment(config),capture_output=True,text=True,timeout=240)
    if checked.returncode: raise ValueError('Archived execution probe failed: ' + checked.stderr[-12000:])
    proof = json.loads(checked.stdout)
    prefix = Path(config['prefix']); capsule = Path(config['capsule_root'])
    for name in ('python_executable','sys_prefix','sys_base_prefix'):
        Path(proof[name]).resolve().relative_to(capsule/'environment')
    for name, raw in proof['loaded_modules'].items():
        Path(raw).relative_to(capsule / ('source' if name.startswith(('backend','gridform_core')) else 'environment'))
    external_roots = [Path(config['data_home']) / key(row['path']) for row in config['execution_record']['source']['roots'] if row['path'].startswith('modules/') and row['path'].endswith('/src')]
    for raw in proof['import_paths']:
        actual=Path(raw or config['source_root']).resolve()
        if not actual.is_relative_to(capsule) and not any(actual == source.resolve() for source in external_roots): raise ValueError('Import path is outside verified archive/installed sources: '+str(actual))
    pinned = {row['path'] for row in config['host_dependencies']}
    for raw in proof['loaded_elf_paths']:
        try: Path(raw).relative_to(capsule)
        except ValueError:
            if raw not in pinned: raise ValueError('Unpinned host library loaded: ' + raw)
    proof.update(schema_version='value.archived-workspace-proof/v1',same_host=True,fully_isolated=False,host_dependencies=config['host_dependencies'],prepared_host_environment=config['prepared_host_environment'],host_locale_evidence='prepared_same_host_not_historical',ui_scientific_source=False)
    (prefix/'diagnostics').mkdir(exist_ok=True); write(prefix/'diagnostics/proof.json',proof)
    return proof

def process_info(pid):
    try:
        folder=Path('/proc')/str(pid); stat=(folder/'stat').read_text().rsplit(')',1)[1].split()
        return {'start_time':stat[19],'group':int(stat[2]),'state':stat[0],'argv':(folder/'cmdline').read_bytes().rstrip(b'\0').split(b'\0'),'environment':(folder/'environ').read_bytes().split(b'\0')}
    except (OSError,ValueError,IndexError): return None

def owned(entry,token):
    actual=process_info(entry['pid'])
    return bool(actual and actual['state']!='Z' and actual['group']==entry['pid'] and actual['start_time']==entry['start_time'] and actual['argv']==[v.encode() for v in entry['argv']] and f'VALUE_LOCAL_INSTANCE={token}'.encode() in actual['environment'])

def stop_record(record):
    live=[]
    for entry in record['processes'].values():
        info=process_info(entry['pid'])
        if not info or info['state']=='Z': continue
        if not owned(entry,record['token']): raise ValueError('Process ownership changed; refusing to stop another instance')
        live.append(entry)
    for entry in live:
        if not owned(entry,record['token']): raise ValueError('Process ownership changed before signaling')
        os.killpg(entry['pid'],signal.SIGTERM)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline and any(owned(e,record['token']) for e in live): time.sleep(.1)
    for entry in live:
        if owned(entry,record['token']): os.killpg(entry['pid'],signal.SIGKILL)

def health(port,path):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=2) as response: return response.status==200
    except (OSError,ValueError): return False

def workspace_url(config):
    return f"http://127.0.0.1:{config['ui_port']}/?" + urlencode({'view':'run','study':config['project_id']})

def start(prefix,config):
    record_path=prefix/'processes.json'
    if record_path.exists():
        previous=read(record_path)
        if previous.get('prefix') != str(prefix): raise ValueError('Process record prefix mismatch')
        if previous.get('processes') and all(owned(e,previous['token']) for e in previous['processes'].values()):
            probe_workspace(config); return {'status':'already_started','ui':workspace_url(config),'source_execution_identity_sha256':config['identity_sha256'],'same_host':True,'fully_isolated':False}
        if any((info:=process_info(e['pid'])) and info['state']!='Z' for e in previous['processes'].values()): raise ValueError('Partial/uncertain existing process record; diagnose then stop')
        record_path.unlink()
    for port in (config['api_port'],config['ui_port']):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try: sock.bind(('127.0.0.1',port)); sock.listen(1)
            except OSError as exc: raise ValueError(f'Port {port} is occupied; existing preview will not be stopped') from exc
    probe_workspace(config)
    token=uuid.uuid4().hex; env=archived_environment(config); env['VALUE_LOCAL_INSTANCE']=token
    commands={'api':archived_python_command(config,'-m','backend.server','--host','127.0.0.1','--port',str(config['api_port'])),'ui':[config['node_executable'],str(Path(config['ui_root'])/'scripts/serve-value-ui.mjs'),'--host','127.0.0.1','--port',str(config['ui_port'])]}
    record={'schema_version':'value.archived-workspace-processes/v1','prefix':str(prefix),'token':token,'processes':{}}; children=[]
    try:
        for kind,command in commands.items():
            with (prefix/'diagnostics'/f'{kind}.log').open('ab') as log: child=subprocess.Popen(command,cwd=config['source_root'] if kind=='api' else config['ui_root'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            children.append(child); info=process_info(child.pid)
            if not info: raise ValueError('Service exited before ownership recording')
            record['processes'][kind]={'pid':child.pid,'start_time':info['start_time'],'argv':command}
        write(record_path,record)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if any(c.poll() is not None for c in children): raise ValueError('Service exited; inspect diagnostics logs')
            if health(config['api_port'],'/api/health') and health(config['ui_port'],'/'): return {'status':'started','ui':workspace_url(config),'source_execution_identity_sha256':config['identity_sha256'],'same_host':True,'fully_isolated':False,'run_started':False}
            time.sleep(.2)
        raise ValueError('Service readiness timed out')
    except Exception:
        stop_record(record); record_path.unlink(missing_ok=True)
        for child in children:
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        raise

def diagnose(prefix,config):
    report={'schema_version':'value.archived-workspace-diagnostics/v1','same_host':True,'fully_isolated':False,'prefix':str(prefix)}
    try: report['proof']=probe_workspace(config)
    except (ValueError,OSError,subprocess.SubprocessError) as exc: report['error']=str(exc)
    path=prefix/'processes.json'
    report['process_ownership']={kind:owned(entry,read(path)['token']) for kind,entry in read(path)['processes'].items()} if path.exists() else {}
    report['health']={kind:health(config[kind+'_port'],'/api/health' if kind=='api' else '/') for kind in ('api','ui')}
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=('start','stop','diagnose')); parser.add_argument('--prefix',type=Path,required=True); args=parser.parse_args()
    try:
        prefix=regular(args.prefix.absolute())
        with regular(prefix/'control.lock').open('a') as control:
            fcntl.flock(control,fcntl.LOCK_EX)
            config=load_workspace(prefix)
            if args.action=='start': result=start(prefix,config)
            elif args.action=='diagnose': result=diagnose(prefix,config)
            else:
                path=prefix/'processes.json'
                if path.exists():
                    record=read(path)
                    if record.get('prefix') != str(prefix): raise ValueError('Process record prefix mismatch')
                    stop_record(record); path.unlink()
                result={'status':'stopped'}
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc: parser.exit(2,str(exc)+'\n')

if __name__=='__main__': main()

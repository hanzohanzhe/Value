"""Prepare SHA-verified, wheel-only private CPython/Node runtimes (no host copying)."""
from __future__ import annotations
import argparse, concurrent.futures, csv, email, gzip, hashlib, json, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path, PurePosixPath
from packaging.requirements import Requirement
from packaging.markers import default_environment
from packaging.tags import cpython_tags, compatible_tags, mac_platforms
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version
ROOT=Path(__file__).resolve().parents[1]
TARGETS={
 'linux-x64':('x86_64-unknown-linux-gnu','a6b9950cee5467d3a0a35473b3e848377912616668968627ba2254e5da4a1d1e','linux-x64',['manylinux_2_28_x86_64','manylinux_2_17_x86_64','manylinux2014_x86_64','manylinux2010_x86_64','manylinux1_x86_64'], 'Linux','x86_64','glibc >= 2.28; libstdc++ >= 6.0.25 (GLIBCXX_3.4.25); Linux kernel >= 4.18'),
 'macos-x64':('x86_64-apple-darwin','4ee44bf41d06626ad2745375d690679587c12d375e41a78f857a9660ce88e255','darwin-x64',list(mac_platforms((15,0),'x86_64')),'Darwin','x86_64','macOS >= 15'),
 'macos-arm64':('aarch64-apple-darwin','5f2a620c5278967c7fe666c9d41dc5d653c1829b3c26f62ece0d818e1a5ff9f8','darwin-arm64',list(mac_platforms((15,0),'arm64')),'Darwin','arm64','macOS >= 15'),
 'windows-x64':('', '608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d','win-x64',['win_amd64'],'Windows','AMD64','Windows 10 or later'),
}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def fetch(url):
 with urllib.request.urlopen(url,timeout=180) as f:return f.read()
def download(url,p,sha):
 p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  tmp=p.with_suffix(p.suffix+'.part')
  with urllib.request.urlopen(url,timeout=60) as source,tmp.open('wb') as dest:shutil.copyfileobj(source,dest)
  tmp.replace(p)
 if digest(p)!=sha:raise RuntimeError('SHA256 mismatch: '+str(p))
 return {'url':url,'sha256':sha,'filename':p.name,'bytes':p.stat().st_size}
def safe_name(name):
 p=PurePosixPath(name.replace('\\','/'))
 if p.is_absolute() or '..' in p.parts or (p.parts and ':' in p.parts[0]):raise RuntimeError('Unsafe archive path '+name)
 return p

def extract(archive,out):
 out.mkdir(parents=True,exist_ok=True)
 if zipfile.is_zipfile(archive):
  with zipfile.ZipFile(archive) as z:
   for m in z.infolist():
    p=out.joinpath(*safe_name(m.filename).parts)
    if m.is_dir():p.mkdir(parents=True,exist_ok=True);continue
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(m));mode=m.external_attr>>16
    if mode:os.chmod(p,mode&0o777)
 else:
  with tempfile.TemporaryFile() as raw:
   with gzip.open(archive,'rb') as compressed:shutil.copyfileobj(compressed,raw)
   raw.seek(0)
   _extract_tar(raw,out)
def _extract_tar(raw,out):
  with tarfile.open(fileobj=raw,mode='r:') as t:
   members=t.getmembers();byname={m.name:m for m in members}
   for m in members:
    p=out.joinpath(*safe_name(m.name).parts)
    if m.isdir():p.mkdir(parents=True,exist_ok=True);continue
    if not(m.isfile() or m.issym() or m.islnk()):raise RuntimeError('Unsafe special archive entry '+m.name)
    source=m;seen=set()
    while source.issym() or source.islnk():
     if source.name in seen:raise RuntimeError('Cyclic archive link')
     seen.add(source.name)
     link=PurePosixPath(source.linkname)
     raw=link if source.islnk() else PurePosixPath(source.name).parent/link
     # Normalize only links, then enforce the archive root boundary.
     parts=[]
     for bit in raw.parts:
      if bit=='..':
       if not parts:raise RuntimeError('Escaping archive link')
       parts.pop()
      elif bit!='.':parts.append(bit)
     key='/'.join(parts);safe_name(key);source=byname[key]
    if not source.isfile():raise RuntimeError('Non-file archive link')
    p.parent.mkdir(parents=True,exist_ok=True)
    with t.extractfile(source) as f,p.open('wb') as dest:shutil.copyfileobj(f,dest)
    os.chmod(p,source.mode&0o777)
def metadata_validate(wheels,config):
 env=default_environment();env.update(python_version='3.10',python_full_version='3.10.11' if config[4]=='Windows' else '3.10.18',implementation_name='cpython',platform_python_implementation='CPython',platform_system=config[4],platform_machine=config[5],sys_platform={'Linux':'linux','Darwin':'darwin','Windows':'win32'}[config[4]],os_name='nt' if config[4]=='Windows' else 'posix',extra='')
 tags=set(cpython_tags((3,10),['cp310'],config[3]))|set(compatible_tags((3,10),'cp310',config[3]));found={};requirements=[]
 for wheel in wheels:
  name,version,_,wtags=parse_wheel_filename(wheel.name)
  if not tags.intersection(wtags):raise RuntimeError('Incompatible wheel '+wheel.name)
  with zipfile.ZipFile(wheel) as z:meta=email.message_from_bytes(z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))))
  if meta.get('Requires-Python') and Version(env['python_full_version']) not in Requirement('python'+meta['Requires-Python']).specifier:raise RuntimeError('Requires-Python incompatible '+wheel.name)
  found[canonicalize_name(name)]=version
  for req in meta.get_all('Requires-Dist',[]):requirements.append((wheel.name,Requirement(req)))
 for owner,req in requirements:
  if req.marker and not req.marker.evaluate(env):continue
  got=found.get(canonicalize_name(req.name))
  if got is None or got not in req.specifier:raise RuntimeError(f'Dependency closure failure: {owner} requires {req}, have {got}')
 return {k:str(v) for k,v in sorted(found.items())}
def pinned_requirements(path):
 result={}
 for line in path.read_text().splitlines():
  line=line.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('-r '):result.update(pinned_requirements(path.parent/line[3:].strip()));continue
  req=Requirement(line)
  if req.marker:raise RuntimeError('Conditional top-level lock requires explicit target evaluation')
  result[canonicalize_name(req.name)]=req
 return result
def build(target,base):
 c=TARGETS[target];out=base/target;cache=base/'downloads';stage=base/('stage-'+target);shutil.rmtree(stage,ignore_errors=True);stage.mkdir(parents=True)
 records=[]
 pyname='python-3.10.11-embed-amd64.zip' if target=='windows-x64' else f'cpython-3.10.18+20250918-{c[0]}-install_only.tar.gz'
 pyurl='https://www.python.org/ftp/python/3.10.11/'+pyname if target=='windows-x64' else 'https://github.com/astral-sh/python-build-standalone/releases/download/20250918/'+pyname.replace('+','%2B')
 records.append(download(pyurl,cache/pyname,c[1]));extract(cache/pyname,stage/'python-unpack')
 python=stage/'runtime/python';python.parent.mkdir(parents=True)
 shutil.move(str(stage/'python-unpack' if target=='windows-x64' else stage/'python-unpack/python'),python)
 if target.startswith('macos-'):shutil.rmtree(python/'share/terminfo',ignore_errors=True)
 nodename='node-v22.22.0-'+c[2]+('.zip' if target=='windows-x64' else '.tar.gz')
 nodehash=json.loads((ROOT/'packaging/full-local/runtime-sources.lock.json').read_text())['node_artifacts'][nodename]['sha256']
 records.append(download('https://nodejs.org/dist/v22.22.0/'+nodename,cache/nodename,nodehash));extract(cache/nodename,stage/'node-unpack');shutil.move(str(stage/'node-unpack'/nodename.removesuffix('.zip').removesuffix('.tar.gz')),stage/'runtime/node')
 wheels=base/'wheels'/target;wheels.mkdir(parents=True,exist_ok=True)
 builder=base/'builder-python/bin/python3.10'
 cmd=[str(builder),'-m','pip','download','--requirement',str(ROOT/'requirements/value-all-py310.lock'),'--dest',str(wheels),'--python-version','3.10','--implementation','cp','--abi','cp310','--only-binary=:all:','--index-url','https://pypi.org/simple']
 for platform in c[3]:cmd+=['--platform',platform]
 wheel_lock=ROOT/'packaging/full-local'/(target+'-wheels.lock.json')
 if wheel_lock.exists():
  locked=json.loads(wheel_lock.read_text())
  allowed={item['filename'] for item in locked['wheels']}
  for old in wheels.glob('*.whl'):
   if old.name not in allowed:old.unlink()
  for item in locked['wheels']:download(item['url'],wheels/item['filename'],item['sha256'])
 else:subprocess.run(cmd,check=True)
 wheelpaths=sorted(wheels.glob('*.whl'));packages=metadata_validate(wheelpaths,c)
 for name,req in pinned_requirements(ROOT/'requirements/value-all-py310.lock').items():
  if name not in packages or Version(packages[name]) not in req.specifier:raise RuntimeError('Wheel lock diverges from requirements: '+str(req))
 for w in wheelpaths:
  n,v,*_=parse_wheel_filename(w.name);data=json.loads(fetch(f'https://pypi.org/pypi/{n}/{v}/json'));source=next(f for f in data['urls'] if f['filename']==w.name)
  records.append(download(source['url'],w,source['digests']['sha256']))
 site=python/('Lib/site-packages' if target=='windows-x64' else 'lib/python3.10/site-packages')
 install=[str(builder),'-m','pip','install','--no-index','--no-deps','--no-compile','--only-binary=:all:','--python-version','3.10','--implementation','cp','--abi','cp310','--target',str(site)]
 for platform in c[3]:install+=['--platform',platform]
 subprocess.run(install+[str(w) for w in wheelpaths],check=True)
 shutil.rmtree(site/'bin',ignore_errors=True)
 for record in site.glob('*.dist-info/RECORD'):
  rows=list(csv.reader(record.open(newline='')))
  with record.open('w',newline='') as f:csv.writer(f).writerows(row for row in rows if not row[0].startswith(('../../bin/','bin/')))
 for pyc in python.rglob('*.pyc'):pyc.unlink()
 for pycache in sorted(python.rglob('__pycache__'),reverse=True):shutil.rmtree(pycache,ignore_errors=True)
 if target=='windows-x64':(python/'python310._pth').write_text('python310.zip\n.\n../../app\nLib/site-packages\nimport site\n',encoding='ascii')
 provenance={'target':target,'python_version':'3.10.11' if target=='windows-x64' else '3.10.18','node_version':'22.22.0','minimum_system':c[6],'python_entry':'runtime/python/python.exe' if target=='windows-x64' else 'runtime/python/bin/python3.10','node_entry':'runtime/node/node.exe' if target=='windows-x64' else 'runtime/node/bin/node','downloads':records,'packages':packages,'dependency_closure_verified':True,'wheel_tags_verified':True,'foreign_platform_execution_verified':False}
 if not any(f.is_file() and 'license' in f.name.lower() for f in python.rglob('*')):raise RuntimeError('Python license missing')
 if not (stage/'runtime/node/LICENSE').is_file():raise RuntimeError('Node license missing')
 inventory=[{'path':f.relative_to(stage).as_posix(),'sha256':digest(f),'bytes':f.stat().st_size,'mode':f.stat().st_mode&0o777} for f in sorted((stage/'runtime').rglob('*')) if f.is_file()]
 if target!='linux-x64':
  folded=[row['path'].casefold() for row in inventory]
  if len(folded)!=len(set(folded)):raise RuntimeError('Case-insensitive runtime collision')
 inventory_path=stage/'runtime-inventory.json';inventory_path.write_text(json.dumps(inventory,indent=2)+'\n')
 provenance['runtime_inventory_sha256']=digest(inventory_path)
 provenance['system_requirement_sources']=['https://raw.githubusercontent.com/nodejs/node/v22.22.0/BUILDING.md','https://raw.githubusercontent.com/astral-sh/python-build-standalone/20250918/docs/running.rst','https://pypi.org/pypi/cbcbox/2.929/json']
 provenance['prepared_runtime_symlinks']=0
 provenance['omitted_upstream_paths']=['runtime/python/share/terminfo (case-colliding terminal database unused by VALUE)'] if target.startswith('macos-') else []
 licenses=[row for row in inventory if any(word in Path(row['path']).name.lower() for word in ('license','licence','copying','copyright'))]
 license_path=stage/'runtime-licenses.json';license_path.write_text(json.dumps(licenses,indent=2)+'\n')
 provenance['runtime_licenses_sha256']=digest(license_path)
 provenance['license_file_count']=len(licenses)
 (stage/'runtime-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
 locks=ROOT/'packaging/full-local';(locks/(target+'-wheels.lock.json')).write_text(json.dumps({'target':target,'packages':packages,'wheels':records[2:]},indent=2)+'\n')
 shutil.rmtree(out,ignore_errors=True);out.mkdir();shutil.move(str(stage/'runtime'),out/'runtime');shutil.move(str(stage/'runtime-provenance.json'),out/'runtime-provenance.json');shutil.move(str(inventory_path),out/'runtime-inventory.json');shutil.move(str(license_path),out/'runtime-licenses.json');shutil.rmtree(stage)
 return provenance

def main():
 p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--target',action='append',choices=TARGETS);args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
 builder=args.output_dir/'builder-python'
 if not builder.exists():
  c=TARGETS['linux-x64'];name=f'cpython-3.10.18+20250918-{c[0]}-install_only.tar.gz'
  archive=args.output_dir/'downloads'/name
  download('https://github.com/astral-sh/python-build-standalone/releases/download/20250918/'+name.replace('+','%2B'),archive,c[1])
  unpack=args.output_dir/'builder-unpack';extract(archive,unpack);shutil.move(str(unpack/'python'),builder);shutil.rmtree(unpack)
 failed={}
 for target in args.target or TARGETS:
  try:build(target,args.output_dir);print('COMPLETE '+target,flush=True)
  except Exception as e:failed[target]=str(e);print('FAILED '+target+': '+str(e),flush=True)
 (args.output_dir/'build-status.json').write_text(json.dumps({'failures':failed},indent=2)+'\n')
 if failed:raise SystemExit(1)
if __name__=='__main__':main()

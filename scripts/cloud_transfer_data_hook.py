#!/usr/bin/env python3
"""Reconstruct six audited data assets from exact objects; no network/model work."""
from __future__ import annotations
import argparse, hashlib, importlib, json, os, shutil, stat, subprocess, sys, tempfile, types, zipfile, zlib, struct
from pathlib import Path, PurePosixPath

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1048576),b''): digest.update(block)
    return digest.hexdigest()

def verify(path, digest, size):
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=size or sha(path)!=digest:
        raise ValueError('Object integrity mismatch: '+path.name)

def safe(root, name):
    rel=PurePosixPath(name)
    if '\\' in name or '\x00' in name or ':' in name or rel.is_absolute() or any(p in ('','..','.') for p in rel.parts):
        raise ValueError('Unsafe relative path')
    result=root.joinpath(*rel.parts)
    result.resolve().relative_to(root.resolve())
    for parent in (result,*result.parents):
        if parent==root.parent: break
        if parent.is_symlink(): raise ValueError('Symlink is forbidden')
    return result

def write_zip(node, destination, object_paths, artifacts):
    with zipfile.ZipFile(destination,'w',allowZip64=True) as archive:
        for member in node['members']:
            source=object_paths[member['object']] if 'object' in member else artifacts[member['artifact']]
            info=zipfile.ZipInfo(member['name'],tuple(member['date_time']))
            info.compress_type=member['compression'];info.external_attr=member['external_attr']
            if member['force_zip64']:info.create_version=45;info.extract_version=45
            if member['write_mode']=='writestr':
                # Supplemental original writer passed ZipInfo without a per-
                # member compression level, hence zlib default 6 (the archive-
                # level 9 is ignored by writestr in this form).
                level=6 if node['kind']=='supplemental' else member['level']
                archive.writestr(info,source.read_bytes(),compresslevel=level)
            else:
                info._compresslevel=member['level']
                with source.open('rb') as reader,archive.open(info,'w',force_zip64=member['force_zip64']) as writer:
                    shutil.copyfileobj(reader,writer,1048576)

def normalize_zip64_metadata(path, node):
    # Match the audited Python 3.12 forced-Zip64 metadata: Python 3.10
    # writes different local version/32-bit size fields and central versions.
    # Never recompress or modify a member payload or its 64-bit sizes.
    with zipfile.ZipFile(path) as archive:
        offset=archive.start_dir
        infos=archive.infolist()
        if archive.namelist()!=[m['name'] for m in node['members']]:
            raise ValueError('Archive member order mismatch')
    with path.open('r+b') as target:
        for info,member in zip(infos,node['members']):
            if not member['force_zip64']:continue
            target.seek(info.header_offset);header=target.read(30)
            if header[:4]!=b'PK\x03\x04':raise ValueError('Invalid local header')
            name_length,extra_length=struct.unpack_from('<HH',header,26)
            filename=target.read(name_length);extra=target.read(extra_length)
            if filename!=member['name'].encode('utf-8'):
                raise ValueError('Local Zip64 filename mismatch')
            if struct.unpack_from('<I',header,14)[0]!=info.CRC:
                raise ValueError('Local CRC mismatch')
            if len(extra)!=20 or struct.unpack_from('<HH',extra)!=(1,16):
                raise ValueError('Expected forced Zip64 local sizes')
            if struct.unpack_from('<QQ',extra,4)!=(info.file_size,info.compress_size):
                raise ValueError('Zip64 local sizes mismatch')
            target.seek(info.header_offset+4);target.write(struct.pack('<H',45))
            target.seek(info.header_offset+18);target.write(b'\xff'*8)
        for member in node['members']:
            target.seek(offset);header=target.read(46)
            if header[:4]!=b'PK\x01\x02':raise ValueError('Invalid central directory')
            lengths=struct.unpack_from('<HHH',header,28)
            if member['force_zip64']:
                target.seek(offset+4);target.write(bytes((45,)))
                target.seek(offset+6);target.write(struct.pack('<H',45))
            offset+=46+sum(lengths)

def assemble(recipe, fixture, full, output, scratch, object_paths):
    # Only import data/archive APIs; avoid importing gridform_core.__init__.
    package=types.ModuleType('gridform_core');package.__path__=[str(full/'app/gridform_core')]
    sys.modules['gridform_core']=package
    bundle=importlib.import_module('gridform_core.data_bundle')
    suite=importlib.import_module('gridform_core.research_suite')
    artifacts={}; records=[]
    for node in recipe['artifacts']:
        destination=safe(output,node['id']);destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            verify(destination,node['expected_sha256'],node['expected_bytes'])
            artifacts[node['id']]=destination
            records.append({'name':node['id'],'sha256':node['expected_sha256'],'bytes':node['expected_bytes'],'status':'exact_sha256_passed'})
            continue
        if node['kind']=='data_bundle':
            pack=safe(scratch,'packs/'+node['id']);pack.mkdir(parents=True)
            for member in node['members']:
                if member['name']=='value-data-bundle.json':continue
                target=safe(pack,member['name']);target.parent.mkdir(parents=True,exist_ok=True)
                # Hard links retain exact bytes and do not create unsafe symlinks.
                os.link(object_paths[member['object']],target)
            bundle.build_data_bundle(pack_root=pack,destination=destination)
            shutil.rmtree(pack)
        elif node['kind']=='suite':
            members={m['name']:m for m in node['members']}
            rights=safe(scratch,'suite-rights');rights.mkdir()
            for name in ('RIGHTS.json','ATTRIBUTION.md'):
                shutil.copyfile(object_paths[members[name]['object']],rights/name)
            suite.build_research_suite(
                base_bundle=artifacts[members['components/base.data-bundle.zip']['artifact']],
                network_bundle=artifacts[members['components/network.data-bundle.zip']['artifact']],
                studies_path=object_paths[members['study-templates.json']['object']],
                rights_paths=[rights/'RIGHTS.json',rights/'ATTRIBUTION.md'],destination=destination)
            # The audited local build changes only the stock suite descriptor ID.
            candidate=json.loads(zipfile.ZipFile(destination).read('research-suite.json'))
            expected=json.loads(object_paths[members['research-suite.json']['object']].read_bytes())
            candidate['suite_id']='value-uk-research-suite-v1-public1'
            if candidate!=expected:raise ValueError('Suite descriptor differs beyond approved public revision')
            temporary=destination.with_suffix('.public-id.tmp')
            write_zip(node,temporary,object_paths,artifacts);os.replace(temporary,destination)
            suite.validate_research_suite(destination)
        else:write_zip(node,destination,object_paths,artifacts)
        normalize_zip64_metadata(destination,node)
        verify(destination,node['expected_sha256'],node['expected_bytes'])
        artifacts[node['id']]=destination
        records.append({'name':node['id'],'sha256':node['expected_sha256'],'bytes':node['expected_bytes'],'status':'exact_sha256_passed'})
        print('Exact archive verified: '+node['id'],flush=True)
    return artifacts,records

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('full-root','fixture-dir','output-dir','receipt'):parser.add_argument('--'+flag,required=True,type=Path)
    args=parser.parse_args();full=args.full_root.resolve();fixture=args.fixture_dir.resolve()
    runtime=full/'runtime/python/bin/python3.10'
    if Path(sys.executable).resolve()!=runtime.resolve():
        os.execv(str(runtime),[str(runtime),str(Path(__file__).resolve()),*sys.argv[1:]])
    if sys.version_info[:3]!=(3,10,18) or zlib.ZLIB_RUNTIME_VERSION!='1.3.1':raise ValueError('Unapproved ZIP runtime')
    recipe=json.loads(safe(fixture,'recipe.json').read_text())
    if recipe['schema_version']!='value.public-data-exact-cloud-reconstruction/v1':raise ValueError('Unsupported recipe')
    target='value-data-2026-10-04'
    if os.environ.get('VALUE_DATA_TARGET_TAG')!=target or any(x['target_tag']!=target for x in recipe['outputs']):raise ValueError('Wrong destination tag')
    for row in recipe['source_api_files']:
        path=safe(full,row['path'])
        if sha(path)!=row['sha256']:raise ValueError('Full archive API has changed')
    source=Path(os.environ['VALUE_APPROVED_REUSE_SOURCE']).resolve()
    approved=recipe['source_asset'];verify(source,approved['asset_sha256'],approved['asset_bytes'])
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Output directory must be empty')
    with tempfile.TemporaryDirectory(prefix='value-exact-data-',dir=output.parent) as temporary:
        scratch=Path(temporary);cache=scratch/'objects';cache.mkdir();object_paths={}
        # Read only explicitly approved source members; never extract the whole source archive.
        with zipfile.ZipFile(source) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)):raise ValueError('Duplicate source archive paths')
            for row in recipe['objects']:
                if row['kind']=='approved_remote_member':
                    member=row['member'];safe(scratch,member);info=archive.getinfo(member)
                    if info.flag_bits&1 or stat.S_ISLNK(info.external_attr>>16) or info.file_size!=row['bytes']:raise ValueError('Unsafe source member')
                    path=cache/row['sha256']
                    with archive.open(info) as reader,path.open('wb') as writer:shutil.copyfileobj(reader,writer,1048576)
                    verify(path,row['sha256'],row['bytes']);object_paths[row['sha256']]=path
                elif row['kind']=='fixture_object':
                    path=safe(fixture,row['path']);verify(path,row['sha256'],row['bytes']);object_paths[row['sha256']]=path
                elif row['kind']!='binary_patch':raise ValueError('Unknown object kind')
        for row in recipe['objects']:
            if row['kind']=='binary_patch':
                patch=safe(fixture,row['patch_path']);verify(patch,row['patch_sha256'],row['patch_bytes'])
                if row['codec']!='zstd-patch-from':raise ValueError('Unknown patch codec')
                path=cache/row['sha256']
                subprocess.run(['zstd','-d','-M2048MB','--patch-from='+str(object_paths[row['base_sha256']]),str(patch),'-o',str(path)],check=True)
                verify(path,row['sha256'],row['bytes']);object_paths[row['sha256']]=path
        artifacts,checks=assemble(recipe,fixture,full,output,scratch,object_paths)
        assets=[]
        for row in recipe['outputs']:
            path=artifacts[row['artifact']];verify(path,row['sha256'],row['bytes'])
            assets.append({'path':str(path),'name':row['name'],'sha256':row['sha256'],'bytes':row['bytes'],'target_tag':target})
        # Inner family components are nested in the final outer container, not separate release assets.
        keep={x['name'] for x in assets}
        for path in output.iterdir():
            if path.name not in keep:path.unlink()
        receipt={'schema_version':'value.exact-data-cloud-reconstruction-receipt/v1','assets':assets,'archive_checks':checks,
            'recipe_sha256':sha(fixture/'recipe.json'),'source_asset_sha256':approved['asset_sha256'],
            'source_asset_members_used_only':True,'python':sys.version.split()[0],'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'scientific_computation':False,'scientific_input_bytes_changed':False}
        args.receipt.parent.mkdir(parents=True,exist_ok=True);args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()

"""Install selected backends directly from reviewed, pinned upstream GitHub revisions."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from apollo_capabilities import CapabilityService, atomic_json


def run(args, **kwargs):
    print('Running:', ' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True,**kwargs)


def checkout(name, source, home):
    target=home/'sources'/name
    if target.exists():
        if not (target/'.git').exists(): raise RuntimeError(f'{target} is not a verified Git checkout')
        sha=subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip()
        if sha != source['sha']: raise RuntimeError('Existing checkout differs from the pin; move it aside before repair')
        dirty=subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True)
        if dirty: raise RuntimeError('Refusing to install a modified upstream checkout')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        run(['git','init',target])
        run(['git','-C',target,'remote','add','origin','https://github.com/'+source['repository']+'.git'])
        run(['git','-C',target,'fetch','--depth','1','origin',source['sha']])
        run(['git','-C',target,'checkout','--detach','FETCH_HEAD'])
    license_file=next((target/p for p in ('LICENSE','LICENSE.txt','LICENSE.md') if (target/p).is_file()),None)
    if license_file is None: raise RuntimeError('Upstream licence is missing')
    # Hash the committed blob; Git for Windows may convert checkout newlines.
    original=subprocess.check_output(['git','-C',str(target),'show','HEAD:'+license_file.name])
    if hashlib.sha256(original).hexdigest()!=source['license_sha256']:
        raise RuntimeError('Upstream licence does not match reviewed source')
    return target


def install(name, *, base=BASE, cuda=False):
    if not (3,12)<=sys.version_info[:2]<=(3,13):
        raise RuntimeError('Run this installer with Python 3.12 or 3.13; Apollo itself is not replaced')
    if not shutil.which('git'): raise RuntimeError('Install Git for Windows first')
    svc=CapabilityService(base); source=svc.sources[name]; home=svc.home
    cache=home/'cache';cache.mkdir(parents=True,exist_ok=True)
    temporary=cache/'tmp';temporary.mkdir(exist_ok=True)
    os.environ.update(PIP_CACHE_DIR=str(cache/'pip'),TMP=str(temporary),TEMP=str(temporary))
    target=checkout(name,source,home)
    # Removing the receipt makes a failed repair visible instead of claiming readiness.
    receipt=home/'receipts'/(name+'.json');receipt.unlink(missing_ok=True)
    record={'sha':source['sha'],'repository':source['repository'],'license':source['license']}
    if name=='llama_cpp':
        if not shutil.which('cmake'): raise RuntimeError('CMake and a C++ toolchain are required for llama.cpp')
        build=home/'build'/'llama_cpp'
        run(['cmake','-S',target,'-B',build,'-DLLAMA_BUILD_SERVER=ON','-DLLAMA_CURL=OFF',
             '-DGGML_CUDA='+('ON' if cuda else 'OFF'),'-DCMAKE_BUILD_TYPE=Release'])
        run(['cmake','--build',build,'--config','Release','--target','llama-server','-j','4'])
        candidates=list(build.rglob('llama-server.exe' if os.name=='nt' else 'llama-server'))
        if not candidates: raise RuntimeError('Built server binary was not found')
        run([candidates[0],'--version']);record['binary']=str(candidates[0].resolve());record['cuda']=cuda
        print('Start the server with: '+str(candidates[0])+' -m YOUR_MODEL.gguf --host 127.0.0.1 --port 8080 -c 8192 -ngl '+('99' if cuda else '0'),flush=True)
    elif name=='browser_use':
        if not shutil.which('docker'): raise RuntimeError('Browser Use requires Docker; no host execution fallback')
        context=home/'build'/'browser_use';context.mkdir(parents=True,exist_ok=True)
        shutil.copy2(BASE/'apollo_capability_worker.py',context/'apollo_capability_worker.py')
        shutil.copy2(BASE/'apollo_capability_policy.py',context/'apollo_capability_policy.py')
        dockerfile=f'''FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git chromium ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "browser-use @ git+https://github.com/{source['repository']}.git@{source['sha']}"
RUN useradd -m -u 10001 apollo
COPY apollo_capability_worker.py apollo_capability_policy.py /opt/apollo/
USER 10001:10001
ENV HOME=/tmp/home DO_NOT_TRACK=1 ANONYMIZED_TELEMETRY=false BROWSER_USE_SETUP_LOGGING=false
WORKDIR /tmp
ENTRYPOINT ["python", "-u", "/opt/apollo/apollo_capability_worker.py"]
'''
        (context/'Dockerfile').write_text(dockerfile)
        run(['docker','build','--tag',svc.image(),context]);record['image']=svc.image()
    else:
        environment=home/'environments'/name
        if not svc.python(name).is_file(): venv.EnvBuilder(with_pip=True).create(environment)
        python=svc.python(name)
        run([python,'-m','pip','install','--upgrade','pip'])
        if name in {'kokoro','docling'}:
            run([python,'-m','pip','install','torch','--index-url','https://download.pytorch.org/whl/'+('cu128' if cuda else 'cpu')])
        build_root=home/'build';build_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root,prefix=name+'-') as staging:
            stage=Path(staging);archive=stage/'source.tar'
            run(['git','-C',target,'archive','--format=tar','-o',archive,'HEAD'])
            clean=stage/'source';clean.mkdir()
            with tarfile.open(archive) as bundle: bundle.extractall(clean,filter='data')
            run([python,'-m','pip','install',str(clean)+source.get('extras','')])
        if name=='kokoro': run([python,'-m','pip','install','soundfile'])
        if name=='gpt_researcher': run([python,'-m','pip','install','langchain-ollama'])
        if name=='graphiti': run([python,'-m','pip','install','httpx'])
        cache=home/'browsers'
        if name=='crawl4ai':
            env={**os.environ,'PLAYWRIGHT_BROWSERS_PATH':str(cache)}
            run([python,'-m','playwright','install','chromium'],env=env)
        run([python,'-c',f'import {source["import"]}; print("Pinned backend import passed")'])
        record['python']=str(python);record['packages']=subprocess.check_output([str(python),'-m','pip','freeze'],text=True).splitlines()
    atomic_json(receipt,record)
    print(name+' installed. Model downloads and external services are checked when first used.',flush=True)
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backends',nargs='+',choices=list(CapabilityService(BASE).sources))
    parser.add_argument('--cuda',action='store_true',help='Owner-selected CUDA build; default CPU avoids competing with the main LLM')
    args=parser.parse_args()
    for backend in args.backends: install(backend,cuda=args.cuda)

"""Private backend entry point. Third-party imports occur only inside a task."""
from __future__ import annotations
import asyncio
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback
from apollo_capability_policy import public_url

MAX_TEXT = 100000


def document(args):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions
    opts = PdfPipelineOptions()
    opts.accelerator_options = AcceleratorOptions(device=args['settings']['device'], num_threads=4)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    result = converter.convert(args['path'], max_num_pages=100, max_file_size=50*1024*1024)
    from docling.datamodel.base_models import ConversionStatus
    if result.status != ConversionStatus.SUCCESS: raise RuntimeError('Document conversion incomplete: '+str(result.status))
    text = result.document.export_to_markdown()
    target = Path(args['output_dir']) / 'document.md'; target.write_text(text, encoding='utf-8')
    return {'content': text[:MAX_TEXT], 'truncated':len(text)>MAX_TEXT, 'artifact':str(target),
            'source':args['path'], 'status':str(result.status), 'pages':len(result.document.pages)}


def synthesize(args):
    from kokoro import KPipeline
    import numpy as np
    import soundfile as sf
    settings = args['settings']; text = str(args['text'])[:12000]
    voice = settings['voice_name']
    if not voice.startswith(('af_','am_','bf_','bm_')): raise ValueError('Select a bundled English Kokoro voice')
    pipeline = KPipeline(repo_id='hexgrad/Kokoro-82M', lang_code='b' if voice.startswith('b') else 'a', device=settings['device'])
    chunks = [audio for _, _, audio in pipeline(text, voice=voice) if audio is not None]
    if not chunks: raise RuntimeError('Kokoro produced no audio')
    audio = np.concatenate([a.detach().cpu().numpy() if hasattr(a,'detach') else a for a in chunks])
    path = Path(args['output_dir']) / 'speech.wav'; sf.write(str(path), audio, 24000)
    return {'saved': True, 'file':str(path), 'sample_rate':24000, 'seconds':len(audio)/24000,
            'voice':voice, 'engine':'Kokoro', 'offline_after_model_download':True}


def transcribe(args):
    from faster_whisper import WhisperModel
    settings = args['settings']; device = settings['device']
    model = WhisperModel(settings['whisper_model'], device=device,
        compute_type='int8' if device == 'cpu' else 'float16', cpu_threads=4,
        download_root=str(Path(os.environ['HF_HOME']) / 'whisper'))
    segments, info = model.transcribe(args['path'], beam_size=3, vad_filter=True,
        language=args.get('language') or None)
    items = []
    for item in segments:
        items.append({'start':item.start,'end':item.end,'text':item.text})
        if len(items) >= 10000: raise ValueError('Transcript exceeds segment budget')
    text = ''.join(s['text'] for s in items).strip()
    target = Path(args['output_dir']) / 'transcript.json'; target.write_text(json.dumps(items), encoding='utf-8')
    return {'text':text[:MAX_TEXT], 'truncated':len(text)>MAX_TEXT, 'language':info.language,
            'segments':items[:100], 'artifact':str(target)}


async def crawl(args):
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    config = BrowserConfig(headless=True, verbose=False)
    async with AsyncWebCrawler(config=config) as crawler:
        async def guarded(page, context, **_kwargs):
            async def route_handler(route):
                try:
                    await asyncio.to_thread(public_url, route.request.url)
                except Exception: await route.abort(); return
                await route.continue_()
            await context.route('**/*', route_handler)
            return page
        crawler.crawler_strategy.set_hook('on_page_context_created', guarded)
        result = await crawler.arun(url=args['url'], config=CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS, page_timeout=45000, verbose=False))
        if not result.success: raise RuntimeError(str(result.error_message)[:1000])
        text = result.markdown.raw_markdown if hasattr(result.markdown,'raw_markdown') else str(result.markdown)
        return {'url':result.url, 'text':text[:MAX_TEXT], 'content':text[:MAX_TEXT],
                'truncated':len(text)>MAX_TEXT, 'title':result.metadata.get('title','') if result.metadata else '',
                'retrieved_at':datetime.now(timezone.utc).isoformat()}


async def browser_task(args):
    from browser_use import Browser, Agent, ChatOpenAI
    config = args['model_config']
    browser = Browser('chromium', headless=True, executable_path='/usr/bin/chromium',
        allowed_domains=args['domains'], block_ip_addresses=True)
    agent = Agent(str(args['query'])[:12000], browser=browser,
        llm=ChatOpenAI(model=config['model'], base_url=config['url'].rstrip('/')+'/v1', api_key='local-only'),
        workspace='/tmp/workspace', use_vision=False, web_search=False)
    try:
        history = await agent.run(max_steps=min(30,int(args['settings']['max_steps'])), timeout=150)
        completed=bool(history.is_successful())
        return {'content':str(history.final_result() or '')[:MAX_TEXT],
                'completed':completed, 'success':completed, 'status':'completed' if completed else 'incomplete', 'domains':args['domains'],
                'notice':'Fresh browser in a resource-limited container; no host session or file mounts'}
    finally: await browser.stop()


async def research(args):
    config = args['model_config']; settings = args['settings']
    provider = config.get('provider', 'ollama')
    model_spec = provider + ':' + config['model']
    os.environ.update(OLLAMA_BASE_URL=config['url'], OPENAI_API_BASE=config['url']+'/v1', OPENAI_BASE_URL=config['url']+'/v1',
        OPENAI_API_KEY='local-only', FAST_LLM=model_spec, SMART_LLM=model_spec,
        STRATEGIC_LLM=model_spec, EMBEDDING='ollama:'+settings['embedding_model'],
        EMBEDDING_PROVIDER='ollama', OLLAMA_EMBEDDING_MODEL=settings['embedding_model'], RETRIEVER='duckduckgo')
    from gpt_researcher import GPTResearcher
    config_file = Path(args['output_dir']) / 'research_config.json'
    config_file.write_text(json.dumps({'FAST_LLM':model_spec, 'SMART_LLM':model_spec,
        'STRATEGIC_LLM':model_spec, 'EMBEDDING':'ollama:'+settings['embedding_model'],
        'RETRIEVER':'duckduckgo', 'MAX_ITERATIONS':2, 'MAX_SEARCH_RESULTS_PER_QUERY':3,
        'MAX_SUBTOPICS':3, 'SCRAPER':'bs', 'REPORT_SOURCE':'web'}))
    researcher = GPTResearcher(query=str(args['query'])[:12000], report_type='research_report',
        source_urls=args['sources'], complement_source_urls=False, config_path=str(config_file), verbose=False, max_subtopics=3)
    await researcher.conduct_research()
    report = await researcher.write_report()
    sources = researcher.get_research_sources()
    target = Path(args['output_dir'])/'research.md';target.write_text(report, encoding='utf-8')
    return {'content':report[:MAX_TEXT], 'sources':sources[:20], 'artifact':str(target),
        'notice':'Generated research; citations and conclusions require evaluation'}


async def graph(operation, args):
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    # Avoid a separate GPU reranker and cloud-default fallback.
    class LexicalReranker(CrossEncoderClient):
        async def rank(self, query, passages):
            words = set(query.lower().split())
            return sorted([(p, len(words & set(p.lower().split()))/max(1,len(words))) for p in passages], key=lambda x:-x[1])
    settings=args['settings'];config=args['model_config'];credentials=args['graph_credentials']
    client = Graphiti(settings['graph_uri'], settings['graph_user'], credentials['password'],
        llm_client=OpenAIGenericClient(config=LLMConfig(api_key='local-only',model=config['model'],base_url=config['url']+'/v1')),
        embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key='local-only',
            embedding_model=settings['embedding_model'],base_url=config['url']+'/v1')),
        cross_encoder=LexicalReranker(), max_coroutines=1)
    group='apollo_named_memory'
    try:
        if operation == 'graph_search':
            edges = await client.search(str(args['query'])[:12000], group_ids=[group], num_results=8)
            return {'facts':[{'id':e.uuid,'fact':e.fact,'valid_at':str(e.valid_at),'invalid_at':str(e.invalid_at),
                              'episodes':e.episodes} for e in edges], 'reranker':'CPU lexical overlap'}
        await client.build_indices_and_constraints()
        result = await client.add_episode(name=str(args['name'])[:200], episode_body=str(args['content'])[:MAX_TEXT],
            source_description=str(args['source'])[:1000], reference_time=datetime.now(timezone.utc),
            source=EpisodeType.text, group_id=group, uuid=args.get('episode_id'))
        return {'indexed':True, 'episode_id':result.episode.uuid, 'source':args['source']}
    finally: await client.close()


def inference(args):
    import urllib.request
    payload = {'model':str(args.get('model','local')), 'messages':[{'role':'user','content':str(args['query'])[:12000]}],
               'max_tokens':128,'stream':False,'temperature':0}
    req=urllib.request.Request(args['url']+'/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response: result=json.load(response)
    return {'content':result['choices'][0]['message'].get('content',''), 'usage':result.get('usage',{}),
            'timings':result.get('timings',{}), 'notice':'Uses the separately started local llama-server; no speed claim implied'}


def execute(backend, operation, args):
    dispatch = {'document':document, 'synthesize':synthesize, 'transcribe':transcribe, 'crawl':crawl,
                'browser_task':browser_task,'research':research,'inference':inference}
    if operation.startswith('graph_'): return asyncio.run(graph(operation,args))
    result = dispatch[operation](args)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


if __name__ == '__main__':
    output = sys.stdout
    try:
        data=json.loads(sys.stdin.read(2*1024*1024+1))
        Path(data['arguments']['output_dir']).mkdir(parents=True,exist_ok=True)
        with contextlib.redirect_stdout(sys.stderr): result=execute(data['backend'],data['operation'],data['arguments'])
        output.write(json.dumps(result,default=str));output.flush()
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        output.write(json.dumps({'error':f'{type(exc).__name__}: {exc}'}));output.flush()

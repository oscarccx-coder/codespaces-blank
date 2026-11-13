"""Core routing, real process lifecycle, source provenance and local inference transport."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apollo_capabilities import CapabilityService, OWNER, atomic_json
from apollo_capability_policy import public_url, local_endpoint
from ollama_client import OllamaClient

BASE=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('cap_test_'+name,BASE/'modules'/name/'module.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result.Module


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.svc=CapabilityService(self.base)
        (self.base/'config.json').write_text(json.dumps({'ollama_url':'http://127.0.0.1:11434','model':'fixture:7b'}))

    def test_sources_are_pinned_with_matching_licences(self):
        import hashlib,re
        self.assertEqual(len(self.svc.sources),8)
        for name,source in self.svc.sources.items():
            self.assertRegex(source['sha'],r'^[a-f0-9]{40}$')
            data=(BASE/'integrations/licenses'/(name+'.txt')).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),source['license_sha256'])
        self.assertFalse(any(s['installed'] for s in self.svc.status()['backends'].values()))

    def test_settings_are_explicit_and_no_uninstalled_fallback(self):
        self.assertEqual(self.svc.settings()['voice'],'existing')
        self.assertEqual(self.svc.settings()['device'],'cpu')
        self.svc.configure(voice='kokoro',device='cpu')
        with self.assertRaisesRegex(RuntimeError,'must finish first'):
            self.svc.run('kokoro','synthesize',{'text':'Hello'})
        with self.assertRaises(ValueError): self.svc.configure(unknown=True)
        with self.assertRaises(PermissionError): self.svc.configure(llama_url='https://remote.invalid/v1')
        with self.assertRaises(ValueError): self.svc.run('docling','shell')

    def test_paths_and_destinations_cannot_escape(self):
        with self.assertRaises(PermissionError):self.svc.input_file('/etc/passwd')
        for url in ['http://127.0.0.1','http://[::1]','http://192.168.1.1','file:///etc/passwd','https://u:p@example.com']:
            with self.assertRaises((PermissionError,ValueError)):public_url(url,resolve=False)
        with patch('socket.getaddrinfo',return_value=[(None,None,None,None,('10.1.2.3',443))]):
            with self.assertRaises(PermissionError):public_url('https://public-looking.example')
        self.assertEqual(local_endpoint('http://127.0.0.1:8080/v1'),'http://127.0.0.1:8080/v1')

    def test_native_system_hooks_delegate_to_shared_service(self):
        files=module('file_manager')({'base_dir':str(self.base)})
        path=self.base/'workspace'/'paper.md';path.write_text('# Evidence')
        with patch('apollo_capabilities.service',return_value=self.svc),patch.object(self.svc,'run',return_value={'content':'actual'}) as execute:
            self.assertEqual(files.run('read_document',{'root':'workspace','path':'paper.md'})['content'],'actual')
            self.assertEqual(execute.call_args.args,('docling','document',{'path':str(path.resolve())}))
            with self.assertRaises(PermissionError): files.run('read_document',{'root':'workspace','path':'../../escape'})
        web=module('web_explorer')({'base_dir':str(self.base)})
        self.svc.configure(web='crawl4ai')
        with patch('apollo_capabilities.service',return_value=self.svc),patch.object(self.svc,'run',return_value={'text':'page'}) as execute:
            self.assertEqual(web.run('fetch_url',{'url':'https://example.com'})['text'],'page')
            self.assertEqual(execute.call_args.args[0],'crawl4ai')
            web.run('research_report',{'query':'Research','sources':['https://example.com']})
            self.assertEqual(execute.call_args.args[:2],('gpt_researcher','research'))
        memory=module('memory_bank')({'base_dir':str(self.base),'validation':True});self.addCleanup(memory.close)
        row=memory.store_memory('Engineering decision','Use aluminium','knowledge')
        with patch('apollo_capabilities.service',return_value=self.svc),patch.object(self.svc,'run',return_value={'indexed':True}) as execute:
            memory.run('index_temporal_memory',{'id':row['id']})
            self.assertEqual(execute.call_args.args[:2],('graphiti','graph_add'))
            self.assertEqual(execute.call_args.args[2]['content'],'Use aluminium')
            with self.assertRaises(KeyError):memory.run('index_temporal_memory',{'id':-1})

    def test_existing_dictation_and_voice_output_use_selected_backends(self):
        speech=module('text_to_speech')({'base_dir':str(self.base)})
        self.svc.configure(transcription='faster_whisper',voice='kokoro')
        with patch('apollo_capabilities.service',return_value=self.svc),patch.object(self.svc,'run',return_value={'text':'Hello Oscar','saved':True}) as execute:
            self.assertEqual(speech._recognize_wave_file(self.base/'audio.wav',culture='en-GB'),'Hello Oscar')
            self.assertEqual(execute.call_args.args[:2],('faster_whisper','transcribe'))
            speech.run('save_wav',{'text':'Hello Oscar'})
            self.assertEqual(execute.call_args.args[:2],('kokoro','synthesize'))
        with patch('apollo_capabilities.service',return_value=self.svc),patch.object(speech,'_require_windows'),patch.object(speech,'_queue_voice_imprint',return_value={'started':True}) as queue:
            result=speech.run('speak_text',{'text':'Hello Oscar'})
            self.assertEqual(result['engine'],'Kokoro')
            queue.assert_called_once_with('Hello Oscar',backend='kokoro')

    def test_superseded_kokoro_output_never_starts_playback(self):
        import types
        from unittest.mock import Mock
        speech=module('text_to_speech')({'base_dir':str(self.base)})
        speech._imprint_generation=2
        sound=types.SimpleNamespace(PlaySound=Mock(),SND_FILENAME=1,SND_ASYNC=2)
        with patch.dict(sys.modules,{'winsound':sound}),patch('apollo_capabilities.service',return_value=self.svc),patch.object(self.svc,'run',return_value={'file':'speech.wav','seconds':0.01}):
            speech._speak_kokoro({'text':'Old speech','id':'old','generation':1})
            sound.PlaySound.assert_not_called()
            speech._speak_kokoro({'text':'Current speech','id':'new','generation':2})
            sound.PlaySound.assert_called_once_with('speech.wav',3)

    def test_model_cannot_install_configure_or_bypass_browser_permission(self):
        from apollo_runtime import ApolloRuntime
        core=module('capabilities')({'base_dir':str(self.base)})
        names={tool['name'] for tool in core.tools()}
        self.assertFalse(names & {'install','configure','activate','setup'})
        runtime=ApolloRuntime(self.base);self.addCleanup(runtime.conn.close)
        self.assertEqual(runtime.risk_for('capabilities__browser_task'),'high')
        class Manager:
            def _execute_tool_direct(self,*args):raise AssertionError('Denied browser executed')
        with self.assertRaises(PermissionError):runtime.execute_tool(Manager(),'capabilities__browser_task',{'query':'click','domains':['example.com']})

    def _fixture_worker(self, delay):
        worker=self.base/'fixture';worker.mkdir(exist_ok=True)
        (worker/'apollo_capability_worker.py').write_text('import json,sys,time\ndata=json.load(sys.stdin)\ntime.sleep('+str(delay)+')\nprint(json.dumps({"content":"from worker"}))\n')
        self.svc.python=lambda name:Path(sys.executable)
        atomic_json(self.svc.home/'receipts/docling.json',{'sha':self.svc.sources['docling']['sha']})
        path=self.base/'source.md';path.write_text('Source')
        return worker,path

    def test_real_child_process_has_saved_result_and_environment_isolated(self):
        worker,path=self._fixture_worker(0)
        with patch('apollo_capabilities.ROOT',worker),patch.dict(os.environ,{'OPENAI_API_KEY':'must-not-leak'}):
            result=self.svc.run('docling','document',{'path':str(path)})
        self.assertEqual(result['content'],'from worker')
        self.assertEqual(self.svc.runs()[0]['state'],'completed')
        self.assertFalse(self.svc.lock.locked());self.assertIsNone(self.svc.process)

    def test_shutdown_releases_child_and_preserves_cancelled_receipt(self):
        worker,path=self._fixture_worker(30);errors=[]
        core=module('capabilities')({'base_dir':str(self.base)});core.service=self.svc
        def run():
            try:
                with patch('apollo_capabilities.ROOT',worker):self.svc.run('docling','document',{'path':str(path)})
            except Exception as exc:errors.append(str(exc))
        thread=threading.Thread(target=run);thread.start()
        deadline=time.monotonic()+5
        while self.svc.process is None and time.monotonic()<deadline:time.sleep(.01)
        self.assertIsNotNone(self.svc.process)
        core.close();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertTrue(errors)
        self.assertFalse(self.svc.lock.locked());self.assertIsNone(self.svc.process)
        self.assertEqual(self.svc.runs()[0]['state'],'cancelled')

    def test_setup_error_after_acquiring_lock_still_releases_it(self):
        worker,path=self._fixture_worker(0)
        with patch('apollo_capabilities.ROOT',worker):
            with self.assertRaises((TypeError,ValueError)):
                self.svc.run('docling','document',object())
        self.assertFalse(self.svc.lock.locked())
        self.assertEqual(self.svc.runs()[0]['state'],'failed')

    def test_owner_cancel_does_not_stop_other_work(self):
        owner=object();self.svc.owner=owner
        self.svc.cancel(expected_owner=object());self.assertFalse(self.svc.cancelled.is_set())
        self.svc.cancel(expected_owner=owner);self.assertTrue(self.svc.cancelled.is_set())

    def test_interrupted_receipts_are_not_replayed(self):
        atomic_json(self.svc.home/'runs/old.json',{'id':'old','started':1,'state':'running'})
        self.assertEqual(self.svc.runs()[0]['state'],'interrupted')
        self.assertEqual(json.loads((self.svc.home/'runs/old.json').read_text())['state'],'interrupted')


class LlamaTransportTests(unittest.TestCase):
    def setUp(self):
        self.requests=[];requests=self.requests
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"local-gguf"}]}')
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append((self.path,data))
                self.send_response(200);self.end_headers()
                if data['stream']:
                    self.wfile.write(b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: {"choices":[],"usage":{"completion_tokens":1,"prompt_tokens":4}}\n\ndata: [DONE]\n\n')
                else:
                    self.wfile.write(json.dumps({'choices':[{'message':{'role':'assistant','content':'','tool_calls':[{'id':'call_x','type':'function','function':{'name':'calculator__calculate','arguments':'{"expression":"2+2"}'}}]}}], 'usage':{'prompt_tokens':4,'completion_tokens':2}}).encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.client=OllamaClient(f'http://127.0.0.1:{self.server.server_port}/v1','local-gguf');self.client.strict_model=True

    def test_real_http_models_native_calls_and_sse_stream(self):
        self.assertEqual(self.client.models(),['local-gguf'])
        result=self.client.chat_once([{'role':'user','content':'Calculate'}])
        self.assertEqual(result['message']['tool_calls'][0]['function']['arguments'],{'expression':'2+2'})
        self.assertEqual(self.requests[0][0],'/v1/chat/completions')
        self.assertNotIn('options',self.requests[0][1])
        self.assertEqual(''.join(self.client.stream_chat([{'role':'user','content':'Hi'}])),'Hello')
        self.assertEqual(self.client.last_metrics['eval_count'],1)

    def test_tool_replies_have_correct_openai_call_ids(self):
        messages=[{'role':'assistant','content':'','tool_calls':[{'function':{'name':'calculator__calculate','arguments':{'expression':'2+2'}}}]},
                  {'role':'tool','tool_name':'calculator__calculate','content':'4'}]
        converted=self.client._openai_messages(messages)
        self.assertEqual(converted[0]['tool_calls'][0]['id'],converted[1]['tool_call_id'])
        self.assertEqual(json.loads(converted[0]['tool_calls'][0]['function']['arguments']),{'expression':'2+2'})


@unittest.skipUnless(importlib.util.find_spec('docling'),'Optional real Docling environment is not installed')
class RealDocumentTests(unittest.TestCase):
    def test_real_docling_conversion_preserves_content_and_artifact(self):
        from apollo_capability_worker import document
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'evidence.md';path.write_text('# Apollo evidence\n\nAn engineering decision.\n')
            result=document({'path':str(path),'output_dir':temporary,'settings':{'device':'cpu'}})
            self.assertIn('Apollo evidence',result['content'])
            self.assertEqual(Path(result['artifact']).read_text(),result['content'])


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'Qt is not installed')
class BackendUiTests(unittest.TestCase):
    def test_owner_page_builds_without_starting_any_backend(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication, QPushButton
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            core=module('capabilities')({'base_dir':temporary})
            with patch('subprocess.Popen',side_effect=AssertionError('UI startup launched a backend')):
                page=core.build_ui()
                buttons={button.text():button for button in page.findChildren(QPushButton)}
                self.assertIn('Install / repair selected',buttons)
                buttons['Save backend choices'].click()
                self.assertEqual(core.service.settings()['voice'],'existing')
                page.close();page.deleteLater();app.processEvents()


if __name__=='__main__':unittest.main()

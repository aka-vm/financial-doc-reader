import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from financial_brief.llm_config import LLMRegistry,LLMConfigError,load_registry,TASKS
from financial_brief.server import create_app
from reader.backends import LLM_ROUTER,call


def local_config():
    return {'version':1,'llms':{
        'small':{'provider':'link','model':'small-local','base_url':'http://127.0.0.1:8000/v1'},
        'large':{'provider':'link','model':'large-local','base_url':'http://127.0.0.1:9000/v1'}},
        'tasks':{task:'small' if task in {'extract','month_inputs'} else 'large' for task in TASKS}}


class RegistryTests(unittest.TestCase):
    def test_all_local_configuration_requires_no_openai_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'models.json';config.write_text(json.dumps(local_config()))
            with patch('financial_brief.server.openai_key',side_effect=AssertionError('must not read an OpenAI key')):
                app=create_app({'TESTING':True,'DATA_DIR':str(Path(folder)/'data'),'BACKEND':'openai','LLM_CONFIG':str(config)})
                health=app.test_client().get('/healthz').json
            self.assertEqual(health['backend'],'registry')
            self.assertEqual(health['models']['extract'],'small-local')
            self.assertEqual(health['models']['contract'],'large-local')
            self.assertNotIn('base_url',json.dumps(health))

    def test_task_keys_route_to_distinct_endpoints_and_options(self):
        registry=LLMRegistry(local_config())
        token=LLM_ROUTER.set(registry)
        try:
            with patch('reader.backends.openai_compatible',return_value={'ok':True}) as invoke:
                call('registry','task:extract','Read',{},max_tokens=900)
                self.assertEqual(invoke.call_args.args[:2],('http://127.0.0.1:8000/v1','small-local'))
                call('registry','task:review','Check',{},max_tokens=1200)
                self.assertEqual(invoke.call_args.args[:2],('http://127.0.0.1:9000/v1','large-local'))
                self.assertEqual(invoke.call_args.args[5],1200)
        finally:LLM_ROUTER.reset(token)

    def test_invalid_routes_disabled_entries_and_embedded_keys_fail_closed(self):
        cases=[]
        data=local_config();data['tasks']['review']='missing';cases.append(data)
        data=local_config();data['llms']['large']['enabled']=False;cases.append(data)
        data=local_config();data['llms']['small']['api_key']='secret';cases.append(data)
        data=local_config();data['llms']['small']['base_url']='http://user:secret@host/v1';cases.append(data)
        data=local_config();del data['tasks']['answer'];cases.append(data)
        for data in cases:
            with self.subTest(data=data),self.assertRaises(LLMConfigError):LLMRegistry(data)

    def test_config_reloads_between_jobs_but_existing_snapshot_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';data=local_config();path.write_text(json.dumps(data))
            original=load_registry(path)
            data['tasks']['extract']='large';path.write_text(json.dumps(data))
            changed=load_registry(path)
            self.assertEqual(original.models()['extract'],'small-local')
            self.assertEqual(changed.models()['extract'],'large-local')
            self.assertNotEqual(original.revision,changed.revision)

    def test_parallel_registry_contexts_do_not_leak_between_jobs(self):
        def execute(model):
            data=local_config();data['llms']['small']['model']=model;registry=LLMRegistry(data)
            token=LLM_ROUTER.set(registry)
            try:return LLM_ROUTER.get().models()['extract']
            finally:LLM_ROUTER.reset(token)
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(execute,['one','two'])),['one','two'])
        self.assertIsNone(LLM_ROUTER.get())

    def test_openai_entry_uses_its_own_credential_reference_and_reasoning(self):
        data=local_config();data['llms']['large']={'provider':'openai','model':'gpt-6-luna','api_key_env':'REVIEW_API_KEY','api_key_file':'/server/review-key'}
        data['tasks']['review']={'llm':'large','reasoning_effort':'medium','max_output_tokens':16000}
        registry=LLMRegistry(data)
        with patch('reader.backends.openai_key',return_value='server-only-key') as key,patch('reader.backends.openai',return_value={'ok':True}) as invoke:
            registry.invoke('review','Review',{})
        key.assert_called_once_with('REVIEW_API_KEY','/server/review-key')
        self.assertEqual(invoke.call_args.args[0],'gpt-6-luna')
        self.assertEqual(invoke.call_args.args[3:5],(16000,'medium'))
        self.assertEqual(invoke.call_args.kwargs,{'key':'server-only-key'})
        self.assertNotIn('server-only-key',json.dumps(registry.describe()))

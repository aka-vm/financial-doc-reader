"""Validated LLM registry and per-task routing, snapshotted once for each job."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

TASKS=('extract','write','review','answer','contract','month_inputs')
PROVIDERS={'openai','link','ollama'}
EFFORTS={'none','minimal','low','medium','high','xhigh','max'}


class LLMConfigError(ValueError):
    pass


def credential(entry):
    from reader.backends import openai_key
    if entry['provider']=='openai':
        return openai_key(entry.get('api_key_env','OPENAI_API_KEY'),entry.get('api_key_file'))
    env=entry.get('api_key_env')
    if env and os.environ.get(env,'').strip():return os.environ[env].strip()
    filename=entry.get('api_key_file')
    if filename:
        try:return Path(filename).expanduser().read_text().strip()
        except OSError:raise LLMConfigError('LLM credential file is unavailable.') from None
    if env:raise LLMConfigError(f'LLM credential environment variable {env!r} is not set.')
    return None


class LLMRegistry:
    def __init__(self,data):
        self.data=copy.deepcopy(data)
        if not isinstance(data,dict) or data.get('version')!=1:
            raise LLMConfigError('LLM config requires version: 1.')
        entries=data.get('llms');tasks=data.get('tasks')
        if not isinstance(entries,dict) or not entries or not isinstance(tasks,dict):
            raise LLMConfigError('LLM config requires llms and tasks maps.')
        for key,entry in entries.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',key) or not isinstance(entry,dict):
                raise LLMConfigError('Invalid LLM registry key or entry.')
            if entry.get('provider') not in PROVIDERS:
                raise LLMConfigError(f'LLM {key!r}: provider must be openai, link, or ollama.')
            if not isinstance(entry.get('model'),str) or not entry['model'].strip():
                raise LLMConfigError(f'LLM {key!r}: model ID is required.')
            if any(field in entry for field in ('api_key','key','headers','token')):
                raise LLMConfigError('Use api_key_env or api_key_file references; never embed credentials in the registry.')
            for field in ('api_key_env','api_key_file'):
                if field in entry and (not isinstance(entry[field],str) or not entry[field]):
                    raise LLMConfigError(f'LLM {key!r}: invalid credential reference.')
            if 'thinking' in entry and (entry['provider']!='link' or not isinstance(entry['thinking'],bool)):
                raise LLMConfigError(f'LLM {key!r}: thinking must be true or false, and only applies to link.')
            url=entry.get('base_url')
            if entry['provider']=='openai' and url:
                raise LLMConfigError('The openai provider uses api.openai.com. Use link for a custom endpoint.')
            if entry['provider'] in {'link','ollama'} and entry.get('enabled',True):
                if not isinstance(url,str):raise LLMConfigError(f'LLM {key!r}: base_url is required.')
                parsed=urlsplit(url)
                if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise LLMConfigError(f'LLM {key!r}: base_url must be a plain HTTP(S) API base URL.')
        missing=set(TASKS)-set(tasks)
        if missing:raise LLMConfigError("Missing required LLM tasks: "+", ".join(sorted(missing)))
        self.routes={}
        for task in tasks:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}",task):raise LLMConfigError("Invalid LLM task key.")
            route=tasks.get(task)
            if isinstance(route,str):route={'llm':route}
            if not isinstance(route,dict) or route.get('llm') not in entries:
                raise LLMConfigError(f'Task {task!r} must reference a registered LLM key.')
            entry=entries[route['llm']]
            if not entry.get('enabled',True):raise LLMConfigError(f'Task {task!r} references a disabled LLM.')
            effort=route.get('reasoning_effort')
            if effort is not None and effort not in EFFORTS:raise LLMConfigError(f'Task {task!r}: invalid reasoning_effort.')
            if entry['provider']=='openai':
                if entry['model'].startswith(('gpt-6-luna','gpt-5.6-luna')) and effort=='minimal':
                    raise LLMConfigError(f'Task {task!r}: Luna supports none/low/medium, not minimal.')
                if entry['model'].startswith(('gpt-5-nano','gpt-5-mini')) and effort=='none':
                    raise LLMConfigError(f'Task {task!r}: this GPT-5 model requires minimal or higher reasoning.')
            budget=route.get('max_output_tokens')
            if budget is not None and (isinstance(budget,bool) or not isinstance(budget,int) or not 256<=budget<=32768):
                raise LLMConfigError(f'Task {task!r}: max_output_tokens must be between 256 and 32768.')
            self.routes[task]=copy.deepcopy(route)
        self.revision=hashlib.sha256(json.dumps(self.data,sort_keys=True).encode()).hexdigest()[:12]

    def describe(self):
        return {task:{'llm':route['llm'],'provider':self.data['llms'][route['llm']]['provider'],
                      'model':self.data['llms'][route['llm']]['model'],
                      **{k:v for k,v in route.items() if k in {'reasoning_effort','max_output_tokens'}}}
                for task,route in self.routes.items()}

    def models(self):
        return {task:self.data['llms'][route['llm']]['model'] for task,route in self.routes.items()}

    def invoke(self,task,prompt,schema,max_tokens=16384,reasoning_effort=None):
        from reader import backends
        task=task.removeprefix('task:')
        if task not in self.routes:raise LLMConfigError(f'Unknown LLM task: {task!r}.')
        route=self.routes[task];entry=self.data['llms'][route['llm']]
        budget=route.get('max_output_tokens',max_tokens)
        effort=route.get('reasoning_effort',reasoning_effort)
        key=credential(entry)
        if entry['provider']=='openai':
            return backends.openai(entry['model'],prompt,schema,budget,effort,key=key)
        if entry['provider']=='ollama':
            return backends.ollama(entry['model'],prompt,schema,budget,host=entry['base_url'],key=key)
        # Thinking tokens count against the output budget; a thinking model can spend it all before answering.
        extra={} if entry.get('thinking',True) else {'chat_template_kwargs':{'enable_thinking':False}}
        return backends.openai_compatible(entry['base_url'],entry['model'],prompt,schema,key,budget,temperature=0,**extra)


def load_registry(path):
    path=Path(path).expanduser()
    try:
        if path.stat().st_size>100_000:raise LLMConfigError('LLM config is too large.')
        data=json.loads(path.read_text())
    except OSError:raise LLMConfigError('LLM config file could not be read.') from None
    except json.JSONDecodeError:raise LLMConfigError('LLM config must be valid JSON.') from None
    return LLMRegistry(data)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config',nargs='?',default='llm-config.json')
    parser.add_argument('--test',action='store_true',help='Make one small test request per selected LLM (may incur provider charges).')
    args=parser.parse_args()
    registry=load_registry(args.config)
    print(json.dumps({'revision':registry.revision,'tasks':registry.describe()},indent=2))
    if args.test:
        tested=set()
        schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
        for task,route in registry.routes.items():
            if route['llm'] in tested:continue
            result=registry.invoke(task,'Return only {"ok":true}.',schema,max_tokens=512)
            if result!={'ok':True}:raise LLMConfigError(f'LLM {route["llm"]!r} failed the JSON smoke test.')
            tested.add(route['llm']);print(f'{route["llm"]}: connection and JSON response OK')

if __name__=='__main__':main()

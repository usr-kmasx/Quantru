"""Inference throughput from llama.cpp's own cumulative decode timings."""
from collections import deque
import math
import json
import urllib.request

class TokenStats:
    def __init__(self,context_limit=None):
        self.context_limit=context_limit
        self.total_n=0
        self.total_ms=0.0
        self.n=0
        self.ms=0.0
        self.samples=deque()

    @classmethod
    def for_engine(cls,port):
        # Read the actual per-slot context capacity (one slot in Quantru).
        # Do not delay or fail inference when an older engine lacks this field.
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/props',timeout=2) as response:
                limit=json.load(response)['default_generation_settings']['n_ctx']
            if type(limit) is int and limit>0:return cls(limit)
        except (OSError,ValueError,KeyError,TypeError):pass
        return cls()

    def next_round(self):
        self.total_n+=self.n
        self.total_ms+=self.ms
        self.n=0
        self.ms=0.0
        self.samples.clear()

    def update(self,chunk):
        timing=chunk.get('timings')
        if not isinstance(timing,dict):return None
        n,ms=timing.get('predicted_n'),timing.get('predicted_ms')
        if type(n) is not int or n<=0 or type(ms) not in (int,float) or not math.isfinite(ms) or ms<=0:return None
        if n<self.n or ms<self.ms:return None
        self.n,self.ms=n,float(ms)
        if not self.samples or self.samples[-1]!=(n,ms):self.samples.append((n,ms))
        while len(self.samples)>2 and self.samples[1][1]<ms-1000:self.samples.popleft()
        a,b=self.samples[0]
        current=(n-a)*1000/(ms-b) if n>a and ms>b else n*1000/ms
        count=self.total_n+n
        avg=count*1000/(self.total_ms+ms)
        result={'tokens':count,'current':round(current,2),'average':round(avg,2),'decode_ms':round(self.total_ms+ms,2)}
        # prompt_n excludes cache hits. Use only this inference round's
        # generated tokens, not the cumulative count across tool calls.
        cached,processed=timing.get('cache_n'),timing.get('prompt_n')
        if type(self.context_limit) is int and self.context_limit>0 and all(type(v) is int and v>=0 for v in (cached,processed)):
            used=cached+processed+n
            result['context_used']=used
            result['context_limit']=self.context_limit
        return result

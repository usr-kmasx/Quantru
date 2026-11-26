"""Inference throughput from llama.cpp's own cumulative decode timings."""
from collections import deque
import math

class TokenStats:
    def __init__(self):
        self.total_n=0
        self.total_ms=0.0
        self.n=0
        self.ms=0.0
        self.samples=deque()

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
        return {'tokens':count,'current':round(current,2),'average':round(avg,2),'decode_ms':round(self.total_ms+ms,2)}

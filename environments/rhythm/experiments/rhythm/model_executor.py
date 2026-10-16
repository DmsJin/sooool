"""Thin protocol adapter. All action times originate in the model's JSON.

Older pure additions are accepted; stale replacement/cancellation is rejected.
Versions remain monotonic and command IDs are first-writer-wins.
No pixel conversion, clock offset, phase fitting, matching, refractory period,
retiming, or automatic cancellation exists here. The owner supplies a browser
page and keeps its game/environment concerns outside this generic executor.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import re
from typing import Any

SCRIPT=Path(__file__).resolve().parents[2]/'dist/model-executor.js'
_ID=re.compile(r'^[A-Za-z0-9_-]{1,64}$')

def parse_commands(answer: str | dict[str,Any]) -> dict[str,Any]:
    tx=json.loads(answer) if isinstance(answer,str) else answer
    if not isinstance(tx,dict) or set(tx) not in ({'version','cancel_ids','taps'},{'version','cancel_ids','taps','replace_pending'}):
        raise ValueError('Expected version, cancel_ids, taps and optional replace_pending')
    if 'replace_pending' in tx and type(tx['replace_pending']) is not bool:
        raise ValueError('replace_pending must be boolean')
    if type(tx['version']) is not int or not 0<=tx['version']<=2**53-1:
        raise ValueError('version must be a nonnegative safe integer')
    def valid_id(value):return isinstance(value,str) and _ID.fullmatch(value) is not None
    cancels=tx['cancel_ids']
    if not isinstance(cancels,list) or len(cancels)>12 or not all(map(valid_id,cancels)) or len(set(cancels))!=len(cancels):
        raise ValueError('cancel_ids must contain at most 12 unique IDs')
    taps=tx['taps']
    if not isinstance(taps,list) or len(taps)>12:raise ValueError('At most 12 finite tap commands')
    ids=set()
    for tap in taps:
        if not isinstance(tap,dict) or set(tap)!={'id','key','at_ms','expires_ms'}:
            raise ValueError('Invalid tap fields')
        if not valid_id(tap['id']) or tap['id'] in ids or tap['key'] not in ('d','f','j','k'):
            raise ValueError('Invalid or duplicate tap ID/key')
        for field in ('at_ms','expires_ms'):
            if type(tap[field]) not in (int,float) or not math.isfinite(tap[field]):
                raise ValueError('Tap timestamps must be finite numbers')
        if tap['at_ms']<0 or tap['expires_ms']<tap['at_ms']:
            raise ValueError('Invalid timestamp ordering')
        ids.add(tap['id'])
    return tx

class ModelExecutor:
    def __init__(self,page):self._page=page

    async def install(self, *, before_navigation=False):
        source=SCRIPT.read_text()
        if before_navigation:await self._page.add_init_script(source)
        else:await self._page.evaluate(source)
        return self

    async def submit(self,answer: str | dict[str,Any]):
        payload=parse_commands(answer)
        return await self._page.evaluate('tx=>window.__modelExecutor.submit(tx)',payload)

    async def apply(self,answer: str | dict[str,Any]):
        return await self.submit(answer)

    async def snapshot(self,after_seq=0):
        return await self._page.evaluate('cursor=>window.__modelExecutor.snapshot(cursor)',after_seq)

    async def drain(self):
        """Run the identical timer routine after an externally controlled clock tick."""
        await self._page.evaluate('window.__modelExecutor.drain()')

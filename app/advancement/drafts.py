from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import json,os,re,tempfile,uuid
ID_RE=re.compile(r'^[a-z0-9][a-z0-9_-]*$'); USER_RE=re.compile(r'[^A-Za-z0-9_.@-]+')
DEFAULT_ADVANCEMENT_DRAFT_ROOT=Path('data/advancement_drafts')
class AdvancementDraftError(RuntimeError): pass
@dataclass(slots=True)
class AdvancementDraft:
    draft_id:str; owner:str; character_id:str; system_id:str; action_id:str; character_schema:int; base_updated_at:str; current_step:int; data:dict[str,Any]; created_at:str; updated_at:str; path:Path

def _now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _owner(x):
    s=USER_RE.sub('_',str(x).strip()).strip('._')
    if not s: raise AdvancementDraftError('Draft owner is invalid.')
    return s
def _path(owner,did,root):
    if not ID_RE.fullmatch(did): raise AdvancementDraftError('Invalid advancement draft id.')
    return root/_owner(owner)/f'{did}.json'
def _write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix='.'+path.stem+'.',suffix='.tmp',dir=path.parent); tp=Path(tmp)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as h: json.dump(payload,h,indent=2); h.write('\n'); h.flush(); os.fsync(h.fileno())
        os.replace(tp,path)
    finally: tp.unlink(missing_ok=True)
def save_advancement_draft(d,*,draft_root=DEFAULT_ADVANCEMENT_DRAFT_ROOT):
    d.updated_at=_now(); d.path=_path(d.owner,d.draft_id,Path(draft_root)); _write(d.path,{k:getattr(d,k) for k in ('draft_id','owner','character_id','system_id','action_id','character_schema','base_updated_at','current_step','data','created_at','updated_at')}); return d
def create_advancement_draft(owner,character_id,system_id,action_id,character_schema,base_updated_at,data,*,draft_root=DEFAULT_ADVANCEMENT_DRAFT_ROOT):
    now=_now(); d=AdvancementDraft(uuid.uuid4().hex[:12],owner,character_id,system_id,action_id,character_schema,base_updated_at,0,dict(data),now,now,Path()); return save_advancement_draft(d,draft_root=draft_root)
def load_advancement_draft(owner,draft_id,*,draft_root=DEFAULT_ADVANCEMENT_DRAFT_ROOT):
    p=_path(owner,draft_id,Path(draft_root))
    if not p.is_file(): raise AdvancementDraftError('Advancement draft does not exist.')
    try: x=json.loads(p.read_text())
    except Exception as exc: raise AdvancementDraftError(f'Could not read advancement draft: {exc}') from exc
    if x.get('owner')!=owner: raise AdvancementDraftError('Advancement draft owner mismatch.')
    return AdvancementDraft(x['draft_id'],x['owner'],x['character_id'],x['system_id'],x['action_id'],x['character_schema'],x['base_updated_at'],int(x.get('current_step',0)),x['data'],x['created_at'],x['updated_at'],p)
def delete_advancement_draft(owner,draft_id,*,draft_root=DEFAULT_ADVANCEMENT_DRAFT_ROOT): _path(owner,draft_id,Path(draft_root)).unlink(missing_ok=True)
def list_advancement_drafts(owner,*,draft_root=DEFAULT_ADVANCEMENT_DRAFT_ROOT):
    folder=Path(draft_root)/_owner(owner); out=[]
    if not folder.exists(): return out
    for p in folder.glob('*.json'):
        try: x=json.loads(p.read_text())
        except Exception: continue
        if x.get('owner')==owner: out.append(x)
    return sorted(out,key=lambda x:x.get('updated_at',''),reverse=True)

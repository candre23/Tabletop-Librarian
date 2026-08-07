from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re, yaml

ADVANCEMENT_FORMAT_VERSION=1
ID_RE=re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

@dataclass(slots=True)
class AdvancementIssue:
    severity:str; message:str; field:str|None=None
    def format(self):
        return f"{self.severity.upper()}: {self.field}: {self.message}" if self.field else f"{self.severity.upper()}: {self.message}"

@dataclass(slots=True)
class AdvancementStep:
    id:str; title:str; fields:list[str]; description:str=""; raw:dict[str,Any]=field(default_factory=dict)

@dataclass(slots=True)
class AdvancementAction:
    id:str; title:str; description:str; available_when:str|None; changes:dict[str,str]; steps:list[AdvancementStep]; raw:dict[str,Any]

@dataclass(slots=True)
class AdvancementWorkflow:
    path:Path; version:int; actions:list[AdvancementAction]; raw:dict[str,Any]
    def action(self, action_id:str):
        return next((x for x in self.actions if x.id==action_id),None)

def load_advancement_workflow(path, *, schema, engine):
    path=Path(path); issues=[]
    try: raw=yaml.safe_load(path.read_text())
    except FileNotFoundError: return None,[AdvancementIssue('error','Advancement workflow file does not exist.')]
    except yaml.YAMLError as exc: return None,[AdvancementIssue('error',f'Invalid YAML: {exc}')]
    if not isinstance(raw,dict): return None,[AdvancementIssue('error','Advancement workflow root must be a mapping/object.')]
    version=raw.get('version',1)
    if version!=1: issues.append(AdvancementIssue('error',f'Unsupported advancement workflow version {version}.','version'))
    actions=[]; seen=set()
    raw_actions=raw.get('actions')
    if not isinstance(raw_actions,list) or not raw_actions: issues.append(AdvancementIssue('error','actions must be a non-empty list.','actions')); raw_actions=[]
    for ai,a in enumerate(raw_actions):
        loc=f'actions[{ai}]'
        if not isinstance(a,dict): issues.append(AdvancementIssue('error','Action must be a mapping/object.',loc)); continue
        aid=a.get('id')
        if not isinstance(aid,str) or not ID_RE.fullmatch(aid): issues.append(AdvancementIssue('error','Invalid action id.',loc+'.id')); continue
        if aid in seen: issues.append(AdvancementIssue('error','Duplicate action id.',loc+'.id')); continue
        seen.add(aid)
        title=a.get('title',aid.replace('_',' ').title()); desc=a.get('description','') or ''
        available=a.get('available_when')
        if available is not None:
            if not isinstance(available,str) or not available.strip(): issues.append(AdvancementIssue('error','available_when must be a non-empty expression.',loc+'.available_when')); available=None
            else:
                try:
                    deps=engine.expression_dependencies(available)
                    unknown=[x for x in deps if x not in schema.fields and x not in engine.modifiers]
                    if unknown: issues.append(AdvancementIssue('error','Unknown available_when fields: '+', '.join(unknown),loc+'.available_when'))
                except Exception as exc: issues.append(AdvancementIssue('error',f'Invalid available_when expression: {exc}',loc+'.available_when'))
        changes=a.get('changes',{})
        if not isinstance(changes,dict) or not changes: issues.append(AdvancementIssue('error','changes must be a non-empty mapping.',loc+'.changes')); changes={}
        clean_changes={}
        for fid,expr in changes.items():
            if fid not in schema.fields: issues.append(AdvancementIssue('error',f'Unknown changed field {fid!r}.',loc+'.changes')); continue
            if schema.fields[fid].type=='calculated': issues.append(AdvancementIssue('error','Calculated fields cannot be advancement change targets.',loc+'.changes.'+fid)); continue
            if not isinstance(expr,str) or not expr.strip(): issues.append(AdvancementIssue('error','Change expression must be non-empty.',loc+'.changes.'+fid)); continue
            try: engine.expression_dependencies(expr)
            except Exception as exc: issues.append(AdvancementIssue('error',f'Invalid change expression: {exc}',loc+'.changes.'+fid)); continue
            clean_changes[fid]=expr
        steps=[]; used=set()
        rs=a.get('steps',[])
        if not isinstance(rs,list): issues.append(AdvancementIssue('error','steps must be a list.',loc+'.steps')); rs=[]
        for si,s in enumerate(rs):
            sl=f'{loc}.steps[{si}]'
            if not isinstance(s,dict): issues.append(AdvancementIssue('error','Step must be a mapping/object.',sl)); continue
            sid=s.get('id')
            if not isinstance(sid,str) or not ID_RE.fullmatch(sid): issues.append(AdvancementIssue('error','Invalid step id.',sl+'.id')); continue
            fields=s.get('fields',[])
            if not isinstance(fields,list) or not fields: issues.append(AdvancementIssue('error','fields must be a non-empty list.',sl+'.fields')); fields=[]
            clean=[]
            for fid in fields:
                if fid not in schema.fields: issues.append(AdvancementIssue('error',f'Unknown character field {fid!r}.',sl+'.fields')); continue
                if schema.fields[fid].type=='calculated': issues.append(AdvancementIssue('error','Calculated fields cannot be direct advancement inputs.',sl+'.fields')); continue
                if fid in used: issues.append(AdvancementIssue('error',f'Field {fid!r} appears in more than one advancement step.',sl+'.fields')); continue
                used.add(fid); clean.append(fid)
            steps.append(AdvancementStep(sid,str(s.get('title') or sid.replace('_',' ').title()),clean,str(s.get('description') or ''),dict(s)))
        if not steps: steps=[AdvancementStep('review','Review',[], 'Review the advancement before applying it.')]
        actions.append(AdvancementAction(aid,str(title),str(desc),available,clean_changes,steps,dict(a)))
    if any(i.severity=='error' for i in issues): return None,issues
    return AdvancementWorkflow(path,version,actions,raw),issues

"""Export visible messages/tools, never hidden reasoning or authentication payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PATTERNS=[(r'gh[pousr]_[A-Za-z0-9_]{20,}', '[REDACTED_GITHUB_TOKEN]'),
 (r'github_pat_[A-Za-z0-9_]{20,}', '[REDACTED_GITHUB_TOKEN]'),
 (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]'),
 (r'UbuntuAll\d+', '[REDACTED_SSH_PASSWORD]'),(r'(?i)(sshpass\s+-p\s+)(?:\x27[^\x27]*\x27|\"[^\"]*\"|[^\s;]+)',r'\1[REDACTED]'),
 (r'sk-[A-Za-z0-9_-]{10,}', '[REDACTED_API_KEY]'),
 (r'AKIA[A-Z0-9]{16}', '[REDACTED_AWS_ACCESS_KEY_ID]'),
 (r'(?i)(X-Amz-(?:Credential|Signature|Security-Token)=)[^&\s\"\x27\\]+', r'\1[REDACTED]'),
 (r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED_JWT]'),
 (r'(?i)(Bearer\s+)[A-Za-z0-9._-]{15,}',r'\1[REDACTED]'),
 (r'(?i)([\"\x27]?(?:access_token|refresh_token|id_token|api_key|password)[\"\x27]?\s*[:=]\s*[\"\x27])([^\"\x27\n]{8,})([\"\x27])',r'\1[REDACTED]\3')]
def scrub(text):
 for pattern,replacement in PATTERNS:text=re.sub(pattern,replacement,text)
 return text

def clean(value):
 if isinstance(value,str):return scrub(value)
 if isinstance(value,dict):
  return {k:('[REDACTED]'if k.lower()in {'access_token','refresh_token','id_token','api_key','password'}else clean(v))for k,v in value.items()}
 if isinstance(value,list):return [clean(v)for v in value]
 return value

def export(source,dest):
 dest.mkdir(parents=True,exist_ok=True);rows=[];excluded=0
 for line in source.open():
  try:r=json.loads(line)
  except json.JSONDecodeError:continue
  p=r.get('payload',{});typ=p.get('type')
  if r.get('type')!='response_item' or typ=='reasoning':continue
  if typ=='message':
   if p.get('role')not in ('user','assistant'):continue
   # Drop injected machine/configuration messages; retain visible task conversation.
   text='\n'.join(c.get('text','')for c in p.get('content',[])if c.get('type')in ('input_text','output_text'))
   if not text or '<environment_context>'in text or '<external_codex_apps_open_page>'in text or text.startswith('# AGENTS.md instructions'):continue
   item={'timestamp':r.get('timestamp'),'type':'message','role':p['role'],'text':text}
  elif typ in ('function_call','function_call_output','custom_tool_call','custom_tool_call_output'):
   item={'timestamp':r.get('timestamp'),'type':typ,**{k:p[k]for k in ('name','call_id','arguments','input','output')if k in p}}
   raw=json.dumps(item)
   # Interactive stdin containing secrets is omitted, rather than guessed at.
   if ('write_stdin'in raw or 'terminal_write'in raw)and ('chars'in raw or 'text'in raw):
    item={'timestamp':r.get('timestamp'),'type':typ,'call_id':p.get('call_id'),'omitted':'interactive terminal input potentially containing credentials'};excluded+=1
  else:continue
  cleaned=clean(item);rows.append(cleaned)
 (dest/'trajectory.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in rows))
 messages=[x for x in rows if x['type']=='message']
 (dest/'conversation.md').write_text('\n\n'.join('### '+x['role']+' '+str(x['timestamp'])+'\n\n'+x['text']for x in messages))
 (dest/'manifest.json').write_text(json.dumps({'source_filename':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'records':len(rows),'messages':len(messages),'omitted_interactive_inputs':excluded,'scope':'visible exported messages/tools only; hidden reasoning excluded; secrets redacted; local research archive, review before public release'},indent=2))
 print(dest.name,len(rows),len(messages))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('dest',type=Path);a=p.parse_args();export(a.source,a.dest)

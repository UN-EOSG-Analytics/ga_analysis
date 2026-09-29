import hashlib,json
import time
from pathlib import Path

def atomic_replace(source,destination):
 # Windows indexers/Office may hold a completed output briefly; never delete it first.
 for attempt in range(6):
  try:return Path(source).replace(destination)
  except PermissionError:
   if attempt==5:raise
   time.sleep(.05*2**attempt)

def read_jsonl(path):
 with Path(path).open(encoding='utf-8-sig') as f:
  for line_no,line in enumerate(f,1):
   if line.strip():
    try:yield json.loads(line)
    except json.JSONDecodeError as e:raise ValueError(f'{path}:{line_no}: invalid JSON') from e

def write_jsonl(path,rows):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 # Atomic replacement prevents half-written derived datasets.
 tmp=path.with_suffix(path.suffix+'.tmp')
 with tmp.open('w',encoding='utf8') as f:
  for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
 atomic_replace(tmp,path)

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def stable_hash(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def workspace_path(root,value):
 root=Path(root).resolve();path=(root/value).resolve()
 if not path.is_relative_to(root):raise ValueError(f'Path leaves project: {value}')
 return path

import argparse,json
from pathlib import Path
from .pipeline import status,ingest,register

def main():
 p=argparse.ArgumentParser(description='UNGA analysis input and cache architecture')
 p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('status')
 q=sub.add_parser('register');q.add_argument('manifest',type=Path)
 q=sub.add_parser('ingest');q.add_argument('--year',type=int);q.add_argument('--source-id')
 a=p.parse_args()
 try:
  if a.command=='status':result=status(a.root)
  elif a.command=='register':result=register(a.root,a.manifest)
  else:result=ingest(a.root,a.year,a.source_id)
 except (ValueError,OSError,KeyError) as e:p.exit(2,f'Input validation failed: {e}\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

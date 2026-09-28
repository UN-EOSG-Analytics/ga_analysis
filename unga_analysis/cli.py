import argparse,json
from pathlib import Path
from .pipeline import status,ingest,register

def main():
 p=argparse.ArgumentParser(description='UNGA analysis input and cache architecture')
 p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('status')
 sub.add_parser('prepare',help='Rebuild canonical English speeches and normalize all accepted years locally')
 sub.add_parser('screen',help='Find local AI term candidates; preserve Pending labels and make no API calls')
 q=sub.add_parser('register');q.add_argument('manifest',type=Path)
 q=sub.add_parser('ingest');q.add_argument('--year',type=int);q.add_argument('--source-id')
 for name in ('analyze','review','discover','classify','aggregate','report'):
  q=sub.add_parser(name,help='Analysis workflow; without --execute performs a local readiness check only')
  q.add_argument('--execute',action='store_true',help='Explicitly authorize API calls within the cost cap')
  q.add_argument('--max-cost-usd',type=float,help='Cumulative API cost cap; default is in config/analysis.toml')
  q.add_argument('--allow-partial',action='store_true',help='Generate an explicitly interim report from a partial session')
  q.add_argument('--final-day',type=Path,help='Path to the 2026 Day 6 English TXT/JSON; copied as an immutable source on execution')
 a=p.parse_args()
 try:
  if a.command=='status':result=status(a.root)
  elif a.command=='prepare':
   from .preparation.publish import prepare
   result=prepare(a.root)
  elif a.command=='screen':
   from .screening import screen
   result=screen(a.root)
  elif a.command=='register':result=register(a.root,a.manifest)
  elif a.command in ('analyze','review','discover','classify','aggregate','report'):
   from .analysis.workflow import run
   result=run(a.root,execute=a.execute,budget=a.max_cost_usd,allow_partial=a.allow_partial,
              final_day=a.final_day,stop_after='report' if a.command=='analyze' else a.command)
  else:result=ingest(a.root,a.year,a.source_id)
 except (ValueError,OSError,KeyError,RuntimeError) as e:p.exit(2,f'Workflow stopped: {e}\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

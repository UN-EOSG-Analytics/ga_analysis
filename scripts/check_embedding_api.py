"""One short embedding request; never prints or stores credentials."""
import json
import os
from pathlib import Path
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT/'config/analysis.toml').open('rb') as handle:
        config = tomllib.load(handle)['discovery']
    key = os.environ.get(config['api_key_env'], '').strip()
    env_file = ROOT/'.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() == config['api_key_env']:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                key = value.strip()
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'model': config['model'], 'success': False,
              'scope': 'single_test_sentence_only; no corpus data sent'}
    if not key:
        result['status'] = 'key_missing; set OPENAI_API_KEY in project .env'
    else:
        body = json.dumps({'model': config['model'], 'input': 'Embedding connection test.',
                           'dimensions': config['dimensions'], 'encoding_format': 'float'}).encode()
        request = Request('https://api.openai.com/v1/embeddings', data=body,
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
            dimension = len(payload['data'][0]['embedding'])
            result.update(success=dimension == config['dimensions'],
                          status='ok' if dimension == config['dimensions'] else 'unexpected_dimensions',
                          dimensions=dimension, total_tokens=payload.get('usage', {}).get('total_tokens'))
        except HTTPError as error:
            # Authentication error bodies may repeat part of a key. Never print them.
            result.update(status='http_error', http_status=error.code)
        except (URLError, TimeoutError, OSError):
            result['status'] = 'network_or_connection_error'
        except (KeyError, IndexError, TypeError, ValueError):
            result['status'] = 'unexpected_response'
    destination = ROOT/'output/diagnostics/embedding_api_check.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())

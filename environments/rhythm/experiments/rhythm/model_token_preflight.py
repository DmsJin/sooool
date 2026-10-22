"""Count one fixed-size visual input; retain a full financial reservation.

This runs before gameplay and never interprets the image or makes a game action.
Counting-endpoint billing is not assumed free: its original conservative
reservation remains uncertain even after a successful count response.
"""
import argparse, asyncio, base64, getpass, json, struct, uuid
from pathlib import Path
import httpx
from .scheduler import BudgetLedger, TokenPricing

async def run(args, key):
    if not (Path(args.run_root) / 'budget.json').is_file():
        raise RuntimeError('Existing cumulative budget.json required; refusing a fresh paid budget')
    output = Path(args.output)
    if output.exists():
        raise ValueError('Refusing to overwrite token certificate')
    png = Path(args.image).read_bytes()
    if png[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
        raise ValueError('Expected a PNG image')
    width, height = struct.unpack('>II', png[16:24])
    payload = {'model': 'gpt-6.1-sol', 'reasoning': {'effort': 'low'},
               'text': {'verbosity': 'low'}, 'input': [{'role': 'user', 'content': [
                   {'type': 'input_text', 'text': ''},
                   {'type': 'input_image', 'detail': args.detail,
                    'image_url': 'data:image/png;base64,' + base64.b64encode(png).decode()}]}]}
    ledger = BudgetLedger.existing(Path(args.run_root) / 'budget.json')
    if (Path(args.run_root) / 'budget.remote-owner.json').exists():
        raise RuntimeError('Budget is owned by another verifier')
    rid = uuid.uuid4().hex
    ledger.reserve(rid, TokenPricing('15', '60').cost_usd(4096 + 8192, 0), 'accounting')
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post('https://api.openai.com/v1/responses/input_tokens',
                headers={'Authorization': 'Bearer ' + key}, json=payload)
            if response.status_code != 200:
                raise RuntimeError('Token counter HTTP ' + str(response.status_code))
            data = response.json()
        count = data.get('input_tokens')
        if data.get('object') != 'response.input_tokens' or type(count) is not int or not 0 < count <= 12288:
            raise ValueError('Unexpected token counting response')
        certificate = {'schema': 1, 'model': payload['model'], 'detail': args.detail,
            'width': width, 'height': height, 'framed_image_input_tokens': count,
            'response_object': data['object'],
            'billing': 'full_uncertain_reservation_retained', 'ledger_request_id': rid,
            'reserved_micros': 184320,
            'reference': 'https://developers.openai.com/api/docs/guides/token-counting'}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(certificate, indent=2))
        print(json.dumps(certificate), flush=True)
    finally:
        ledger.mark_uncertain(rid, 'Counting endpoint billing unestablished; retain full original bound')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True); p.add_argument('--output', required=True)
    p.add_argument('--run-root', required=True); p.add_argument('--detail', choices=('high', 'low'), default='high')
    args = p.parse_args()
    asyncio.run(run(args, getpass.getpass('API key (process memory only): ')))

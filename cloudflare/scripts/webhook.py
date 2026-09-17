"""Configure Telegram webhook using local secrets, never tokens in command arguments."""
import argparse
import getpass
import json
import re
import urllib.request
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', help='HTTPS Worker URL, e.g. https://name.account.workers.dev')
    parser.add_argument('--remove', action='store_true', help='Remove webhook before returning to local polling')
    args = parser.parse_args()
    config = {}
    for filename in (Path(__file__).resolve().parents[2] / '.env', Path(__file__).resolve().parents[1] / '.dev.vars'):
        if filename.exists():
            for line in filename.read_text(encoding='utf-8-sig').splitlines():
                if line.strip() and not line.lstrip().startswith('#'):
                    k, v = line.split('=', 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    token = config.get('BOT_TOKEN')
    if not token or token == 'replace_me':
        token = getpass.getpass('Bot token (ko‘rinmaydi): ')
    if args.remove:
        method, payload = 'deleteWebhook', {'drop_pending_updates': False}
    else:
        if not args.url or not re.fullmatch(r'https://[a-zA-Z0-9.-]+(?::443)?/?', args.url):
            raise ValueError('Worker HTTPS manzili kerak.')
        secret = config.get('WEBHOOK_SECRET') or getpass.getpass('Worker WEBHOOK_SECRET (ko‘rinmaydi): ')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
            raise ValueError('Webhook maxfiy qiymati kamida 32 belgi bo‘lsin.')
        method = 'setWebhook'
        payload = {'url': args.url.rstrip('/') + '/webhook', 'secret_token': secret,
                   'allowed_updates': ['message', 'callback_query'], 'max_connections': 1, 'drop_pending_updates': False}
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
                                     data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        if not json.load(response).get('ok'):
            raise RuntimeError('Telegram rad etdi.')
    print('Webhook olib tashlandi.' if args.remove else 'Webhook sozlandi. Telegram orqali botni sinang.')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Webhook sozlanmadi: ' + type(error).__name__) from None

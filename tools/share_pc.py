"""Run the protected PC gateway and temporary tunnel; Ctrl+C stops both."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cloudflared', default=None)
    args = parser.parse_args()
    binary = args.cloudflared or shutil.which('cloudflared')
    if not binary and (ROOT/'.tools/cloudflared.exe').exists():
        binary = str(ROOT/'.tools/cloudflared.exe')
    if not binary:
        raise SystemExit('Install cloudflared first: https://developers.cloudflare.com/tunnel/downloads/')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8001)) == 0:
            raise SystemExit('Port 8001 is already in use. Stop the earlier shared server first.')
    private = ROOT/'.shared'
    private.mkdir(exist_ok=True)
    config = private/'credentials.json'
    if not config.exists():
        config.write_text(json.dumps({'user':'journey', 'password':secrets.token_urlsafe(24),
                                      'bridge':secrets.token_urlsafe(32)}), encoding='utf8')
        if os.name != 'nt':
            config.chmod(0o600)
    credentials = json.loads(config.read_text(encoding='utf8'))
    environment = dict(os.environ, FLIGHT_BRIDGE_TOKEN=credentials['bridge'])
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    children = []
    log = (private/'pc-server.log').open('a', encoding='utf8')
    ready = threading.Event()
    try:
        server = subprocess.Popen([sys.executable,'-m','flightcore.pc_bridge'],
            cwd=ROOT, env=environment, stdout=log, stderr=log, creationflags=flags)
        children.append(server)
        for _ in range(50):
            if server.poll() is not None:
                raise SystemExit('PC gateway failed. See .shared/pc-server.log.')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',8001)) == 0:
                    break
            time.sleep(.1)
        else:
            raise SystemExit('PC gateway did not start.')
        tunnel = subprocess.Popen([binary,'--no-autoupdate','tunnel','--url','http://127.0.0.1:8001'],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf8', errors='replace', creationflags=flags)
        children.append(tunnel)

        def read_tunnel():
            with (private/'tunnel.log').open('a',encoding='utf8') as tunnel_log:
                for line in tunnel.stdout:
                    tunnel_log.write(line)
                    tunnel_log.flush()
                    match = re.search(r'https://[-a-z0-9]+\.trycloudflare\.com',line)
                    if match and not ready.is_set():
                        values = {'FLIGHT_SHARE_USER':credentials['user'],
                            'FLIGHT_SHARE_PASSWORD':credentials['password'],
                            'FLIGHT_BRIDGE_TOKEN':credentials['bridge'],
                            'FLIGHT_PC_URL':match.group()}
                        target = ROOT/'.env.vercel-pc'
                        target.write_text(''.join(f'{k}={v}\n' for k,v in values.items()),encoding='utf8')
                        if os.name != 'nt':
                            target.chmod(0o600)
                        print('PC link prepared. Import .env.vercel-pc into Vercel; never commit or share this file.',flush=True)
                        print('Keep this process and the PC awake. Ctrl+C stops sharing.',flush=True)
                        ready.set()
        threading.Thread(target=read_tunnel,daemon=True).start()
        deadline = time.monotonic()+45
        while all(child.poll() is None for child in children):
            if not ready.is_set() and time.monotonic()>deadline:
                raise SystemExit('Tunnel did not start. See .shared/tunnel.log.')
            time.sleep(.5)
        raise SystemExit('A sharing process stopped. See .shared logs; restart to reconnect.')
    except KeyboardInterrupt:
        print('Stopping PC sharing.')
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
        log.close()


if __name__ == '__main__':
    main()

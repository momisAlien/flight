"""Loopback-only gateway. Only the authenticated Vercel relay may reach the app."""
import os
import secrets
from pathlib import Path
from starlette.responses import JSONResponse
from .server import create_app
from .shared_jobs import SharedJobs


class Bridge:
    def __init__(self, app, token):
        if len(token) < 32:
            raise ValueError('FLIGHT_BRIDGE_TOKEN은 32자 이상이어야 합니다')
        self.app, self.token = app, token.encode('ascii')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        supplied = headers.get(b'x-flight-bridge', b'')
        if not secrets.compare_digest(supplied, self.token):
            return await JSONResponse({'detail': '연결 인증 필요'}, status_code=401)(
                scope, receive, send)
        if scope['path'] == '/healthz':
            return await JSONResponse({'status': 'online'}, headers={'Cache-Control': 'no-store'})(
                scope, receive, send)
        if scope['method'] == 'POST' and (
            scope['path'] in ('/api/browser-jobs', '/api/reference-jobs') or
            scope['path'].endswith(('/details', '/resume-details'))):
            return await JSONResponse(
                {'detail': '공유 모드에서는 최저가 통합 검색을 이용하세요.'}, status_code=409)(
                    scope, receive, send)
        # Caller-origin checks are enforced by Vercel before injecting the token.
        # Keep the original app's CSRF check. Do not trust proxy-supplied Host/Origin.
        clean = [(k, v) for k, v in scope['headers'] if k not in (
            b'host', b'origin', b'x-flight-bridge', b'authorization',
            b'forwarded', b'x-forwarded-host', b'x-forwarded-proto', b'sec-fetch-site')]
        clean.extend([(b'host', b'localhost'), (b'origin', b'http://localhost'),
                      (b'sec-fetch-site', b'same-origin')])
        scope = dict(scope, headers=clean)
        return await self.app(scope, receive, send)


def build_bridge():
    # Never use the owner's personal.db for a shared instance.
    token = os.environ.get('FLIGHT_BRIDGE_TOKEN', '')
    if len(token) < 32:
        raise ValueError('FLIGHT_BRIDGE_TOKEN 설정이 필요합니다')
    db = Path(os.environ.get('FLIGHT_SHARED_DB', '.shared/shared.db'))
    db.parent.mkdir(parents=True, exist_ok=True)
    return Bridge(create_app(str(db), combined_factory=SharedJobs), token)


if __name__ == '__main__':
    import uvicorn
    config = Path('.env.pc')
    if config.exists():
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name in ('FLIGHT_BRIDGE_TOKEN', 'FLIGHT_SHARED_DB'):
                os.environ.setdefault(name, value.strip())
    uvicorn.run(build_bridge(), host='127.0.0.1', port=8001, workers=1,
                proxy_headers=False, access_log=False)

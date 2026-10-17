"""Same-origin local app with official stored references; no booking/payment."""
import argparse
import ipaddress
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from .bulk import parse_csv,template
from .core import parse_korean
from .serde import conditions_from_dict,quote_from_dict,dumps
from .store import Store
from .review import coverage,quote_reasons
from .jobs import Jobs
from .reference_jobs import ReferenceJobs,tasks
from .browser_jobs import BrowserJobs
from .combined_jobs import CombinedJobs
from .browser_prices import validate as validate_browser
from .core import estimate

STATIC=Path(__file__).parent/"web"
MAX_BODY=2*1024*1024


def lan_address(value):
    address=ipaddress.ip_address(value)
    ranges=(ipaddress.ip_network("10.0.0.0/8"),ipaddress.ip_network("172.16.0.0/12"),ipaddress.ip_network("192.168.0.0/16"))
    if not any(address in network for network in ranges):
        raise argparse.ArgumentTypeError("모바일 공유는 이 PC의 사설 IPv4 주소만 사용할 수 있습니다")
    return str(address)


def server_parser():
    p=argparse.ArgumentParser(description="개인용 항공권 수동 비교 서버")
    p.add_argument("--port",type=int,default=8000)
    p.add_argument("--db",default="personal.db")
    p.add_argument("--lan",type=lan_address,metavar="이_PC의_사설_IP",help="명시적으로 같은 네트워크 접속 허용. 공유 위험 안내 표시")
    return p


def create_app(db_path,lan=None):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    jobs=Jobs(db_path)
    reference_jobs=ReferenceJobs(db_path)
    browser_jobs=BrowserJobs(db_path)
    combined_jobs=CombinedJobs(db_path,browser_jobs,reference_jobs)
    token=secrets.token_urlsafe(32)
    hosts={"127.0.0.1","localhost"}
    if lan:
        hosts.add(lan_address(lan))

    @app.middleware("http")
    async def protect(request,call_next):
        host=urlsplit("http://"+request.headers.get("host","")).hostname
        if host not in hosts:
            return JSONResponse({"detail":"허용되지 않은 Host"},400)
        if request.headers.get("sec-fetch-site") in ("cross-site","same-site"):
            return JSONResponse({"detail":"동일 출처 요청만 허용됩니다"},403)
        if request.method not in ("GET","HEAD"):
            origin=request.headers.get("origin")
            if origin and urlsplit(origin).netloc!=request.headers.get("host"):
                return JSONResponse({"detail":"다른 출처의 변경 요청을 거부했습니다"},403)
            if not secrets.compare_digest(request.headers.get("x-csrf-token",""),token):
                return JSONResponse({"detail":"화면을 새로고침한 뒤 다시 시도하세요"},403)
            if request.headers.get("content-type","").split(";")[0]!="application/json":
                return JSONResponse({"detail":"JSON 요청이 필요합니다"},415)
            chunks=[]; size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>MAX_BODY:
                    return JSONResponse({"detail":"입력이 2 MiB를 초과합니다. 나누어 입력하세요. 저장된 행은 없습니다"},413)
                chunks.append(chunk)
            request._body=b"".join(chunks)
        response=await call_next(request)
        response.headers["Cache-Control"]="no-store"
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Referrer-Policy"]="no-referrer"
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    @app.exception_handler(TypeError)
    @app.exception_handler(KeyError)
    @app.exception_handler(ArithmeticError)
    async def bad_input(request,exc):
        return JSONResponse({"detail":str(exc)},422)

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request,exc):
        return JSONResponse({"detail":"입력ID가 중복됩니다. 기존 입력을 확인하세요. 일괄 저장은 전부 취소됐습니다"},409)

    def encoded(obj):
        return json.loads(dumps(obj))

    @app.get("/")
    def home():
        return FileResponse(STATIC/"index.html")

    @app.get("/api/config")
    def config():
        return {"csrf":token,"lan":bool(lan),"lan_address":lan,"version":"3.0-local",
                "notice":"같은 네트워크에서 접근 가능한 사람이 입력 내용을 보고 변경할 수 있습니다. HTTP는 암호화되지 않습니다. 신뢰하는 사설망에서만 사용하고 공유가 끝나면 서버를 종료하세요." if lan else "127.0.0.1 · 이 PC에서만 접속",
                "external_status":"Google·네이버 관찰 및 마이리얼트립 참고 조회 연결 · 확정 운임 자동 비교 미연동","travelpayouts":"약관 확인 대기 · 연동 코드 없음"}

    def combined_idle():
        if combined_jobs.thread and combined_jobs.thread.is_alive():
            raise ValueError('통합 검색 진행 중에는 별도 조회를 시작할 수 없습니다')

    @app.post('/api/combined-plan')
    async def combined_plan(request:Request):
        c=conditions_from_dict((await request.json())['conditions'])
        validate_browser(c,'naver');validate_browser(c,'google')
        try:reference_count=sum(1 for _ in tasks(c))
        except ValueError:reference_count=None
        return {'browser_queries':estimate(c)['base_total_per_provider']*2,'reference_queries':reference_count,
                'notice':'세 서비스를 동시에 조회합니다. 왕복 상위20·편도 조합 상위20으로 표시. 마이리얼트립은 저장 왕복 참고가만 지원하며 지원하지 않는 조건은 건너뜁니다. 로그인·접근 제한 시 해당 공급사를 중단합니다.'}

    @app.post('/api/combined-jobs')
    async def combined_start(request:Request):
        c=conditions_from_dict((await request.json())['conditions'])
        return {'id':combined_jobs.start(c)}

    @app.get('/api/combined-jobs/{id}')
    def combined_status(id:str):return combined_jobs.status(id)

    @app.get('/api/combined-history')
    def combined_history():return {'items':combined_jobs.history()}

    @app.post('/api/combined-jobs/{id}/cancel')
    def combined_cancel(id:str):
        combined_jobs.cancel(id);return {'requested':True}

    @app.post("/api/reference-plan")
    async def reference_plan(request:Request):
        c=conditions_from_dict((await request.json())["conditions"])
        return {"requests":sum(1 for _ in tasks(c)),"cost":"요금 미확인 · 유료 플랜 가입 없음",
                "notice":"저장된 직항 왕복 참고 가격만 조회합니다. 시간·귀국 마감·수하물 필터와 실시간 편도 비교는 적용하지 않습니다."}

    @app.post("/api/browser-plan")
    async def browser_plan(request:Request):
        body=await request.json()
        c=conditions_from_dict(body["conditions"])
        validate_browser(c,body["provider"])
        return {"queries":estimate(c)["base_total_per_provider"],
                "notice":"실험 기능 · 현재 로드된 가격 카드만 관찰하며 판매처·수하물·전체 재고·왕복 예약 운임은 확정하지 않습니다. 읽을 수 있는 일정의 시간·소요시간·귀국 마감을 점검하며 미확인 조건도 표시합니다. 중간 기착은 상세 확인이 필요합니다. Chrome과 requirements-browser.txt 설치 필요. 최초 실행 시 Selenium이 공식 드라이버를 다운로드할 수 있습니다."}

    @app.post("/api/browser-jobs")
    async def browser_start(request:Request):
        combined_idle()
        body=await request.json()
        return {"id":browser_jobs.start(conditions_from_dict(body["conditions"]),body["provider"])}

    @app.get("/api/browser-jobs/{id}")
    def browser_status(id:str,page:int=1):
        return browser_jobs.status(id,page)

    @app.get('/api/browser-jobs/{id}/price-summary')
    def browser_price_summary(id:str):
        return browser_jobs.price_summary(id)

    @app.get('/api/browser-jobs/{id}/candidate-comparisons')
    def browser_candidates(id:str,page:int=1):
        return browser_jobs.candidate_comparisons(id,page)

    @app.post("/api/browser-jobs/{id}/cancel")
    def browser_cancel(id:str):
        browser_jobs.cancel(id)
        return {"requested":True}

    @app.post("/api/reference-jobs")
    async def reference_start(request:Request):
        combined_idle()
        c=conditions_from_dict((await request.json())["conditions"])
        return {"id":reference_jobs.start(c)}

    @app.get('/api/browser-jobs/{id}/detail-plan')
    def browser_detail_plan(id:str):
        preview=browser_jobs.detail_plan(id)
        return {k:v for k,v in preview.items() if k not in ('candidates','skipped')}

    @app.post('/api/browser-jobs/{id}/details')
    def browser_details(id:str):
        combined_idle()
        return {'id':browser_jobs.start_details(id)}

    @app.post('/api/browser-jobs/{id}/resume-details')
    def browser_resume_details(id:str):
        combined_idle()
        return {'id':browser_jobs.resume_pending_details(id)}

    @app.get("/api/reference-jobs/{id}")
    def reference_status(id:str):
        return reference_jobs.status(id)

    @app.post("/api/reference-jobs/{id}/cancel")
    def reference_cancel(id:str):
        state=reference_jobs.status(id)
        if state["status"]=="running":
            reference_jobs.cancelled.set()
        return {"requested":True}

    @app.post("/api/parse")
    async def parse(request:Request):
        return parse_korean((await request.json())["text"])

    @app.post("/api/dashboard")
    async def dashboard(request:Request):
        body=await request.json(); c=conditions_from_dict(body["conditions"])
        page=int(body.get("page",1))
        if page<1:
            raise ValueError("페이지 번호가 올바르지 않습니다")
        with Store(db_path) as store:
            cover=coverage(store.all_quotes,c)
            total=store.db.execute("SELECT COUNT(*) FROM manual_quotes").fetchone()[0]
            rows=store.db.execute("SELECT payload FROM manual_quotes ORDER BY id LIMIT 25 OFFSET ?",((page-1)*25,))
            records=[]
            for row in rows:
                q=quote_from_dict(json.loads(row[0]))
                records.append({"quote":q,"reasons":quote_reasons(q,c,datetime.now(timezone.utc))})
            return encoded({"coverage":cover,"inputs":{"items":records,"total":total,"page":page,"pages":max(1,(total+24)//25)},
                            "references":list(store.references())})

    @app.post("/api/manual")
    async def manual(request:Request):
        data=await request.json()
        for key in ("taxes_included","mandatory_fees_included","baggage_confirmed"):
            if key not in data:
                raise ValueError(f"필수 확인 선택 누락: {key}")
        for leg in data["legs"]:
            for segment in leg["segments"]:
                if "intermediate_stops" not in segment:
                    raise ValueError("중간 기착은 0/1/미확인을 선택해야 합니다")
        q=quote_from_dict(data)
        with Store(db_path) as store:
            store.add_manual(q)
        return {"saved":q.id,"label":"수동 입력 · 외부 검증 안 됨"}

    @app.post("/api/manual/delete")
    async def delete(request:Request):
        body=await request.json()
        with Store(db_path) as store:
            store.delete_manual(body["id"])
        return {"deleted":body["id"]}

    @app.get("/api/csv-template")
    def csv_template():
        return Response(template(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=manual-input-template.csv"})

    @app.post("/api/csv/preview")
    async def csv_preview(request:Request):
        text=(await request.json())["text"]
        quotes,errors=parse_csv(text)
        with Store(db_path) as store:
            existing={r[0] for r in store.db.execute("SELECT id FROM manual_quotes")}
        for q in quotes:
            if q.id in existing:
                errors.append({"id":q.id,"message":"이미 저장된 입력ID"})
        # Stateless receipt: data are re-parsed and rechecked at commit.
        import hashlib,hmac
        receipt=hmac.new(token.encode(),text.encode(),hashlib.sha256).hexdigest()
        return encoded({"quotes":quotes,"errors":errors,"count":len(quotes),"receipt":receipt,"can_save":bool(quotes) and not errors})

    @app.post("/api/csv/commit")
    async def csv_commit(request:Request):
        import hashlib,hmac
        body=await request.json(); text=body["text"]
        receipt=hmac.new(token.encode(),text.encode(),hashlib.sha256).hexdigest()
        if not secrets.compare_digest(receipt,body.get("receipt","")):
            raise ValueError("CSV가 변경됐습니다. 미리보기를 다시 확인하세요")
        quotes,errors=parse_csv(text)
        if errors or not quotes:
            raise ValueError("오류가 있는 CSV는 저장할 수 없습니다")
        with Store(db_path) as store:
            store.add_batch(quotes)
        return {"saved":len(quotes)}

    @app.post("/api/jobs")
    async def start_job(request:Request):
        c=conditions_from_dict((await request.json())["conditions"])
        return {"id":jobs.start(c),"note":"저장된 수동 입력만 비교 · 외부 요청 0건 / 비용 0원"}

    @app.get("/api/jobs/{id}")
    def job_status(id:str):
        return jobs.status(id)

    @app.post("/api/jobs/{id}/cancel")
    def cancel_job(id:str):
        jobs.cancel(id)
        return {"requested":True}

    @app.get("/api/jobs/{id}/results")
    def results(id:str,bucket:str="eligible",page:int=1,sort:str="direct_first"):
        return jobs.results(id,bucket,page,sort)

    @app.get("/api/jobs/{id}/daily")
    def daily(id:str):
        return jobs.daily(id)

    app.mount("/static",StaticFiles(directory=STATIC),name="static")
    return app


def main():
    args=server_parser().parse_args()
    if not 1<=args.port<=65535:
        raise SystemExit("포트는 1~65535여야 합니다")
    if args.lan:
        print("주의: LAN 공유가 켜졌습니다. 같은 네트워크 사용자가 데이터를 열람·변경할 수 있습니다. HTTP 암호화 없음. 공용망/포트포워딩 금지.")
    host=args.lan or "127.0.0.1"
    print(f"개인 항공권 비교: http://{host}:{args.port} · 마이리얼트립 참고 조회 지원 · 실시간 비교 미연동")
    import uvicorn
    uvicorn.run(create_app(args.db,lan=args.lan),host=host,port=args.port,proxy_headers=False,access_log=False)


if __name__=="__main__":
    main()

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import estimate, plan, parse_korean, comparisons, lowest_per_date
from .serde import dumps, conditions_from_dict, quote_from_dict, reference_from_dict
from .store import Store


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="유연한 일정 항공권 비교 — 2단계 오프라인 핵심 모듈")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("plan", help="검색 조건 수만 계산. 실제 가격 조회 안 함")
    p.add_argument("conditions")
    p.add_argument("--list", action="store_true", help="모든 조건을 JSONL로 출력")
    p = sub.add_parser("parse", help="자연어 해석 초안. 실행 안 함")
    p.add_argument("text")
    for name in ("init-db", "import-manual", "import-reference", "compare", "references"):
        p = sub.add_parser(name)
        p.add_argument("--db", required=True)
        if name in ("import-manual", "import-reference"):
            p.add_argument("file")
        if name == "compare":
            p.add_argument("conditions")
            p.add_argument("--daily", action="store_true", help="통화별·출발일별 입력값 비교 요약")
            p.add_argument("--sort", choices=("direct_first", "price", "departure", "duration"), default="direct_first")
    args = parser.parse_args()
    if not args.command:
        print(dumps({"stage": 2, "status": "연동되지 않음", "results": [], "ui": "3단계 예정", "network_calls": 0}))
        return
    if args.command == "parse":
        print(dumps(parse_korean(args.text), indent=2))
        return
    if args.command == "plan":
        conditions = conditions_from_dict(read(args.conditions))
        print(dumps(estimate(conditions), indent=2))
        if args.list:
            for request in plan(conditions):
                print(dumps(request))
        return
    with Store(args.db) as store:
        if args.command == "init-db":
            print("빈 저장소 준비 완료. 외부 서비스는 연동되지 않았습니다.")
        elif args.command == "import-manual":
            store.add_manual(quote_from_dict(read(args.file)))
            print("수동 입력 저장 완료. 외부 검증을 수행하지 않았습니다.")
        elif args.command == "import-reference":
            store.add_reference(reference_from_dict(read(args.file)))
            print("참고용 후보 저장 완료. 비교 순위에서 제외됩니다.")
        elif args.command == "references":
            for reference in store.references():
                print(dumps(reference))
        elif args.command == "compare":
            conditions = conditions_from_dict(read(args.conditions))
            count = 0
            # Quotes are read afresh via a SQLite cursor; combinations aren't accumulated.
            results = comparisons(store.quotes(2), store.quotes(1), lambda: store.quotes(1), conditions, datetime.now(timezone.utc))
            if args.daily:
                for (day,currency,kind), result in sorted(lowest_per_date(results,args.sort).items()):
                    print(dumps({"label":"입력값 중 조건에 맞는 비교 요약 · 외부 검증 안 됨", "date":day, "currency":currency, "kind":kind, "result":result}))
                    count += 1
            else:
                # Full results are streamed, not sorted; UI paging/sorting is stage 3.
                for result in results:
                    print(dumps({"label": "수동 입력 비교 · 외부 검증 안 됨", "booking_type": result.booking_type, "result": result}))
                    count += 1
            print(dumps({"matched_input_combinations": count, "external_status": "연동되지 않음", "automatic_results": []}))


if __name__ == "__main__":
    main()

"""CSV is input-only, with an atomic commit after explicit preview."""
import csv
import io
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from .core import Quote,Leg,Segment,Provenance,Passengers

COLUMNS=("입력ID","여정","구간번호","출발공항","도착공항","출발현지시각","도착현지시각","항공사","편명","중간기착",
         "총액","통화","출처","판매처","조회시각","링크","성인","소아","유아","좌석","수하물조건","세금포함","필수수수료포함","추가필수수수료","수하물확인","수하물상세")
SHARED=("총액","통화","출처","판매처","조회시각","링크","성인","소아","유아","좌석","수하물조건","세금포함","필수수수료포함","추가필수수수료","수하물확인","수하물상세")


def template():
    out=io.StringIO()
    csv.writer(out).writerow(COLUMNS)
    return "\ufeff"+out.getvalue()


def tri(value):
    if value not in ("포함","미포함","미확인"):
        raise ValueError("포함 여부는 포함/미포함/미확인 중 하나를 명시해야 합니다")
    return {"포함":True,"미포함":False,"미확인":None}[value]


def parse_csv(text):
    reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if reader.fieldnames is None or set(reader.fieldnames)!=set(COLUMNS) or len(reader.fieldnames)!=len(COLUMNS):
        raise ValueError("CSV 헤더가 맞지 않습니다. 헤더 전용 양식을 사용하세요")
    groups=OrderedDict()
    errors=[]
    for number,row in enumerate(reader,2):
        if None in row or any(v is None for v in row.values()):
            errors.append({"row":number,"message":"열 수가 맞지 않습니다"})
            continue
        row={k:v.strip() for k,v in row.items()}
        if not any(row.values()):
            continue
        if not row["입력ID"]:
            errors.append({"row":number,"message":"입력ID가 필요합니다"})
            continue
        groups.setdefault(row["입력ID"],[]).append((number,row))
    quotes=[]
    for id,rows in groups.items():
        try:
            first=rows[0][1]
            for _,row in rows:
                if any(row[k]!=first[k] for k in SHARED):
                    raise ValueError("같은 입력ID의 총액·출처·승객·확인 항목은 모든 행에서 같아야 합니다")
            legs=[]
            labels=set(row["여정"] for _,row in rows)
            if not labels <= {"편도","가는편","오는편"} or ("편도" in labels and len(labels)>1) or ("편도" not in labels and labels!={"가는편","오는편"}):
                raise ValueError("편도 또는 가는편+오는편을 사용하세요. 왕복은 같은 입력ID로 묶습니다")
            for label in (("편도",) if labels=={"편도"} else ("가는편","오는편")):
                ordered=sorted((row for _,row in rows if row["여정"]==label),key=lambda r:int(r["구간번호"]))
                if [int(r["구간번호"]) for r in ordered]!=list(range(1,len(ordered)+1)):
                    raise ValueError("여정별 구간번호는 중복 없이 1부터 연속해야 합니다")
                segments=[]
                for r in ordered:
                    if r["중간기착"] not in ("0","1","미확인"):
                        raise ValueError("중간기착은 0/1/미확인 중 하나를 명시해야 합니다. 빈 값은 허용되지 않습니다")
                    segments.append(Segment(r["출발공항"],r["도착공항"],datetime.fromisoformat(r["출발현지시각"]),
                        datetime.fromisoformat(r["도착현지시각"]),r["항공사"],r["편명"] or None,
                        None if r["중간기착"]=="미확인" else int(r["중간기착"])))
                legs.append(Leg(tuple(segments)))
            if first["수하물확인"] not in ("확인","미확인"):
                raise ValueError("수하물확인은 확인/미확인을 명시해야 합니다")
            quotes.append(Quote(id,tuple(legs),Decimal(first["총액"]),first["통화"],
                Provenance(first["출처"],first["판매처"],datetime.fromisoformat(first["조회시각"]),first["링크"]),
                Passengers(int(first["성인"]),int(first["소아"]),int(first["유아"])),first["좌석"],first["수하물조건"],
                first["수하물확인"]=="확인",tri(first["세금포함"]),tri(first["필수수수료포함"]),
                Decimal(first["추가필수수수료"]) if first["추가필수수수료"] else None,baggage_details=first["수하물상세"]))
        except (ValueError,TypeError,ArithmeticError,KeyError) as exc:
            errors.append({"row":rows[0][0],"id":id,"message":str(exc)})
    return quotes,errors

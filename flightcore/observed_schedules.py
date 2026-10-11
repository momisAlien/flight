"""Conservative schedule checks on visible cards, never verified fare quotes."""
import re
from datetime import datetime, timedelta, timezone

# Only airports whose local offset and visible Korean name are supported here.
# Unknown airports remain unverified; never assume every airport is UTC+9.
AIRPORTS = {
    'ICN': ('인천국제공항',), 'GMP': ('김포국제공항',),
    'PUS': ('김해국제공항',), 'CJU': ('제주국제공항',),
    'CJJ': ('청주국제공항',),
    'NRT': ('나리타국제공항',), 'HND': ('하네다공항', '도쿄국제공항'),
    'KIX': ('간사이국제공항',), 'FUK': ('후쿠오카공항',),
}
LOCAL = timezone(timedelta(hours=9))


def minutes(text):
    match = re.search(r'(?:(\d+)시간\s*)?(\d+)분', text)
    if match:
        return int(match[1] or 0) * 60 + int(match[2])
    match = re.search(r'(\d+)시간', text)
    return int(match[1]) * 60 if match else None


def leg(origin, destination, departure, arrival, advertised, stop_text):
    elapsed = int((arrival - departure).total_seconds() / 60)
    if elapsed <= 0 or elapsed != advertised:
        raise ValueError('날짜·시각과 표시 소요시간 불일치')
    stops = re.search(r'경유\s*(\d+)', stop_text)
    return {'origin': origin, 'destination': destination,
            'departure': departure.isoformat(), 'arrival': arrival.isoformat(),
            'duration_minutes': elapsed,
            'advertised_stops': int(stops[1]) if stops else (0 if '직항' in stop_text else None),
            'intermediate_stops_verified': False}


def google(text, request):
    stamps = re.findall(r'(\d+)월\s*(\d+)\s*(오전|오후)\s*(\d+):(\d+)에\s*(.*?)에서 출발하여|'
                        r'(\d+)월\s*(\d+)\s*(오전|오후)\s*(\d+):(\d+)에\s*(.*?)에 도착합니다', text)
    if len(stamps) != 2:
        raise ValueError('출발·도착 문구 미확인')
    first, second = stamps[0][:6], stamps[1][6:]
    if not all(first) or not all(second):
        raise ValueError('출발·도착 순서 미확인')
    dates = []
    for stamp, airport in zip((first, second), (request.origin, request.destination)):
        month, day, period, hour, minute, name = stamp
        if airport not in AIRPORTS or name.replace(' ', '') not in AIRPORTS[airport]:
            raise ValueError('공항 이름·시간대 미확인')
        candidates = [request.departure + timedelta(days=i) for i in range(8)]
        found = next((d for d in candidates if (d.month, d.day) == (int(month), int(day))), None)
        if found is None or not 1 <= int(hour) <= 12:
            raise ValueError('날짜 또는 시각 미확인')
        dates.append(datetime(found.year, found.month, found.day,
                              int(hour) % 12 + (12 if period == '오후' else 0), int(minute), tzinfo=LOCAL))
    if dates[0].date() != request.departure:
        raise ValueError('검색 출발일과 표시 날짜 불일치')
    duration = text.split('총 비행 시간은', 1)
    if len(duration) != 2:
        raise ValueError('소요시간 미확인')
    return [leg(request.origin, request.destination, *dates, minutes(duration[1]), text)]


def naver(text, request):
    # An offset must be explicitly adjacent to the arrival. Other formats fail
    # closed instead of guessing the day from the departure/arrival clock.
    pattern = r'(\d{2}:\d{2})([A-Z]{3})\s*\n(\d{2}:\d{2})([A-Z]{3})\s*(?:\+(\d+)일\s*)?\n(직항|경유\s*\d+),\s*([^\n]+)'
    matches = re.findall(pattern, text)
    expected = 2 if request.return_date else 1
    if len(matches) != expected:
        raise ValueError('전체 구간 또는 도착일 표시 미확인')
    routes = [(request.origin, request.destination, request.departure)]
    if request.return_date:
        routes.append((request.return_origin or request.destination,
                       request.return_destination or request.origin, request.return_date))
    result = []
    for (dep, origin, arr, destination, offset, stops, duration), (o, d, day) in zip(matches, routes):
        if (origin, destination) != (o, d) or o not in AIRPORTS or d not in AIRPORTS:
            raise ValueError('공항·시간대 미확인')
        departure = datetime.fromisoformat(f'{day}T{dep}').replace(tzinfo=LOCAL)
        arrival = datetime.fromisoformat(f'{day + timedelta(days=int(offset or 0))}T{arr}').replace(tzinfo=LOCAL)
        result.append(leg(o, d, departure, arrival, minutes(duration), stops))
    return result


def assess(provider, row, request, conditions=None):
    """Retain every observation, including parse failures and excluded schedules."""
    result = {'legs': [], 'status': 'unverified', 'reasons': [], 'unknown': [],
              'comparison_eligible': False}
    try:
        result['legs'] = (google if provider == 'google' else naver)(row['text'], request)
    except (ValueError, TypeError, OverflowError):
        result['unknown'].append('표시 일정·공항·날짜·시간대 미확인')
        return result
    if conditions is None:
        result['status'] = 'schedule_observed'
        return result
    for index, item in enumerate(result['legs']):
        departure = datetime.fromisoformat(item['departure'])
        arrival = datetime.fromisoformat(item['arrival'])
        inbound = request.kind == 'inbound' or index == 1
        window = conditions.inbound_window if inbound else conditions.outbound_window
        if window and not window.contains(departure.timetz()):
            result['reasons'].append('귀국 출발 시간 제외' if inbound else '출국 출발 시간 제외')
        if conditions.max_duration_minutes and item['duration_minutes'] > conditions.max_duration_minutes:
            result['reasons'].append('최대 소요시간 초과')
        stops = item['advertised_stops']
        if stops is None:
            result['unknown'].append('경유 횟수 미확인')
        elif (conditions.direct_only and stops > 0) or stops > conditions.max_stops:
            result['reasons'].append('경유 조건 제외')
        if conditions.direct_only:
            result['unknown'].append('중간 기착 여부 상세 확인 필요')
        if inbound and conditions.return_deadline and arrival.date() > conditions.return_deadline:
            result['reasons'].append('한국 도착 마감 초과')
    if request.return_date:
        if len(result['legs']) == 2:
            nights = (datetime.fromisoformat(result['legs'][1]['departure']).date()
                      - datetime.fromisoformat(result['legs'][0]['arrival']).date()).days
            result['actual_nights'] = nights
            if nights != conditions.nights:
                result['reasons'].append('실제 도착 기준 숙박일수 불일치')
        else:
            result['unknown'].append('귀국편 선택 전: 숙박일수·귀국 마감 미확인')
    else:
        result['unknown'].append('반대편 항공권과 결합 전: 전체 여행 조건 미확인')
    result['reasons'] = list(dict.fromkeys(result['reasons']))
    result['unknown'] = list(dict.fromkeys(result['unknown']))
    result['status'] = 'excluded' if result['reasons'] else 'unverified' if result['unknown'] else 'schedule_matches'
    return result

"""Filter displayed local departure clocks; never infer missing return times."""
import re
from datetime import time


def check(c, provider, req, text):
    windows = ([c.outbound_window, c.inbound_window] if req['kind'] == 'roundtrip'
               else [c.inbound_window if req['kind'] == 'inbound' else c.outbound_window])
    if not any(windows):
        return 'matched'
    clocks = []
    if provider == 'naver':
        matches = re.findall(r'(\d{2}:\d{2})([A-Z]{3})[ \t]*\n(\d{2}:\d{2})([A-Z]{3})', text)
        routes = [(req['origin'], req['destination'])]
        if req['kind'] == 'roundtrip':
            routes.append((req.get('return_origin') or req['destination'], req.get('return_destination') or req['origin']))
        if len(matches) == len(routes):
            for (dep, origin, arr, destination), route in zip(matches, routes):
                try:
                    clocks.append(time.fromisoformat(dep) if (origin, destination) == route else None)
                except ValueError:
                    clocks.append(None)
    elif provider == 'google':
        matches = re.findall(r'(오전|오후)\s*(\d{1,2}):(\d{2})에\s*[^\n]*?에서 출발하여', text)
        # A round-trip search card only identifies the selected outbound flight.
        if len(matches) == 1:
            period, hour, minute = matches[0]
            if 1 <= int(hour) <= 12 and 0 <= int(minute) < 60:
                clocks.append(time(int(hour) % 12 + (12 if period == '오후' else 0), int(minute)))
    unknown = False
    for index, window in enumerate(windows):
        if window is None:
            continue
        clock = clocks[index] if index < len(clocks) else None
        if clock is None:
            unknown = True
        elif not window.contains(clock):
            return 'outside'
    return 'unknown' if unknown else 'matched'

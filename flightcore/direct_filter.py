"""Require displayed non-stop evidence for every leg; never infer a return leg."""
import re


def check(provider, req, text):
    if re.search(r'경유\s*[1-9]|[1-9]\s*회\s*경유|기착|\b[1-9]\s*stops?\b', text, re.I):
        return 'outside'
    if provider == 'naver':
        legs = re.findall(r'\d{2}:\d{2}([A-Z]{3})\s*\n\d{2}:\d{2}([A-Z]{3})\s*(?:\+\d+일\s*)?\n(직항|경유\s*\d+)', text)
        routes = [(req['origin'], req['destination'])]
        if req['kind'] == 'roundtrip':
            routes.append((req.get('return_origin') or req['destination'], req.get('return_destination') or req['origin']))
        if len(legs) == len(routes) and all((o, d) == route and stop == '직항' for (o, d, stop), route in zip(legs, routes)):
            return 'matched'
    elif provider == 'google' and req['kind'] != 'roundtrip':
        # Google roundtrip cards describe only outbound; return is not selected.
        if re.search(r'직항|\bnonstop\b|\bnon-stop\b', text, re.I):
            return 'matched'
    return 'unknown'

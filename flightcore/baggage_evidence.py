"""Normalize only complete, seller-scoped baggage statements; preserve evidence."""
import re


def baggage_evidence(statements):
    result = {}
    for kind, word in (('checked', '위탁'), ('cabin', '기내')):
        evidence = [s.strip() for s in statements if word in s and '수하물' in s]
        facts = []
        unsupported = False
        for line in evidence:
            compact = re.sub(r'\s+', '', line)
            if compact == f'{word}수하물불포함':
                facts.append(('not_included', None, None))
            elif compact in (f'{word}수하물유료', f'{word}수하물유료로이용가능'):
                facts.append(('paid', None, None))
            elif compact == f'무료{word}수하물포함':
                facts.append(('included', None, None))
            else:
                match = re.fullmatch(rf'무료{word}수하물(\d+)개(?:\((\d+(?:\.\d+)?)kg\))?', compact, re.IGNORECASE)
                if match and int(match[1]) > 0 and (match[2] is None or float(match[2]) > 0):
                    facts.append(('included', int(match[1]), match[2]))
                else:
                    unsupported = True
        unique = set(facts)
        state, pieces, weight = next(iter(unique)) if len(unique) == 1 and not unsupported else ('conflicting' if len(unique) > 1 else 'unknown', None, None)
        result[kind] = {'state': state, 'pieces': pieces, 'displayed_weight_kg': weight,
                        'weight_scope': 'unverified', 'evidence': evidence,
                        'allowance_verified': False}
    return result


def enrich_offer(offer):
    return {**offer, 'baggage_evidence': baggage_evidence(offer.get('seller_statements') or [])}

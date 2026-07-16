import re
from dataclasses import dataclass

MODEL_PATTERN = re.compile(
    r"\b(?P<brand>rtx|gtx|rx|arc)?\s*"
    r"(?P<number>10[567]0|16[056]0|20[678]0|30[5689]0|3070|3080|3090|40[6789]0|50[789]0|5[567]00|6[56789]00|7[6789]00|a[357]80|a[357]50|a770|b570|b580)"
    r"(?P<suffix>\s*ti|\s*super|\s*s|\s*xt|\s*gre)?\b",
    re.I,
)

@dataclass(frozen=True)
class ProductModel:
    brand: str
    number: str
    suffix: str = ''

@dataclass(frozen=True)
class MatchResult:
    matched: bool
    confidence: int
    reason: str

def _suffix(value:str)->str:
    value=re.sub(r'\s+','',value.lower())
    return 'super' if value=='s' else value

def parse_models(text:str)->list[ProductModel]:
    found=[]
    for m in MODEL_PATTERN.finditer(text):
        model=ProductModel((m.group('brand') or '').lower(),m.group('number').lower(),_suffix(m.group('suffix') or ''))
        if model not in found: found.append(model)
    compact=re.sub(r'[^a-z0-9]','',text.lower())
    cp=re.compile(r'(?P<brand>rtx|gtx|rx|arc)?(?P<number>10[567]0|16[056]0|20[678]0|30[5689]0|3070|3080|3090|40[6789]0|50[789]0|5[567]00|6[56789]00|7[6789]00|a[357]80|a[357]50|a770|b570|b580)(?P<suffix>ti|super|s|xt|gre)?')
    for m in cp.finditer(compact):
        model=ProductModel((m.group('brand') or '').lower(),m.group('number').lower(),_suffix(m.group('suffix') or ''))
        if model not in found: found.append(model)
    return found

def match_title(title:str, query:str)->MatchResult:
    wanted=parse_models(query)
    if not wanted: return MatchResult(True,70,'General search')
    available=parse_models(title)
    if not available: return MatchResult(False,0,'No model in title')
    q=wanted[0]
    for f in available:
        if f.number!=q.number: continue
        if q.brand and f.brand and q.brand!=f.brand: continue
        if q.suffix and f.suffix!=q.suffix: continue
        if q.suffix: return MatchResult(True,100,'Exact model and variant')
        return MatchResult(True,94 if f.suffix else 100,'Matching GPU family')
    return MatchResult(False,0,'Different GPU model')

def product_key(query:str)->str:
    models=parse_models(query)
    if not models: return query.lower().strip()
    m=models[0]
    return f'{m.brand}:{m.number}:{m.suffix}'



def product_key_from_query(
    query: str,
) -> str:
    """Return the normalized product key expected by AI/history modules."""
    return product_key(query)

"""Desktop reference for the unchanged forest plus transparent missing-input fallback."""
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).parent
MODEL = json.loads((ROOT / 'soil_rf_desktop.json').read_text())
META = json.loads((ROOT / 'fallback_metadata.json').read_text())
NAMES = ['moisture','temperature','pH','N','P','K','EC','backup_temperature','backup_moisture']
LIMITS = [(0,100),(-10,60),(3.5,9.5),(0,200),(0,200),(0,250),(0,5),(-10,60),(0,100)]

def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]

def predict(raw):
    if len(raw) not in (7, 9):
        raise ValueError('Expected seven primary values, optionally followed by two backups')
    count = len(raw)
    raw = [f32(float(v)) for v in raw] + [math.nan] * (9-count)
    issues = [1 if not math.isfinite(v) else 0 if lo <= v <= hi else 2 for v, (lo, hi) in zip(raw,LIMITS)]
    features = []
    sources = []
    disagreements = []
    for a,b,tolerance in [(0,8,15),(1,7,5)]:
        if not issues[a] and not issues[b]:
            disagreement = abs(f32(raw[a]-raw[b])) > tolerance
            value = math.nan if disagreement else f32(f32(raw[a]+raw[b])/2)
            if disagreement: disagreements.append(NAMES[a])
            source = 'training_median' if disagreement else 'fused'
        elif not issues[a] or not issues[b]:
            value = raw[a] if not issues[a] else raw[b]
            source = 'primary' if not issues[a] else 'backup'
        else:
            value, source = math.nan, 'training_median'
        features.append(value)
        sources.append(source)
    features += [raw[i] if not issues[i] else math.nan for i in range(2,7)]
    measured = sum(math.isfinite(v) for v in features)
    substitutions = []
    for i,value in enumerate(features):
        if not math.isfinite(value):
            features[i] = META['medians'][i]
            substitutions.append({'feature':NAMES[i], 'method':'training_median', 'value':features[i]})
    votes = [0] * len(MODEL['classes'])
    for tree in MODEL['trees']:
        index = 0
        while tree[index]['feature'] >= 0:
            node = tree[index]
            index = node['left'] if features[node['feature']] <= f32(node['threshold']) else node['right']
        votes[tree[index]['value']] += 1
    crop = MODEL['classes'][max(range(len(votes)),key=votes.__getitem__)]
    return {'prototype':True, 'status':'default_data_only' if measured==0 else 'provisional' if measured<7 else 'complete_inputs',
            'crop':crop, 'measured_features':measured, 'required_features':7,
            'issues':[{'input':NAMES[i], 'reason':'missing_or_nonfinite_or_marked_failed' if issues[i]==1 else 'outside_prototype_range'} for i in range(count) if issues[i]]
                     + ([{'disagreement':disagreements}] if disagreements else []),
            'substitutions':substitutions, 'moisture_source':sources[0], 'temperature_source':sources[1], 'field_validated':False}

if __name__ == '__main__':
    import sys
    print(json.dumps(predict(sys.argv[1].split(',')), indent=2, allow_nan=False))

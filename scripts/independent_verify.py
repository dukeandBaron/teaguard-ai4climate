"""Recompute labels and metrics from CSV without importing the model implementation."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
with (ROOT/'data/weather_daily.csv').open(encoding='utf-8',newline='') as f:
    rows=list(csv.DictReader(f))
bydate={r['date']:i for i,r in enumerate(rows)}
pred=json.loads((ROOT/'artifacts/test_predictions.json').read_text(encoding='utf-8'))
report=json.loads((ROOT/'artifacts/evaluation.json').read_text(encoding='utf-8'))
checks=0
for p in pred:
    i=bydate[p['origin']]
    actual_heat=max(float(rows[k]['temperature_2m_max']) for k in range(i+1,i+4))
    actual_water=sum(float(rows[k]['et0_fao_evapotranspiration'])-float(rows[k]['precipitation_sum']) for k in range(i+1,i+8))
    assert abs(actual_heat-p['heat_3d_actual'])<1e-10
    assert abs(actual_water-p['balance_7d_actual'])<1e-10
    assert p['origin']>='2025-01-01' and p['label_end']<='2025-12-31'
    checks+=3
for name in ['heat_3d','balance_7d']:
    for method in ['selected','persistence','seasonal']:
        errors=[p[f'{name}_{method}']-p[f'{name}_actual'] for p in pred]
        mae=sum(abs(e) for e in errors)/len(errors)
        rmse=math.sqrt(sum(e*e for e in errors)/len(errors))
        stored=report['test_metrics'][name][method]
        assert abs(mae-stored['mae'])<1e-10
        assert abs(rmse-stored['rmse'])<1e-10
        checks+=2
assert hashlib.sha256((ROOT/'data/weather_daily.csv').read_bytes()).hexdigest()==report['weather_csv_sha256']
checks+=1
receipt={'status':'PASS_INDEPENDENT_LOCAL_METRIC_AND_LABEL_RECOMPUTATION','test_windows':len(pred),'assertions':checks,'weather_csv_sha256':report['weather_csv_sha256'],'scope':'public reanalysis retrospective only; not an official score or agronomic outcome'}
(ROOT/'artifacts/independent_verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False,indent=2))

"""Small UTF8 copy refinement; preserve exact English scientific source values."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "web/app.js"
text = path.read_text(encoding="utf-8")
old = ".map(([k,v])=>`${k}=${v}`)"
new = ".map(([k,v])=>`${({crop:'物种/品种',setting:'环境/处理',measured_endpoint:'测量终点',treatment_note:'方法边界'}[k]||k)}：${v??'无特定终点'}`)"
if old in text:
    assert text.count(old) == 1
    path.write_text(text.replace(old, new), encoding="utf-8")
style = ROOT / "web/style.css"
css = style.read_text(encoding="utf-8")
needle = '.graph-node text{font-family:"Microsoft YaHei",sans-serif;font-size:12px;'
if needle in css:
    style.write_text(
        css.replace(
            needle,
            '.graph-node text{font-family:"Microsoft YaHei",sans-serif;font-size:13px;',
        ),
        encoding="utf-8",
    )
print("Chinese condition labels refined; source terminology retained")

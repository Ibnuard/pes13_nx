"""Copy only the existing PES install code/version, without printing their data."""
from pathlib import Path
import json
import winreg

port = Path(__file__).resolve().parents[1]
source_key = r'SOFTWARE\WOW6432Node\KONAMI\PES2013'
values = {}
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, source_key, 0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
    for name in ('code', 'version'):
        value, kind = winreg.QueryValueEx(key, name)
        if kind != winreg.REG_SZ or not value or '\0' in value:
            raise ValueError(f'Expected non-empty REG_SZ for {name}')
        values[name] = value

def quote(value):
    # Wine REGISTRY Version 2 text uses C escapes; this path only needs strings.
    return ''.join('\\\\' if c == '\\' else '\\"' if c == '"' else
                   f'\\x{ord(c):04x}' if ord(c) < 32 or ord(c) > 126 else c
                   for c in value)

text = 'WINE REGISTRY Version 2\n\n[Software\\\\KONAMI\\\\PES2013]\n'
text += ''.join(f'"{name}"="{quote(value)}"\n' for name, value in values.items())
dest = port / 'local/config/pes13-install.reg'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(text, encoding='ascii', newline='\n')
report = {'source': 'HKLM\\' + source_key,
          'destination': str(dest.relative_to(port)),
          'values': {name: {'type': 'REG_SZ', 'characters': len(value)} for name, value in values.items()},
          'contents_not_printed': True,
          'installdir': 'Handled by runtime as C:\\PES13\\, not copied from PC'}
(port / 'local/config/metadata-export.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))

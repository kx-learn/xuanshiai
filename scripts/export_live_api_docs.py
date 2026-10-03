"""Export the implemented trial OpenAPI subset and schema field tables."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


def main():
    spec = app.openapi()
    paths = {name: value for name, value in spec['paths'].items() if '/live/v2/' in name
             or name == '/api/v1/discovery/applications/{target_id}'}
    schemas = {}

    def collect(value):
        if isinstance(value, dict):
            ref = value.get('$ref', '')
            if ref.startswith('#/components/schemas/'):
                name = ref.rsplit('/', 1)[1]
                if name not in schemas:
                    schemas[name] = spec['components']['schemas'][name]
                    collect(schemas[name])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(paths)
    out = Path(__file__).resolve().parents[1] / 'docs' / 'api'
    document = {'openapi': spec['openapi'], 'info': {'title':'宣誓爱直播 v2 试点接口','version':'2026-10-02'},
        'paths': paths, 'components': {'schemas': schemas, 'securitySchemes': spec['components'].get('securitySchemes', {})}}
    (out / 'live-v2.openapi.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines = ['# 直播 v2 试点接口字段字典', '', '由实际 Pydantic/OpenAPI 生成；业务条件、权限和示例见 [live-v2.md](live-v2.md)。', '']
    for name, schema in schemas.items():
        lines += ['## '+name, '', '| 字段 | 必填/必返 | 类型、范围、默认值与含义 |', '| --- | --- | --- |']
        for field, definition in schema.get('properties', {}).items():
            details = json.dumps({key:value for key,value in definition.items() if key != 'title'},ensure_ascii=False)
            lines.append(f'| {field} | {"是" if field in schema.get("required",[]) else "否"} | `{details.replace("|", " / ")}` |')
        lines += ['']
    (out / 'live-v2-fields.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Exported {len(paths)} paths and {len(schemas)} request/response models')


if __name__ == '__main__':
    main()

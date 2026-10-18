"""Positional standard templates: validation, conversion and recipient resolution.

Deliberately excludes authentication, location, carousel, flows and commerce.
Only immutable provider-approved snapshots are used to build outgoing templates.
"""
import copy
import re
from urllib.parse import urlparse
from fastapi import HTTPException

TOKEN = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*|[1-9]\d*)\s*\}\}")
FIELDS = {'name', 'phone', 'email', 'city', 'lifecycle.segment', 'lifecycle.totalSpent', 'demographics.city'}


def invalid(message):
    raise HTTPException(422, message)


def mapped_text(text, scope, mappings, examples, *, limit, max_variables=None):
    if not isinstance(text, str) or not text.strip() or len(text) > limit:
        invalid(f'{scope}: enter 1 to {limit} characters')
    keys = list(dict.fromkeys(TOKEN.findall(text)))
    remainder = TOKEN.sub('', text)
    if '{{' in remainder or '}}' in remainder:
        invalid(f'{scope}: malformed variable')
    if max_variables is not None and len(keys) > max_variables:
        invalid(f'{scope}: at most {max_variables} variable(s) supported')
    if keys and any(k.isdigit() for k in keys) and keys != [str(i + 1) for i in range(len(keys))]:
        invalid(f'{scope}: positional variables must be sequential from 1')
    specs = []
    for key in keys:
        field = (mappings.get(scope) or {}).get(key)
        if not isinstance(field, str):
            invalid(f'{scope}.{key}: choose a recipient field')
        normalized = field.removeprefix('customer.')
        if normalized not in FIELDS:
            invalid(f'{scope}.{key}: unsupported recipient field {field}')
        sample = (examples.get(scope) or {}).get(key)
        if sample is None or not str(sample).strip() or '{{' in str(sample):
            invalid(f'{scope}.{key}: provide a submission example')
        specs.append({'key': key, 'field': normalized, 'example': str(sample)})
    converted = TOKEN.sub(lambda m: '{{' + str(keys.index(m.group(1)) + 1) + '}}', text)
    return converted, specs


def compile_draft(name, category, content):
    if not isinstance(content, dict):
        invalid('Template content must be an object')
    for key in ('mappings', 'examples', 'header'):
        if content.get(key) is not None and not isinstance(content[key], dict):
            invalid(f'{key} must be an object')
    for key in ('mappings', 'examples'):
        if any(not isinstance(v, dict) for v in (content.get(key) or {}).values()):
            invalid(f'{key} must contain component-specific objects')
    if not re.fullmatch(r'[a-z0-9_]{1,512}', name or ''):
        invalid('Meta name must contain only lowercase letters, numbers and underscores')
    category = str(category).upper()
    if category not in {'MARKETING', 'UTILITY'}:
        invalid('Only standard MARKETING and UTILITY templates are supported')
    language = content.get('language')
    if not isinstance(language, str) or not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?', language):
        invalid('Choose a valid Meta language code, such as en_US')
    mappings, examples = content.get('mappings') or {}, content.get('examples') or {}
    components, parameters = [], {}
    header = content.get('header') or {}
    kind = str(header.get('type') or 'NONE').upper()
    if kind == 'TEXT':
        text, specs = mapped_text(header.get('text'), 'header', mappings, examples, limit=60, max_variables=1)
        part = {'type': 'HEADER', 'format': 'TEXT', 'text': text}
        if specs:
            part['example'] = {'header_text': [s['example'] for s in specs]}
        components.append(part)
        parameters['header'] = specs
    elif kind in {'IMAGE', 'VIDEO', 'DOCUMENT'}:
        if not header.get('asset_id'):
            invalid('Upload a sample header asset before submission')
        components.append({'type': 'HEADER', 'format': kind})
    elif kind != 'NONE':
        invalid('Unsupported header format')
    body, specs = mapped_text(content.get('body'), 'body', mappings, examples, limit=1024)
    if specs and (body.startswith('{{') or body.endswith('}}') or re.search(r'\}\}\s*\{\{', body)):
        invalid('Body variables need surrounding text and must not be adjacent')
    part = {'type': 'BODY', 'text': body}
    if specs:
        part['example'] = {'body_text': [[s['example'] for s in specs]]}
    components.append(part)
    parameters['body'] = specs
    footer = content.get('footer')
    if footer:
        if not isinstance(footer, str) or len(footer) > 60 or '{{' in footer:
            invalid('Footer supports up to 60 characters without variables')
        components.append({'type': 'FOOTER', 'text': footer})
    buttons = content.get('buttons') or []
    if not isinstance(buttons, list) or len(buttons) > 10:
        invalid('Use at most ten buttons')
    converted_buttons, types, labels = [], [], set()
    for i, button in enumerate(buttons):
        if not isinstance(button, dict):
            invalid('Each button must be an object')
        kind_b = str(button.get('type') or '').upper()
        label = button.get('text') or ''
        if not isinstance(label, str) or not label.strip() or len(label) > 25 or label.casefold() in labels:
            invalid('Button labels must be unique and contain 1 to 25 characters')
        labels.add(label.casefold())
        types.append(kind_b)
        result = {'type': kind_b, 'text': label}
        if kind_b == 'URL':
            scope = f'button_{i}'
            url, specs = mapped_text(button.get('url'), scope, mappings, examples, limit=2000, max_variables=1)
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or '{{' in parsed.netloc:
                invalid('Website buttons require an HTTPS URL with a fixed hostname')
            if specs and not url.endswith('{{1}}'):
                invalid('Dynamic URL variable must be at the end of the URL')
            result['url'] = url
            if specs:
                result['example'] = [url.replace('{{1}}', specs[0]['example'])]
            parameters[scope] = specs
        elif kind_b == 'PHONE_NUMBER':
            phone = button.get('phone_number') or ''
            if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
                invalid('Call Now requires an international phone number beginning with +')
            result['phone_number'] = phone
        elif kind_b != 'QUICK_REPLY':
            invalid('Supported buttons: URL, PHONE_NUMBER and QUICK_REPLY')
        converted_buttons.append(result)
    if types.count('URL') > 2 or types.count('PHONE_NUMBER') > 1 or sum(t != 'QUICK_REPLY' for t in types) > 3:
        invalid('Use at most two website buttons and one Call Now button')
    groups = [t == 'QUICK_REPLY' for t in types]
    if sum(a != b for a, b in zip(groups, groups[1:])) > 1:
        invalid('Group quick replies together before or after call-to-action buttons')
    if converted_buttons:
        components.append({'type': 'BUTTONS', 'buttons': converted_buttons})
    return {'name': name, 'language': language, 'category': category, 'components': components,
            'parameters': parameters, 'header_type': str(header.get('type') or 'NONE').upper(),
            'sample_asset_id': header.get('asset_id')}


def provider_definition(item, previous=None):
    """Preserve mappings only when the provider component definition still matches."""
    components = copy.deepcopy(item.get('components') or [])
    def signature(parts):
        if isinstance(parts, list):
            return [signature(p) for p in parts]
        if isinstance(parts, dict):
            return {k: signature(v) for k, v in parts.items() if k != 'example'}
        return parts
    same = previous and signature(previous.get('components', [])) == signature(components)
    header = next((p for p in components if p.get('type') == 'HEADER'), {})
    return {'name': item['name'], 'language': item['language'], 'category': item['category'],
            'components': components, 'parameters': copy.deepcopy(previous.get('parameters', {})) if same else {},
            'header_type': header.get('format', 'NONE'), 'meta_id': str(item['id'])}


def resolve_value(spec, recipient):
    value = recipient
    if spec['field'] == 'city':
        value = recipient.get('city') or (recipient.get('demographics') or {}).get('city')
        if value is None or not str(value).strip() or '{{' in str(value):
            invalid('Recipient is missing city')
        return str(value)
    for key in spec['field'].split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    if value is None or not str(value).strip() or '{{' in str(value):
        invalid(f"Recipient is missing {spec['field']}")
    return str(value)


def outgoing(definition, recipient, media_id=None, mappings=None):
    if mappings is not None and not isinstance(mappings, dict):
        invalid('Send-time mappings must be an object of component-specific field lists')
    parts = definition.get('components') or []
    if not any(p.get('type') == 'BODY' for p in parts):
        invalid('The approved template has no body definition; synchronize it before sending')
    if any(p.get('type') not in {'HEADER', 'BODY', 'FOOTER', 'BUTTONS'} for p in parts):
        invalid('This specialized template format is unsupported')
    if definition.get('category') not in {'MARKETING', 'UTILITY'}:
        invalid('This template category is unsupported')
    params = copy.deepcopy(definition.get('parameters') or {})
    # External templates can receive explicit mappings, never provider components.
    for scope, fields in (mappings or {}).items():
        if not isinstance(fields, list) or any(not isinstance(f, str) or f.removeprefix('customer.') not in FIELDS for f in fields):
            invalid('Unsupported send-time recipient mapping')
        params[scope] = [{'field': f.removeprefix('customer.')} for f in fields]
    result = {'name': definition['name'], 'language': {'code': definition['language']}, 'components': []}
    for part in parts:
        kind = part.get('type')
        if kind == 'HEADER' and part.get('format') in {'IMAGE', 'VIDEO', 'DOCUMENT'}:
            if not media_id:
                invalid('Select a send-time header asset; approval samples cannot be sent')
            media_type = part['format'].lower()
            result['components'].append({'type': 'header', 'parameters': [{'type': media_type, media_type: {'id': media_id}}]})
        elif kind == 'HEADER' and part.get('format') != 'TEXT':
            invalid('Unsupported header format')
        elif kind in {'HEADER', 'BODY'}:
            scope = kind.lower()
            keys = set(TOKEN.findall(part.get('text') or ''))
            if keys and keys != {str(i + 1) for i in range(len(keys))}:
                invalid('Only standard positional Meta templates are supported; named provider parameters are unsupported')
            specs = params.get(scope) or []
            if len(specs) != len(keys):
                invalid(f'{scope}: supply all required recipient mappings')
            if specs:
                result['components'].append({'type': scope, 'parameters': [{'type': 'text', 'text': resolve_value(s, recipient)} for s in specs]})
        elif kind == 'BUTTONS':
            for i, button in enumerate(part.get('buttons') or []):
                if button.get('type') not in {'URL', 'PHONE_NUMBER', 'QUICK_REPLY'}:
                    invalid('Unsupported template button')
                if button.get('type') == 'URL' and TOKEN.search(button.get('url') or ''):
                    specs = params.get(f'button_{i}') or []
                    if len(specs) != 1:
                        invalid(f'button_{i}: supply its dynamic URL mapping')
                    result['components'].append({'type': 'button', 'sub_type': 'url', 'index': str(i),
                                                 'parameters': [{'type': 'text', 'text': resolve_value(specs[0], recipient)}]})
    return result


def rendered_body(definition, payload):
    """Retain the approved personalized text in queue/delivery audit views."""
    text = next((p.get('text', '') for p in definition['components'] if p.get('type') == 'BODY'), '')
    parameters = next((p.get('parameters', []) for p in payload.get('components', []) if p.get('type') == 'body'), [])
    return TOKEN.sub(lambda match: parameters[int(match.group(1)) - 1]['text'], text)

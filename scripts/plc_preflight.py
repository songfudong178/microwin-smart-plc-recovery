#!/usr/bin/env python3
"""Read-only manifest preflight, not a MicroWIN compiler or native acceptance."""
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
LIMIT = 32 * 1024 * 1024
HASH = re.compile(r'[0-9a-fA-F]{64}$')
POU = re.compile(r'(?:OB1|SBR\d+|INT\d+)$')
ADDRESS = re.compile(r'(SM|AI|AQ|[IQMVLS])(?:(B|W|D)(\d+)|(\d+)\.([0-7]))$', re.I)
TYPE_BITS = {'BOOL': 1, 'BYTE': 8, 'WORD': 16, 'INT': 16,
             'DWORD': 32, 'DINT': 32, 'REAL': 32}
RESERVED = {'BEGIN', 'END', 'NETWORK', 'TITLE', 'VAR', 'END_VAR', 'TRUE', 'FALSE',
            'ORGANIZATION_BLOCK', 'SUBROUTINE_BLOCK', 'INTERRUPT_BLOCK'}
UNCOVERED = [
    'Complete Siemens grammar, opcode legality and full operand/type semantics',
    'Real library CALL signatures, library memory layout and asynchronous behavior',
    'Indirect access/write ownership and completeness of declared allocation inventory',
    'Actual CPU/firmware compatibility, compiled memory capacity and physical I/O layout',
    'Native import/compile, all-Network LAD rendering, protected library internals',
    'Native round-trip executable comparison and save/reopen consistency',
    'Scan behavior, retention implementation, process safety and authorized field testing',
    'Dynamic timer/counter/edge lifecycle, cross-scan scheduling and resource reuse',
    'Truth or completeness of evidence content; hashes only bind declared artifacts',
]


class ManifestError(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def context_hash(manifest):
    """Evidence itself is excluded to avoid recursive hashes; all else is bound."""
    payload = {key: value for key, value in manifest.items() if key != 'evidence'}
    return sha(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':')).encode('utf-8'))


def object_exact(value, fields, where):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ManifestError(f'{where}: required keys exactly {sorted(fields)}')


def string(value, where):
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f'{where}: expected nonempty string')


def array(value, where):
    if not isinstance(value, list):
        raise ManifestError(f'{where}: expected array')


def unique_strings(value, where):
    array(value, where)
    for item in value:
        string(item, where)
    if len(value) != len(set(value)):
        raise ManifestError(f'{where}: duplicate entries')


def validate_manifest(m):
    required = {'schema_version', 'target', 'import', 'inputs', 'allocations',
                'aliases', 'migrations', 'evidence', 'required_evidence'}
    if not isinstance(m, dict) or not required <= set(m) or set(m) - required - {'inventory'}:
        raise ManifestError(f'manifest: required keys {sorted(required)}; only optional key is inventory')
    if 'inventory' in m:
        object_exact(m['inventory'], {'symbol_tables_complete', 'basis'}, 'inventory')
        if type(m['inventory']['symbol_tables_complete']) is not bool:
            raise ManifestError('inventory.symbol_tables_complete must be a boolean')
        string(m['inventory']['basis'], 'inventory.basis')
    if type(m['schema_version']) is not int or m['schema_version'] != 1:
        raise ManifestError('schema_version must be integer 1')
    target_keys = {'vendor', 'family', 'cpu', 'firmware', 'software', 'software_version'}
    object_exact(m['target'], target_keys, 'target')
    for key, value in m['target'].items():
        string(value, f'target.{key}')
    if m['target']['vendor'] != 'Siemens' or m['target']['family'] != 'S7-200 SMART':
        raise ManifestError('Only the Siemens S7-200 SMART manifest profile is supported')
    object_exact(m['import'], {'scope', 'allowed_pous', 'protected_pous'}, 'import')
    if m['import']['scope'] not in ('partial', 'full'):
        raise ManifestError('import.scope must be partial or full')
    for key in ('allowed_pous', 'protected_pous'):
        unique_strings(m['import'][key], f'import.{key}')
        if any(not POU.fullmatch(item) for item in m['import'][key]):
            raise ManifestError(f'import.{key}: only OB1/SBRn/INTn identifiers allowed')
    if not m['import']['allowed_pous']:
        raise ManifestError('import.allowed_pous cannot be empty')
    for key in ('inputs', 'allocations', 'aliases', 'migrations', 'evidence'):
        array(m[key], key)
    for item in m['inputs']:
        object_exact(item, {'id', 'path', 'kind', 'encoding', 'profile'}, 'input')
        for key in item:
            string(item[key], f'input.{key}')
        if item['kind'] not in ('awl', 'db', 'symbols_tsv', 'opaque'):
            raise ManifestError(f"Unknown input kind: {item['kind']}")
        expected = {'awl': ('gbk', 'microwin_awl'), 'db': (None, 'simple_numeric_db'),
                    'symbols_tsv': ('utf-8', 'clipboard_local_v1'),
                    'opaque': ('binary', 'hash_only')}[item['kind']]
        if item['profile'] != expected[1] or (expected[0] and item['encoding'] != expected[0]):
            raise ManifestError(f"Unsupported input encoding/profile: {item['id']}")
        if item['kind'] == 'db' and item['encoding'] not in ('gbk', 'utf-8'):
            raise ManifestError('DB encoding must be gbk or utf-8')
    if not any(item['kind'] == 'awl' for item in m['inputs']):
        raise ManifestError('At least one AWL input is required')
    for item in m['allocations']:
        object_exact(item, {'id', 'address', 'type', 'owner', 'count'}, 'allocation')
        for key in ('id', 'address', 'type', 'owner'):
            string(item[key], f'allocation.{key}')
        if type(item['count']) is not int or not 1 <= item['count'] <= 65536:
            raise ManifestError('allocation.count must be integer 1..65536')
    if not m['allocations']:
        raise ManifestError('Explicit allocations cannot be empty')
    for item in m['aliases']:
        object_exact(item, {'left', 'right', 'reason'}, 'alias')
        for key in item:
            string(item[key], f'alias.{key}')
    for item in m['migrations']:
        object_exact(item, {'old_name', 'new_name', 'address', 'type'}, 'migration')
        for key in ('old_name', 'address', 'type'):
            string(item[key], f'migration.{key}')
        if item['new_name'] is not None:
            string(item['new_name'], 'migration.new_name')
    for item in m['evidence']:
        object_exact(item, {'id', 'file', 'sha256', 'context_sha256', 'input_sha256'}, 'evidence')
        for key in ('id', 'file'):
            string(item[key], f'evidence.{key}')
        for key in ('sha256', 'context_sha256'):
            if not isinstance(item[key], str) or not HASH.fullmatch(item[key]):
                raise ManifestError(f'evidence.{key}: expected SHA-256 hex string')
        if not isinstance(item['input_sha256'], dict):
            raise ManifestError('evidence.input_sha256 must be an object')
        for key, value in item['input_sha256'].items():
            string(key, 'evidence input id')
            if not isinstance(value, str) or not HASH.fullmatch(value):
                raise ManifestError('evidence.input_sha256 values must be SHA-256 strings')
    unique_strings(m['required_evidence'], 'required_evidence')
    for key in ('inputs', 'allocations', 'evidence'):
        ids = [item['id'] for item in m[key]]
        if len(ids) != len(set(ids)):
            raise ManifestError(f'{key}: duplicate id')


def strip_comments(line, hide_strings=False):
    """Only // line comments; quote-aware. Not a general AWL/DB lexer."""
    result, quote = [], None
    i = 0
    while i < len(line):
        char = line[i]
        if quote:
            result.append(' ' if hide_strings else char)
            if char == quote:
                if i + 1 < len(line) and line[i + 1] == quote:
                    result.append(' ' if hide_strings else quote)
                    i += 1
                else:
                    quote = None
        elif line[i:i + 2] == '//':
            break
        elif char in ('"', "'"):
            quote = char
            result.append(' ' if hide_strings else char)
        else:
            result.append(char)
        i += 1
    return ''.join(result).strip()


def address_span(address, count=1):
    match = ADDRESS.fullmatch(address)
    if not match:
        raise ValueError(f'Address outside supported direct bit/byte profile: {address}')
    area, width, byte, bit_byte, bit = match.groups()
    area = area.upper()
    size = {'B': 8, 'W': 16, 'D': 32}.get((width or '').upper(), 1)
    start = int(byte if byte is not None else bit_byte) * 8 + int(bit or 0)
    return area, start, start + size * count, size


def overlap(a, b):
    return a[0] == b[0] and max(a[1], b[1]) < min(a[2], b[2])


class Preflight:
    def __init__(self, path):
        raw_path = str(path)
        self.path_error = raw_path.startswith(('\\', '//')) or '://' in raw_path
        self.path = Path(path) if self.path_error else Path(path).resolve()
        self.report = {'tool': 'plc_preflight', 'schema_version': 1,
                       'recorded_utc': datetime.now(timezone.utc).isoformat(),
                       'successful': False, 'native_acceptance': False,
                       'errors': [], 'review_required': [], 'checks': [],
                       'hashes': {'tool': sha(Path(__file__).read_bytes()), 'inputs': {}, 'evidence': {}},
                       'not_covered': UNCOVERED}
        self.allocations, self.texts, self.files, self.symbols = {}, {}, {}, {}

    def issue(self, code, where, message, review=False):
        self.report['review_required' if review else 'errors'].append(
            {'code': code, 'location': where, 'message': message})

    def check(self, name, **details):
        self.report['checks'].append({'name': name, **details})

    def local_file(self, name, where):
        if name.startswith(('\\\\', '//')) or '://' in name or '\\' == name[:1]:
            raise ValueError('Network/device paths are not allowed')
        path = Path(name)
        if not path.is_absolute():
            path = self.path.parent / path
        path = path.resolve()
        if str(path).startswith(('\\\\', '//')):
            raise ValueError('Resolved network path is not allowed')
        if not path.is_file():
            raise ValueError('File does not exist or is not a regular file')
        if path.stat().st_size > LIMIT:
            raise ValueError(f'File exceeds {LIMIT} byte read limit')
        data = path.read_bytes()
        if not data:
            raise ValueError('Empty file is not evidence/input')
        first_hash = self.files.setdefault(str(path), sha(data))
        if first_hash != sha(data):
            self.issue('file.changed_between_reads', where, 'Same file changed after its first read; first hash is retained')
        return path, data

    def load(self):
        if self.path_error or str(self.path).startswith(('\\\\', '//')):
            raise ManifestError('Manifest must be a local file')
        if not self.path.is_file() or self.path.stat().st_size > LIMIT:
            raise ManifestError('Manifest missing/not regular, or exceeds read limit')
        raw = self.path.read_bytes()
        self.report['hashes']['manifest'] = sha(raw)
        self.files[str(self.path)] = sha(raw)
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ManifestError(f'Duplicate JSON key: {key}')
                result[key] = value
            return result
        self.m = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ManifestError(f'Non-JSON number: {value}')))
        validate_manifest(self.m)
        self.report['hashes']['context_sha256'] = context_hash(self.m)
        self.check('manifest_schema_and_explicit_target', target=self.m['target'], import_scope=self.m['import'])
        inventory = self.m.get('inventory')
        if not inventory or not inventory['symbol_tables_complete']:
            self.issue('inventory.unconfirmed', 'inventory', 'All user/I/O/system/library symbol-table inputs have not been confirmed complete', True)
        self.check('symbol_inventory_declaration', declaration=inventory,
                   limitation='Self-reported completeness only; the tool cannot discover omitted native tables')
        for key, value in self.m['target'].items():
            if value.casefold() in ('unknown', 'unverified', '待核', '未知', '未核实'):
                self.issue('target.unverified', f'target.{key}', 'Explicit identity still requires verification', True)

    def load_inputs(self):
        paths = set()
        for item in self.m['inputs']:
            ident = item['id']
            try:
                path, raw = self.local_file(item['path'], ident)
            except (ValueError, OSError) as error:
                self.issue('input.file', ident, str(error))
                continue
            if str(path).casefold() in paths:
                self.issue('input.duplicate_file', ident, 'Same file declared under multiple ids')
            paths.add(str(path).casefold())
            self.report['hashes']['inputs'][ident] = {'path': str(path), 'sha256': sha(raw), 'bytes': len(raw)}
            if item['kind'] == 'opaque':
                self.issue('input.hash_only', ident, 'Opaque artifact content is not checked', True)
                continue
            if raw.startswith((b'\xef\xbb\xbf', b'\xff\xfe', b'\xfe\xff')):
                self.issue('encoding.bom', ident, 'This declared text profile forbids BOM')
            if b'\n' in raw.replace(b'\r\n', b'') or b'\r' in raw.replace(b'\r\n', b''):
                self.issue('encoding.crlf', ident, 'This declared text profile requires CRLF')
            try:
                text = raw.decode(item['encoding'], errors='strict')
                if text.encode(item['encoding']) != raw:
                    self.issue('encoding.roundtrip', ident, 'Encoding does not round-trip exactly')
            except UnicodeError as error:
                self.issue('encoding.decode', ident, str(error))
                continue
            self.texts[ident] = text
            self.check('text_profile', input=ident, encoding=item['encoding'], profile=item['profile'])

    def allocation_checks(self):
        for item in self.m['allocations']:
            try:
                span = address_span(item['address'], item['count'])
            except ValueError as error:
                self.issue('allocation.address_review', item['id'], str(error), True)
                continue
            if item['type'] not in TYPE_BITS:
                self.issue('allocation.type_review', item['id'], 'Unsupported declared data type', True)
                continue
            if TYPE_BITS[item['type']] != span[3]:
                self.issue('allocation.width', item['id'], 'Address width and declared type differ')
            self.allocations[item['id']] = (item, span)
        ids = {item['id'] for item in self.m['allocations']}
        aliases = set()
        for item in self.m['aliases']:
            pair = frozenset((item['left'], item['right']))
            if len(pair) != 2 or not pair <= ids or pair in aliases:
                self.issue('alias.invalid', item['left'], 'Alias needs two distinct known ids, once only')
                continue
            aliases.add(pair)
            if all(key in self.allocations for key in pair):
                if not overlap(*(self.allocations[key][1] for key in pair)):
                    self.issue('alias.nonoverlap', item['left'], 'Declared alias does not overlap')
            self.check('explicit_alias', **item)
        entries = list(self.allocations.items())
        for index, (left, (_a, span_a)) in enumerate(entries):
            for right, (_b, span_b) in entries[index + 1:]:
                if overlap(span_a, span_b) and frozenset((left, right)) not in aliases:
                    self.issue('allocation.overlap', f'{left}/{right}', 'Bit ranges overlap without a justified explicit alias')
        self.check('allocation_bit_ranges', parsed=len(entries), declared=len(self.m['allocations']))

    def symbol_checks(self):
        addresses, spans = {}, []
        for item in self.m['inputs']:
            if item['kind'] != 'symbols_tsv' or item['id'] not in self.texts:
                continue
            ident, text = item['id'], self.texts[item['id']]
            if text.endswith(('\r', '\n')):
                self.issue('symbol.trailing_line', ident, 'clipboard_local_v1 forbids trailing line terminators/empty rows')
            for number, line in enumerate(text.split('\r\n'), 1):
                where = f'{ident}:{number}'
                cells = line.split('\t')
                if len(cells) != 3 or not cells[0] or not cells[1]:
                    self.issue('symbol.columns', where, 'Exactly three TSV columns: name, address, comment; no blank row')
                    continue
                name, address, _comment = cells
                if number == 1 and name.casefold() in ('symbol', 'name', '符号', '名称') and address.casefold() in ('address', '地址'):
                    self.issue('symbol.header', where, 'Header rows are forbidden in this clipboard profile')
                    continue
                if name != name.strip() or address != address.strip():
                    self.issue('symbol.whitespace', where, 'Name/address must not have surrounding whitespace')
                legal_first = name[0] == '_' or name[0].isalpha() or 128 <= ord(name[0]) <= 255
                legal_rest = all(char.isalnum() or char == '_' or 128 <= ord(char) <= 255 for char in name)
                if not legal_first or not legal_rest or name.upper() in RESERVED:
                    self.issue('symbol.name', where, 'Illegal initial/name character or known reserved word')
                try:
                    if len(name.encode('gbk')) > 23:
                        self.issue('symbol.length', where, 'Name exceeds conservative GBK 23-byte engineering profile')
                except UnicodeError:
                    self.issue('symbol.gbk', where, 'Name is not representable in GBK')
                folded = name.casefold()
                if folded in self.symbols:
                    self.issue('symbol.duplicate_name', where, f'Duplicate across all tables: {name}')
                else:
                    self.symbols[folded] = (name, address, where)
                try:
                    span = address_span(address)
                except ValueError:
                    self.issue('symbol.address_review', where, 'Symbol constants/other address syntaxes require review', True)
                    continue
                key = span[:3]
                if key in addresses:
                    self.issue('symbol.duplicate_address', where, f'Same address as {addresses[key]}')
                addresses[key] = where
                views = {key for key, (_allocation, candidate) in self.allocations.items()
                         if span[0] == candidate[0] and candidate[1] <= span[1] and span[2] <= candidate[2]
                         and span[3] == candidate[3]}
                justified = {frozenset((alias['left'], alias['right'])) for alias in self.m['aliases']}
                for other_span, other_views, other_where in spans:
                    if span[:3] != other_span[:3] and overlap(span, other_span):
                        if not any(left != right and frozenset((left, right)) in justified
                                   for left in views for right in other_views):
                            self.issue('symbol.overlap_review', where, f'Partial symbol overlap with {other_where} has no explicit allocation-view alias', True)
                spans.append((span, views, where))
                if not any(span[0] == candidate[0] and candidate[1] <= span[1] and span[2] <= candidate[2]
                           for _allocation, candidate in self.allocations.values()):
                    self.issue('symbol.unallocated', where, 'Address has no declared allocation coverage')
        self.check('all_symbol_tables', unique_names=len(self.symbols), policy='clipboard_local_v1; conservative GBK bytes, casefold name comparison')

    def awl_checks(self):
        found = set()
        head = re.compile(r'(ORGANIZATION|SUBROUTINE|INTERRUPT)_BLOCK\s+(?:[^\s:]+:)?(OB\d+|SBR\d+|INT\d+)$', re.I)
        for item in self.m['inputs']:
            if item['kind'] != 'awl' or item['id'] not in self.texts:
                continue
            current, body, networks, instructions, in_var = None, False, [], 0, False
            for number, raw in enumerate(self.texts[item['id']].splitlines(), 1):
                where = f"{item['id']}:{number}"
                if re.search(r'密码保护|password.protect|POU.*protected|protected.*POU', raw, re.I):
                    self.issue('awl.protected_stub', where, 'Protected export marker is not an importable implementation')
                line = strip_comments(raw)
                if not line:
                    continue
                match = head.fullmatch(line)
                if match:
                    if current:
                        self.issue('awl.wrapper', where, 'Nested/new POU before END')
                    current = (match[1].upper(), match[2].upper())
                    body, networks, instructions, in_var = False, [], 0, False
                    kind, name = current
                    if not ((kind == 'ORGANIZATION' and name == 'OB1') or
                            (kind == 'SUBROUTINE' and name.startswith('SBR')) or
                            (kind == 'INTERRUPT' and name.startswith('INT'))):
                        self.issue('awl.wrapper', where, 'POU kind and identifier disagree')
                    if name in found:
                        self.issue('awl.duplicate_pou', where, name)
                    found.add(name)
                    if name not in self.m['import']['allowed_pous']:
                        self.issue('awl.disallowed_pou', where, name)
                    if name in self.m['import']['protected_pous']:
                        self.issue('awl.protected_pou', where, 'Import payload must not replace declared protected POU')
                    if name == 'OB1' and self.m['import']['scope'] == 'partial':
                        self.issue('awl.partial_ob1', where, 'Partial import containing OB1 can delete existing POUs')
                    continue
                if current is None:
                    self.issue('awl.wrapper', where, 'Text outside POU wrapper')
                    continue
                if line.upper().startswith('END_') and line.upper().endswith('_BLOCK'):
                    if line.upper() != f'END_{current[0]}_BLOCK' or not body:
                        self.issue('awl.wrapper', where, 'Wrong END wrapper or missing BEGIN')
                    if not networks or not instructions:
                        self.issue('awl.empty_pou', where, 'Empty POU may be a protected/export stub', True)
                    current = None
                    continue
                if line.upper() == 'BEGIN':
                    if body or in_var:
                        self.issue('awl.wrapper', where, 'Duplicate BEGIN or unclosed VAR declaration')
                    body = True
                    continue
                if not body:
                    if line.upper() in ('VAR', 'VAR_INPUT', 'VAR_OUTPUT', 'VAR_IN_OUT', 'VAR_TEMP'):
                        if in_var:
                            self.issue('awl.wrapper', where, 'Nested VAR declaration')
                        in_var = True
                    elif line.upper() == 'END_VAR':
                        if not in_var:
                            self.issue('awl.wrapper', where, 'END_VAR without VAR')
                        in_var = False
                    elif not line.upper().startswith('TITLE=') and not (in_var and re.fullmatch(r'[^\s:]+\s*:\s*[^;]+;', line)):
                        self.issue('awl.preamble_review', where, 'Unknown pre-BEGIN declaration syntax', True)
                    # Declaration type/signature semantics remain unvalidated.
                    continue
                network = re.fullmatch(r'NETWORK\s+(\d+)', line, re.I)
                if network:
                    value = int(network[1])
                    if value != len(networks) + 1:
                        self.issue('awl.network_sequence', where, 'Expected consecutive Network numbering from 1')
                    networks.append(value)
                elif not networks:
                    self.issue('awl.wrapper', where, 'Executable text before first Network')
                else:
                    instructions += 1
            if current:
                self.issue('awl.wrapper', item['id'], 'Unterminated POU')
        if self.m['import']['scope'] == 'full' and 'OB1' not in found:
            self.issue('awl.full_missing_ob1', 'import', 'Full import must explicitly include OB1')
        if not found:
            self.issue('awl.no_pous', 'inputs', 'No parsed POU')
        for missing in set(self.m['import']['allowed_pous']) - found:
            self.issue('awl.missing_expected_pou', 'import.allowed_pous', f'Expected import POU is missing: {missing}')
        self.check('awl_import_wrappers', found_pous=sorted(found), allowed_pous=self.m['import']['allowed_pous'])

    def migration_checks(self):
        for migration in self.m['migrations']:
            old = migration['old_name']
            if migration['new_name'] is not None:
                target = self.symbols.get(migration['new_name'].casefold())
                if not target or target[1].upper() != migration['address'].upper():
                    self.issue('migration.target', old, 'New symbol is missing or not mapped to declared address')
            if not any(a['address'].upper() == migration['address'].upper() and a['type'] == migration['type']
                       for a, _span in self.allocations.values()):
                self.issue('migration.allocation', old, 'Migration address/type does not match an allocation')
            pattern = re.compile(r'(?<!\w)' + re.escape(old) + r'(?!\w)', re.I)
            for item in self.m['inputs']:
                if item['kind'] not in ('awl', 'db') or item['id'] not in self.texts:
                    continue
                for number, raw in enumerate(self.texts[item['id']].splitlines(), 1):
                    code = strip_comments(raw, hide_strings=True)
                    if code.upper().startswith('TITLE='):
                        continue
                    if pattern.search(code):
                        self.issue('migration.old_reference', f"{item['id']}:{number}", f'Active text still references {old}')
        self.check('migration_active_text', entries=len(self.m['migrations']), scope='declared AWL/DB; excludes // comments, quoted literals and TITLE metadata')

    def db_checks(self):
        occupied = []
        numeric = re.compile(r'[+-]?\d+$')
        real = re.compile(r'[+-]?(?:\d+\.\d*|\d*\.\d+|\d+[Ee][+-]?\d+)(?:[Ee][+-]?\d+)?$')
        bit_pattern = re.compile(r'(2|16)#([0-9A-Fa-f]+)$')
        for item in self.m['inputs']:
            if item['kind'] != 'db' or item['id'] not in self.texts:
                continue
            for number, raw in enumerate(self.texts[item['id']].splitlines(), 1):
                where = f"{item['id']}:{number}"
                line = strip_comments(raw)
                if not line:
                    continue
                match = re.fullmatch(r'(V[BWD])(\d+)\s+(.+)', line, re.I)
                if not match:
                    self.issue('db.syntax_review', where, 'Only direct VB/VW/VD numeric scalar/comma-list lines are implemented', True)
                    continue
                prefix, byte, values = match.groups()
                size = {'VB': 1, 'VW': 2, 'VD': 4}[prefix.upper()]
                for index, token in enumerate(values.split(',')):
                    token = token.strip()
                    address = f'{prefix.upper()}{int(byte) + index * size}'
                    span = address_span(address)
                    if any(overlap(span, previous) for previous, _ in occupied):
                        self.issue('db.duplicate_address', where, f'Duplicate/overlapping initializer at {address}')
                    occupied.append((span, where))
                    candidates = {a['type'] for a, allocated in self.allocations.values()
                                  if span[0] == allocated[0] and allocated[1] <= span[1] and span[2] <= allocated[2]
                                  and span[3] == allocated[3] and (span[1] - allocated[1]) % span[3] == 0}
                    if len(candidates) != 1:
                        self.issue('db.allocation', where, f'{address} has missing, ambiguous, misaligned or width-mismatched declared type')
                        continue
                    dtype = next(iter(candidates))
                    pattern = bit_pattern.fullmatch(token)
                    try:
                        if real.fullmatch(token):
                            value, literal_type = float(token), 'real'
                        elif numeric.fullmatch(token):
                            value, literal_type = int(token), 'integer'
                        elif pattern:
                            value, literal_type = int(pattern[2], int(pattern[1])), 'bits'
                        else:
                            raise ValueError('Unsupported literal')
                    except ValueError:
                        self.issue('db.literal_review', where, f'Unimplemented numeric syntax: {token}', True)
                        continue
                    if dtype == 'REAL':
                        if literal_type != 'real' or not math.isfinite(value) or abs(value) > 3.4028234663852886e38:
                            self.issue('db.type', where, f'{address} requires a finite REAL literal fitting 32 bits')
                    elif literal_type == 'real':
                        self.issue('db.type', where, f'{address} declared {dtype}, not REAL')
                    elif dtype in ('INT', 'DINT') and literal_type == 'bits':
                        self.issue('db.signed_bit_pattern_review', where, 'Signed type with bit-pattern initializer needs native semantic review', True)
                    else:
                        bits = TYPE_BITS[dtype]
                        low, high = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if dtype in ('INT', 'DINT') else (0, (1 << bits) - 1)
                        if not low <= value <= high:
                            self.issue('db.range', where, f'{address}: literal outside declared {dtype} range')
        self.check('simple_numeric_db', initialized_cells=len(occupied))

    def evidence_checks(self):
        ids = {item['id'] for item in self.m['inputs']}
        evidence_ids = {item['id'] for item in self.m['evidence']}
        for missing in set(self.m['required_evidence']) - evidence_ids:
            self.issue('evidence.required', missing, 'Required evidence is not declared')
        for item in self.m['evidence']:
            ident = item['id']
            try:
                path, raw = self.local_file(item['file'], ident)
                actual = sha(raw)
                self.report['hashes']['evidence'][ident] = {'path': str(path), 'sha256': actual}
                if actual != item['sha256'].lower():
                    self.issue('evidence.file_hash', ident, 'Evidence file SHA-256 is stale/wrong')
            except (ValueError, OSError) as error:
                self.issue('evidence.file', ident, str(error))
            if item['context_sha256'].lower() != self.report['hashes']['context_sha256']:
                self.issue('evidence.context_hash', ident, 'Target/import/allocation/profile/manifest context changed')
            if set(item['input_sha256']) != ids:
                self.issue('evidence.dependency_set', ident, 'Evidence must name exactly all declared input ids, with no omissions/unknown ids')
            for input_id, expected in item['input_sha256'].items():
                actual = self.report['hashes']['inputs'].get(input_id, {}).get('sha256')
                if actual != expected.lower():
                    self.issue('evidence.input_hash', f'{ident}/{input_id}', 'Evidence dependency is missing or its SHA-256 changed')
        self.check('evidence_hash_binding', declared=len(evidence_ids), required=self.m['required_evidence'])

    def run(self):
        try:
            self.load()
        except (OSError, ValueError, UnicodeError) as error:
            self.issue('manifest.invalid', str(self.path), str(error))
            return self.report
        self.load_inputs()
        self.allocation_checks()
        self.symbol_checks()
        self.awl_checks()
        self.migration_checks()
        self.db_checks()
        self.evidence_checks()
        for name, before in self.files.items():
            try:
                if sha(Path(name).read_bytes()) != before:
                    self.issue('file.changed_during_run', name, 'Rerun against a stable snapshot')
            except OSError as error:
                self.issue('file.changed_during_run', name, str(error))
        self.report['successful'] = not self.report['errors'] and not self.report['review_required']
        return self.report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != '--manifest':
        report = {'successful': False, 'native_acceptance': False,
                  'errors': [{'code': 'cli.arguments', 'message': 'Usage: python -B plc_preflight.py --manifest LOCAL.json'}],
                  'review_required': [], 'checks': [], 'hashes': {}, 'not_covered': UNCOVERED}
        code = 2
    else:
        report = Preflight(argv[1]).run()
        code = 0 if report['successful'] else (2 if any(e['code'] == 'manifest.invalid' for e in report['errors']) else 1)
    # ASCII JSON is still valid UTF-8 and avoids console code-page corruption.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())

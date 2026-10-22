#!/usr/bin/env python3
"""Behavior tests; fixtures only under D: by default or explicit --temp-root."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import plc_preflight as tool

TEMP_ROOT = Path('D:/CodexData/Caches/PLC-Skill-Tests')


def safe_temporary_cleanup(directory, root):
    """Resolve and validate the exact generated directory before recursion."""
    resolved_root = Path(root).resolve()
    resolved_target = Path(directory.name).resolve()
    if resolved_target == resolved_root or not resolved_target.is_relative_to(resolved_root):
        raise RuntimeError(f'Refusing cleanup outside the explicit temporary root: {resolved_target}')
    directory.cleanup()


class Fixture:
    def __init__(self, directory):
        self.root = Path(directory)
        self.path = self.root / 'manifest.json'
        self.awl = 'SUBROUTINE_BLOCK SBR1\r\nTITLE=example\r\nBEGIN\r\nNETWORK 1\r\nLD M0.0\r\n= M0.1\r\nEND_SUBROUTINE_BLOCK\r\n'
        (self.root / 'program.awl').write_bytes(self.awl.encode('gbk'))
        (self.root / 'symbols.tsv').write_bytes('允许\tM0.0\t许可\r\n输出\tM0.1\t输出\r\n计数\tVW100\t计数'.encode('utf-8'))
        (self.root / 'data.db').write_bytes(b'VW100 +1\r\n')
        (self.root / 'evidence.txt').write_bytes(b'Fixture only; not a native acceptance claim.')
        self.m = {
            'schema_version': 1,
            'target': {'vendor': 'Siemens', 'family': 'S7-200 SMART', 'cpu': 'ST40',
                       'firmware': 'declared-test-2.8', 'software': 'STEP 7-Micro/WIN SMART', 'software_version': '2.8'},
            'import': {'scope': 'partial', 'allowed_pous': ['SBR1'], 'protected_pous': ['SBR0']},
            'inputs': [
                {'id': 'program', 'path': 'program.awl', 'kind': 'awl', 'encoding': 'gbk', 'profile': 'microwin_awl'},
                {'id': 'symbols', 'path': 'symbols.tsv', 'kind': 'symbols_tsv', 'encoding': 'utf-8', 'profile': 'clipboard_local_v1'},
                {'id': 'data', 'path': 'data.db', 'kind': 'db', 'encoding': 'gbk', 'profile': 'simple_numeric_db'},
            ],
            'inventory': {'symbol_tables_complete': True, 'basis': 'Test fixture owns all tables; not a native inventory assertion.'},
            'allocations': [
                {'id': 'permit', 'address': 'M0.0', 'type': 'BOOL', 'owner': 'operator', 'count': 1},
                {'id': 'output', 'address': 'M0.1', 'type': 'BOOL', 'owner': 'test_logic', 'count': 1},
                {'id': 'counter', 'address': 'VW100', 'type': 'INT', 'owner': 'test_logic', 'count': 1},
            ],
            'aliases': [], 'migrations': [], 'evidence': [], 'required_evidence': ['fixture'],
        }
        self.save(rebind=True)

    def save(self, rebind=False):
        if rebind:
            self.m['evidence'] = [{
                'id': 'fixture', 'file': 'evidence.txt',
                'sha256': tool.sha((self.root / 'evidence.txt').read_bytes()),
                'context_sha256': tool.context_hash(self.m),
                'input_sha256': {item['id']: tool.sha((self.root / item['path']).read_bytes()) for item in self.m['inputs']},
            }]
        self.path.write_text(json.dumps(self.m, ensure_ascii=False), encoding='utf-8')

    def run(self):
        return tool.Preflight(self.path).run()

    def write_awl(self, text):
        (self.root / 'program.awl').write_bytes(text.encode('gbk'))

    def write_symbols(self, text, name='symbols.tsv'):
        (self.root / name).write_bytes(text.encode('utf-8'))


class PreflightTests(unittest.TestCase):
    def setUp(self):
        if not TEMP_ROOT.is_absolute():
            raise RuntimeError('Test temporary root must be absolute; pass --temp-root explicitly on non-Windows hosts')
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix='preflight-', dir=TEMP_ROOT)
        self.addCleanup(safe_temporary_cleanup, self.directory, TEMP_ROOT)
        self.f = Fixture(self.directory.name)

    def codes(self, report):
        return {entry['code'] for entry in report['errors'] + report['review_required']}

    def assert_code(self, code):
        report = self.f.run()
        self.assertFalse(report['successful'])
        self.assertFalse(report['native_acceptance'])
        self.assertIn(code, self.codes(report))
        return report

    def test_normal_manifest_passes_only_implemented_static_checks(self):
        report = self.f.run()
        self.assertTrue(report['successful'], report)
        self.assertFalse(report['native_acceptance'])
        self.assertGreater(len(report['not_covered']), 5)
        self.assertEqual(set(report['hashes']['inputs']), {'program', 'symbols', 'data'})

    def test_bit_word_overlap_fails_without_explicit_alias(self):
        self.f.m['allocations'].append({'id': 'view', 'address': 'V100.0', 'type': 'BOOL', 'owner': 'diagnostic', 'count': 1})
        self.f.save(rebind=True)
        self.assert_code('allocation.overlap')

    def test_justified_explicit_bit_view_alias_passes(self):
        self.f.m['allocations'].append({'id': 'view', 'address': 'V100.0', 'type': 'BOOL', 'owner': 'diagnostic', 'count': 1})
        self.f.m['aliases'] = [{'left': 'counter', 'right': 'view', 'reason': 'Intentional read-only diagnostic bit view; same storage.'}]
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])

    def test_partial_symbol_overlap_cannot_hide_inside_one_wide_allocation(self):
        self.f.write_symbols('计数\tVW100\tword\r\n位视图\tV100.0\tbit')
        self.f.save(rebind=True)
        self.assert_code('symbol.overlap_review')

    def test_partial_symbol_views_pass_with_explicit_matching_allocation_alias(self):
        self.f.write_symbols('计数\tVW100\tword\r\n位视图\tV100.0\tbit')
        self.f.m['allocations'].append({'id': 'bit', 'address': 'V100.0', 'type': 'BOOL', 'owner': 'diagnostic', 'count': 1})
        self.f.m['aliases'].append({'left': 'counter', 'right': 'bit', 'reason': 'Read-only bit interpretation of the word'})
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])

    def test_underscore_initial_symbol_is_accepted(self):
        self.f.write_symbols('_Run\tM0.0\tvalid')
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])

    def test_alias_requires_reason_and_known_ids(self):
        for alias, code in (({'left': 'counter', 'right': 'absent', 'reason': 'documented'}, 'alias.invalid'),
                            ({'left': 'counter', 'right': 'permit', 'reason': ''}, 'manifest.invalid')):
            with self.subTest(alias=alias):
                self.f.m['aliases'] = [alias]
                self.f.save(rebind=True)
                self.assert_code(code)

    def test_counted_array_overlap_and_type_width_are_checked(self):
        self.f.m['allocations'][2]['count'] = 2
        self.f.m['allocations'].append({'id': 'other', 'address': 'VW102', 'type': 'DINT', 'owner': 'other', 'count': 1})
        self.f.save(rebind=True)
        report = self.assert_code('allocation.width')
        self.assertIn('allocation.overlap', self.codes(report))

    def test_old_name_in_active_awl_and_db_fails(self):
        self.f.m['migrations'] = [{'old_name': '旧计数', 'new_name': '计数', 'address': 'VW100', 'type': 'INT'}]
        self.f.write_awl(self.f.awl.replace('LD M0.0', 'LDW= 旧计数, +1'))
        (self.f.root / 'data.db').write_bytes('旧计数 +1\r\n'.encode('gbk'))
        self.f.save(rebind=True)
        report = self.assert_code('migration.old_reference')
        locations = [entry['location'] for entry in report['errors'] if entry['code'] == 'migration.old_reference']
        self.assertEqual(len(locations), 2)

    def test_old_name_comments_substrings_and_quoted_literals_are_not_references(self):
        self.f.m['migrations'] = [{'old_name': '旧计数', 'new_name': '计数', 'address': 'VW100', 'type': 'INT'}]
        text = self.f.awl.replace('TITLE=example', 'TITLE=旧计数').replace('LD M0.0', '// 旧计数\r\nLD M0.0 // 旧计数')
        self.f.write_awl(text)
        (self.f.root / 'data.db').write_bytes('VW100 +1 // 旧计数\r\n'.encode('gbk'))
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])
        hidden = tool.strip_comments('MOVB "旧计数//literal", VB2 // comment', True)
        self.assertNotIn('旧计数', hidden)
        self.assertNotIn('comment', hidden)
        self.assertTrue(hidden.endswith(', VB2'))

    def test_migration_new_symbol_address_must_match(self):
        self.f.m['migrations'] = [{'old_name': 'Old', 'new_name': '输出', 'address': 'VW100', 'type': 'INT'}]
        self.f.save(rebind=True)
        self.assert_code('migration.target')

    def add_second_table(self, text):
        self.f.write_symbols(text, 'other.tsv')
        self.f.m['inputs'].append({'id': 'other', 'path': 'other.tsv', 'kind': 'symbols_tsv', 'encoding': 'utf-8', 'profile': 'clipboard_local_v1'})
        self.f.save(rebind=True)

    def test_symbol_names_conflict_across_tables(self):
        self.add_second_table('允许\tM0.1\tduplicate')
        self.assert_code('symbol.duplicate_name')

    def test_symbol_same_address_conflicts_across_tables_despite_allocation_alias(self):
        self.add_second_table('另一个名字\tVW100\tduplicate address')
        self.assert_code('symbol.duplicate_address')

    def test_illegal_first_character_and_gbk_byte_length(self):
        self.f.write_symbols('1数字\tM0.0\tbad\r\n' + '中文' * 6 + '\tM0.1\ttoo long')
        self.f.save(rebind=True)
        report = self.assert_code('symbol.name')
        self.assertIn('symbol.length', self.codes(report))

    def test_symbol_unicode_outside_gbk_is_not_silently_replaced(self):
        self.f.write_symbols('允许😀\tM0.0\ttest')
        self.f.save(rebind=True)
        self.assert_code('symbol.gbk')

    def test_tsv_header_columns_newlines_and_final_line_profile(self):
        cases = [('符号\t地址\t注释', 'symbol.header'), ('允许\tM0.0', 'symbol.columns'),
                 ('允许\tM0.0\tx\r\n', 'symbol.trailing_line'),
                 ('允许\tM0.0\tx\n输出\tM0.1\tx', 'encoding.crlf')]
        for text, code in cases:
            with self.subTest(code=code):
                self.f.write_symbols(text)
                self.f.save(rebind=True)
                self.assert_code(code)

    def test_awl_bom_invalid_gbk_and_lf_are_rejected(self):
        cases = [(b'\xef\xbb\xbf' + self.f.awl.encode('gbk'), 'encoding.bom'),
                 (b'\x81', 'encoding.decode'),
                 (self.f.awl.replace('\r\n', '\n').encode('gbk'), 'encoding.crlf')]
        for raw, code in cases:
            with self.subTest(code=code):
                (self.f.root / 'program.awl').write_bytes(raw)
                self.f.save(rebind=True)
                self.assert_code(code)

    def test_partial_ob1_is_forbidden_even_if_allowlisted(self):
        self.f.write_awl(self.f.awl.replace('SUBROUTINE_BLOCK SBR1', 'ORGANIZATION_BLOCK MAIN:OB1').replace('END_SUBROUTINE_BLOCK', 'END_ORGANIZATION_BLOCK'))
        self.f.m['import']['allowed_pous'] = ['OB1']
        self.f.save(rebind=True)
        self.assert_code('awl.partial_ob1')

    def test_full_scope_requires_ob1(self):
        self.f.m['import']['scope'] = 'full'
        self.f.save(rebind=True)
        self.assert_code('awl.full_missing_ob1')

    def test_missing_expected_import_pou_is_rejected(self):
        self.f.m['import']['allowed_pous'].append('SBR2')
        self.f.save(rebind=True)
        self.assert_code('awl.missing_expected_pou')

    def test_full_ob1_valid_wrapper_can_pass_static_scope(self):
        self.f.write_awl(self.f.awl.replace('SUBROUTINE_BLOCK SBR1', 'ORGANIZATION_BLOCK MAIN:OB1').replace('END_SUBROUTINE_BLOCK', 'END_ORGANIZATION_BLOCK'))
        self.f.m['import'].update({'scope': 'full', 'allowed_pous': ['OB1']})
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])

    def test_protected_pou_stub_and_empty_pou_cannot_pass(self):
        self.f.write_awl('SUBROUTINE_BLOCK MBUS:SBR0\r\nTITLE=library\r\nBEGIN\r\nNETWORK 1 // This POU is password protected\r\nEND_SUBROUTINE_BLOCK\r\n')
        self.f.m['import']['allowed_pous'] = ['SBR0']
        self.f.save(rebind=True)
        report = self.assert_code('awl.protected_pou')
        self.assertIn('awl.protected_stub', self.codes(report))
        self.assertIn('awl.empty_pou', self.codes(report))

    def test_wrapper_mismatch_duplicate_network_disallowed_pou(self):
        self.f.write_awl(self.f.awl.replace('NETWORK 1', 'NETWORK 2').replace('END_SUBROUTINE_BLOCK', 'END_ORGANIZATION_BLOCK'))
        self.f.m['import']['allowed_pous'] = ['SBR2']
        self.f.save(rebind=True)
        report = self.assert_code('awl.wrapper')
        self.assertIn('awl.network_sequence', self.codes(report))
        self.assertIn('awl.disallowed_pou', self.codes(report))

    def test_unknown_db_syntax_requires_review_not_pass(self):
        (self.f.root / 'data.db').write_bytes(b'VW100 ARRAY[10]\r\n')
        self.f.save(rebind=True)
        report = self.assert_code('db.literal_review')
        self.assertTrue(report['review_required'])

    def test_db_equals_assignment_is_not_claimed_as_supported_siemens_syntax(self):
        (self.f.root / 'data.db').write_bytes(b'VW100 = +1\r\n')
        self.f.save(rebind=True)
        report = self.assert_code('db.literal_review')
        self.assertEqual(report['errors'], [])

    def test_db_duplicate_width_type_and_range_checks(self):
        for text, code in [('VW100 +1\r\nVW100 +2\r\n', 'db.duplicate_address'),
                           ('VD100 +1\r\n', 'db.allocation'),
                           ('VW100 1.5\r\n', 'db.type'), ('VW100 +32768\r\n', 'db.range')]:
            with self.subTest(code=code):
                (self.f.root / 'data.db').write_bytes(text.encode('gbk'))
                self.f.save(rebind=True)
                self.assert_code(code)

    def test_db_numeric_array_and_real_supported(self):
        self.f.m['allocations'][2]['count'] = 2
        self.f.m['allocations'].append({'id': 'real', 'address': 'VD200', 'type': 'REAL', 'owner': 'test', 'count': 1})
        (self.f.root / 'data.db').write_bytes(b'VW100 +1, -2\r\nVD200 1.5\r\n')
        self.f.save(rebind=True)
        self.assertTrue(self.f.run()['successful'])

    def test_signed_bit_pattern_requires_review(self):
        (self.f.root / 'data.db').write_bytes(b'VW100 16#FFFF\r\n')
        self.f.save(rebind=True)
        self.assert_code('db.signed_bit_pattern_review')

    def test_inventory_missing_or_unconfirmed_requires_review(self):
        for inventory in (None, {'symbol_tables_complete': False, 'basis': 'not yet checked'}):
            with self.subTest(inventory=inventory):
                self.f.m.pop('inventory', None)
                if inventory is not None:
                    self.f.m['inventory'] = inventory
                self.f.save(rebind=True)
                self.assert_code('inventory.unconfirmed')

    def test_input_changed_invalidates_evidence(self):
        self.f.write_awl(self.f.awl.replace('TITLE=example', 'TITLE=changed'))
        self.assert_code('evidence.input_hash')

    def test_target_change_invalidates_evidence_context(self):
        self.f.m['target']['cpu'] = 'SR20'
        self.f.save()
        self.assert_code('evidence.context_hash')

    def test_evidence_content_change_invalidates_evidence_file_hash(self):
        (self.f.root / 'evidence.txt').write_bytes(b'changed')
        self.assert_code('evidence.file_hash')

    def test_repeated_read_change_keeps_first_hash_and_fails_immediately(self):
        checker = tool.Preflight(self.f.path)
        checker.load()
        path, original = checker.local_file('program.awl', 'program')
        first_hash = tool.sha(original)
        self.f.write_awl(self.f.awl.replace('TITLE=example', 'TITLE=changed'))
        checker.local_file('program.awl', 'evidence')
        self.assertEqual(checker.files[str(path)], first_hash)
        self.assertIn('file.changed_between_reads', self.codes(checker.report))

    def test_end_of_run_detects_input_mutation_after_checks(self):
        target = self.f.root / 'program.awl'
        class ChangingFixture(tool.Preflight):
            def evidence_checks(self):
                super().evidence_checks()
                target.write_bytes(target.read_bytes() + b'// changed after checks\r\n')
        result = ChangingFixture(self.f.path).run()
        self.assertFalse(result['successful'])
        self.assertIn('file.changed_during_run', self.codes(result))

    def test_evidence_requires_all_and_only_declared_inputs(self):
        self.f.m['evidence'][0]['input_sha256'].pop('symbols')
        self.f.m['evidence'][0]['input_sha256']['unknown'] = '0' * 64
        self.f.save()
        self.assert_code('evidence.dependency_set')

    def test_missing_input_evidence_and_required_evidence_fail(self):
        (self.f.root / 'data.db').unlink()
        (self.f.root / 'evidence.txt').unlink()
        self.f.m['required_evidence'].append('absent')
        self.f.save()
        report = self.assert_code('input.file')
        self.assertIn('evidence.file', self.codes(report))
        self.assertIn('evidence.required', self.codes(report))

    def test_manifest_wrong_type_unknown_key_and_duplicate_json_key(self):
        original = copy.deepcopy(self.f.m)
        for mutate in (lambda m: m.update({'schema_version': True}),
                       lambda m: m['allocations'][0].update({'count': '1'}),
                       lambda m: m.update({'command': 'Never execute this string'})):
            self.f.m = copy.deepcopy(original)
            mutate(self.f.m)
            self.f.save()
            self.assert_code('manifest.invalid')
        self.f.path.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
        self.assert_code('manifest.invalid')

    def test_manifest_size_limit_is_checked_before_json_parse(self):
        self.f.path.write_bytes(b' ' * (tool.LIMIT + 1))
        report = self.assert_code('manifest.invalid')
        self.assertIn('read limit', report['errors'][0]['message'])

    def test_cleanup_refuses_root_or_outside_target(self):
        class FakeDirectory:
            def __init__(self, name):
                self.name, self.called = str(name), False
            def cleanup(self):
                self.called = True
        for name in (TEMP_ROOT, TEMP_ROOT.parent / 'not-owned'):
            directory = FakeDirectory(name)
            with self.assertRaises(RuntimeError):
                safe_temporary_cleanup(directory, TEMP_ROOT)
            self.assertFalse(directory.called)

    def test_http_and_unc_paths_are_rejected_without_fetching(self):
        for path in ('https://example.invalid/program.awl', r'\\server\share\program.awl'):
            self.f.m['inputs'][0]['path'] = path
            self.f.save()
            self.assert_code('input.file')
        result = tool.Preflight('https://example.invalid/manifest.json').run()
        self.assertIn('manifest.invalid', self.codes(result))

    def test_unknown_address_and_type_are_review_not_silent_pass(self):
        self.f.m['allocations'].append({'id': 'timer', 'address': 'T37', 'type': 'TIMER', 'owner': 'timer', 'count': 1})
        self.f.save(rebind=True)
        self.assert_code('allocation.address_review')

    def test_cli_json_exit_codes_and_no_input_writes(self):
        before = {p.name: p.read_bytes() for p in self.f.root.iterdir() if p.is_file()}
        result = subprocess.run([sys.executable, '-B', str(Path(tool.__file__)), '--manifest', str(self.f.path)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['successful'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.f.root.iterdir() if p.is_file()})
        (self.f.root / 'data.db').write_bytes(b'unknown syntax\r\n')
        result = subprocess.run([sys.executable, '-B', str(Path(tool.__file__)), '--manifest', str(self.f.path)], capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['successful'])
        result = subprocess.run([sys.executable, '-B', str(Path(tool.__file__))], capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['native_acceptance'])


if __name__ == '__main__':
    if '--temp-root' in sys.argv:
        index = sys.argv.index('--temp-root')
        if index + 1 >= len(sys.argv):
            raise SystemExit('--temp-root needs an explicit absolute path')
        TEMP_ROOT = Path(sys.argv[index + 1])
        del sys.argv[index:index + 2]
    unittest.main()

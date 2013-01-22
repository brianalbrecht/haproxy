from contextlib import contextmanager

from testtools import TestCase
from mock import patch, call, MagicMock

import hooks


class ReverseProxyRelationTest(TestCase):

    def setUp(self):
        super(ReverseProxyRelationTest, self).setUp()

        self.get_relation_data = self.patch_hook("get_relation_data")
        self.get_config_services = self.patch_hook("get_config_services")
        self.log = self.patch_hook("log")
        self.write_service_config = self.patch_hook("write_service_config")

    def patch_hook(self, hook_name):
        mock_controller = patch.object(hooks, hook_name)
        mock = mock_controller.start()
        self.addCleanup(mock_controller.stop)
        return mock

    def test_relation_data_returns_none(self):
        self.get_relation_data.return_value = None
        self.assertIs(None, hooks.create_services())
        self.log.assert_called_once_with("No relation data, exiting.")
        self.write_service_config.assert_not_called()

    def test_relation_data_returns_no_relations(self):
        self.get_relation_data.return_value = ()
        self.assertIs(None, hooks.create_services())
        self.log.assert_called_once_with("No relation data, exiting.")
        self.write_service_config.assert_not_called()

    def test_no_port_in_relation_data(self):
        self.get_relation_data.return_value = {
            "foo": {"private-address": "1.2.3.4"},
        }
        self.assertIs(None, hooks.create_services())
        self.log.assert_called_once_with(
            "No port in relation data for 'foo', skipping.")
        self.write_service_config.assert_not_called()

    def test_no_private_address_in_relation_data(self):
        self.get_relation_data.return_value = {
            "foo": {"port": 4242},
        }
        self.assertIs(None, hooks.create_services())
        self.log.assert_called_once_with(
            "No private-address in relation data for 'foo', skipping.")
        self.write_service_config.assert_not_called()

    def test_no_hostname_in_relation_data(self):
        self.get_relation_data.return_value = {
            "foo": {"port": 4242,
                    "private-address": "1.2.3.4"},
        }
        self.assertIs(None, hooks.create_services())
        self.log.assert_called_once_with(
            "No hostname in relation data for 'foo', skipping.")
        self.write_service_config.assert_not_called()

    @patch('hooks.config_get')
    def test_creates_haproxy_globals(self, config_get):
        config_get.return_value = {
            'global_log': 'foo-log, bar-log',
            'global_maxconn': 123,
            'global_user': 'foo-user',
            'global_group': 'foo-group',
            'global_spread_checks': 234,
            'global_debug': False,
            'global_quiet': False,
        }
        result = hooks.create_haproxy_globals()

        expected = '\n'.join([
            'global',
            '    log foo-log',
            '    log bar-log',
            '    maxconn 123',
            '    user foo-user',
            '    group foo-group',
            '    spread-checks 234',
        ])
        self.assertEqual(result, expected)

    @patch('hooks.config_get')
    def test_creates_haproxy_globals_quietly_with_debug(self, config_get):
        config_get.return_value = {
            'global_log': 'foo-log, bar-log',
            'global_maxconn': 123,
            'global_user': 'foo-user',
            'global_group': 'foo-group',
            'global_spread_checks': 234,
            'global_debug': True,
            'global_quiet': True,
        }
        result = hooks.create_haproxy_globals()

        expected = '\n'.join([
            'global',
            '    log foo-log',
            '    log bar-log',
            '    maxconn 123',
            '    user foo-user',
            '    group foo-group',
            '    debug',
            '    quiet',
            '    spread-checks 234',
        ])
        self.assertEqual(result, expected)


class HelpersTest(TestCase):
    def test_log(self):
        with patch('subprocess.call') as mock_call:
            msg = 'some message'

            hooks.log(msg)

            mock_call.assert_called_with(["juju-log", msg])

    def test_gets_config(self):
        json_string = '{"foo": "BAR"}'
        with patch('subprocess.check_output') as check_output:
            check_output.return_value = json_string

            result = hooks.config_get()

            self.assertEqual(result['foo'], 'BAR')
            check_output.assert_called_with(['config-get', '--format=json'])

    def test_gets_config_with_scope(self):
        json_string = '{"foo": "BAR"}'
        with patch('subprocess.check_output') as check_output:
            check_output.return_value = json_string

            result = hooks.config_get(scope='baz')

            self.assertEqual(result['foo'], 'BAR')
            check_output.assert_called_with(['config-get', 'baz',
                                             '--format=json'])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_logs_and_returns_none_if_config_get_fails(self, log,
                                                       check_output):
        check_output.side_effect = RuntimeError('some error')

        result = hooks.config_get()

        log.assert_called_with('some error')
        self.assertIsNone(result)

    @patch('subprocess.call')
    def test_installs_packages(self, mock_call):
        mock_call.return_value = 'some result'

        result = hooks.apt_get_install('foo bar')

        self.assertEqual(result, 'some result')
        mock_call.assert_called_with(['apt-get', '-y', 'install', '-qq',
                                      'foo bar'])

    def test_installs_nothing_if_package_not_provided(self):
        self.assertFalse(hooks.apt_get_install())

    def test_enables_haproxy(self):
        mock_file = MagicMock()

        @contextmanager
        def mock_open(*args, **kwargs):
            yield mock_file

        initial_content = """
        foo
        ENABLED=0
        bar
        """
        ending_content = initial_content.replace('ENABLED=0', 'ENABLED=1')

        with patch('__builtin__.open', mock_open):
            mock_file.read.return_value = initial_content

            hooks.enable_haproxy()

            mock_file.write.assert_called_with(ending_content)


class RelationsTest(TestCase):
    @patch('subprocess.check_output')
    def test_gets_relation(self, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.relation_get()

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-get', '--format=json', ''])

    @patch('subprocess.check_output')
    def test_gets_relation_with_scope(self, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.relation_get(scope='baz-scope')

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-get', '--format=json',
                                         'baz-scope'])

    @patch('subprocess.check_output')
    def test_gets_relation_with_unit_name(self, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.relation_get(scope='baz-scope', unit_name='baz-unit')

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-get', '--format=json',
                                         'baz-scope', 'baz-unit'])

    @patch('subprocess.check_output')
    def test_gets_relation_with_relation_id(self, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.relation_get(scope='baz-scope', unit_name='baz-unit',
                                    relation_id=123)

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-get', '--format=json', '-r',
                                         123, 'baz-scope', 'baz-unit'])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_logs_and_returns_none_relation_get_fails(self, log,
                                                      check_output):
        check_output.side_effect = RuntimeError('some error')

        result = hooks.relation_get()

        log.assert_called_with('some error')
        self.assertIsNone(result)

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_gets_relation_ids(self, log, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.get_relation_ids()

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-ids', '--format=json'])
        log.assert_called_with('Calling: %s' % ['relation-ids',
                                                '--format=json'])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_gets_relation_ids_by_name(self, log, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.get_relation_ids(relation_name='baz')

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-ids', '--format=json',
                                         'baz'])
        log.assert_called_with('Calling: %s' % ['relation-ids',
                                                '--format=json', 'baz'])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_returns_none_when_get_relation_ids_fails(self, log,
                                                      check_output):
        check_output.side_effect = RuntimeError('some error')

        result = hooks.get_relation_ids()

        log.assert_called_with('Calling: %s' % ['relation-ids',
                                                '--format=json'])
        self.assertIsNone(result)

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_gets_relation_list(self, log, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.get_relation_list()

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-list', '--format=json'])
        log.assert_called_with('Calling: %s' % ['relation-list',
                                                '--format=json'])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_gets_relation_list_by_id(self, log, check_output):
        json_string = '{"foo": "BAR"}'
        check_output.return_value = json_string

        result = hooks.get_relation_list(relation_id=123)

        self.assertEqual(result['foo'], 'BAR')
        check_output.assert_called_with(['relation-list', '--format=json',
                                         '-r', 123])
        log.assert_called_with('Calling: %s' % ['relation-list',
                                                '--format=json', '-r', 123])

    @patch('subprocess.check_output')
    @patch('hooks.log')
    def test_returns_none_when_get_relation_list_fails(self, log,
                                                       check_output):
        check_output.side_effect = RuntimeError('some error')

        result = hooks.get_relation_list()

        log.assert_called_with('Calling: %s' % ['relation-list',
                                                '--format=json'])
        self.assertIsNone(result)

    @patch('hooks.get_relation_ids')
    @patch('hooks.get_relation_list')
    @patch('hooks.relation_get')
    def test_gets_relation_data_by_name(self, relation_get, get_relation_list,
                                        get_relation_ids):
        get_relation_ids.return_value = [1, 2]
        get_relation_list.side_effect = [
            ['foo/1', 'bar/1'],
            ['foo/2', 'bar/2'],
        ]
        relation_get.side_effect = [
            'FOO 1',
            'BAR 1',
            'FOO 2',
            'BAR 2',
        ]

        result = hooks.get_relation_data(relation_name='baz')
        expected_data = {
            'foo-1': 'FOO 1',
            'bar-1': 'BAR 1',
            'foo-2': 'FOO 2',
            'bar-2': 'BAR 2',
        }

        self.assertEqual(result, expected_data)
        get_relation_ids.assert_called_with('baz')
        self.assertEqual(get_relation_list.mock_calls, [
            call(relation_id=1),
            call(relation_id=2),
        ])
        self.assertEqual(relation_get.mock_calls, [
            call(relation_id=1, unit_name='foo/1'),
            call(relation_id=1, unit_name='bar/1'),
            call(relation_id=2, unit_name='foo/2'),
            call(relation_id=2, unit_name='bar/2'),
        ])

    @patch('hooks.get_relation_ids')
    def test_gets_data_as_none_if_no_relation_ids_exist(self,
                                                        get_relation_ids):
        get_relation_ids.return_value = None

        result = hooks.get_relation_data(relation_name='baz')

        self.assertEqual(result, ())
        get_relation_ids.assert_called_with('baz')

    @patch('hooks.get_relation_ids')
    @patch('hooks.get_relation_list')
    def test_returns_none_if_get_data_fails(self, get_relation_list,
                                            get_relation_ids):
        get_relation_ids.return_value = [1, 2]
        get_relation_list.side_effect = RuntimeError('some error')

        result = hooks.get_relation_data(relation_name='baz')

        self.assertIsNone(result)

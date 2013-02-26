from contextlib import contextmanager
from StringIO import StringIO

from testtools import TestCase
from mock import patch, call, MagicMock

import hooks


class HelpersTest(TestCase):

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

    @patch('subprocess.call')
    def test_installs_nothing_if_package_not_provided(self, mock_call):
        self.assertFalse(hooks.apt_get_install())
        self.assertFalse(mock_call.called)

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

    @patch('hooks.config_get')
    def test_creates_haproxy_defaults(self, config_get):
        config_get.return_value = {
            'default_options': 'foo-option, bar-option',
            'default_timeouts': '234, 456',
            'default_log': 'foo-log',
            'default_mode': 'foo-mode',
            'default_retries': 321,
        }
        result = hooks.create_haproxy_defaults()

        expected = '\n'.join([
            'defaults',
            '    log foo-log',
            '    mode foo-mode',
            '    option foo-option',
            '    option bar-option',
            '    retries 321',
            '    timeout 234',
            '    timeout 456',
        ])
        self.assertEqual(result, expected)

    def test_returns_none_when_haproxy_config_doesnt_exist(self):
        self.assertIsNone(hooks.load_haproxy_config('/some/foo/file'))

    @patch('__builtin__.open')
    @patch('os.path.isfile')
    def test_loads_haproxy_config_file(self, isfile, mock_open):
        content = 'some content'
        config_file = '/etc/haproxy/haproxy.cfg'
        file_object = StringIO(content)
        isfile.return_value = True
        mock_open.return_value = file_object

        result = hooks.load_haproxy_config()

        self.assertEqual(result, content)
        isfile.assert_called_with(config_file)
        mock_open.assert_called_with(config_file)

    @patch('hooks.load_haproxy_config')
    def test_gets_monitoring_password(self, load_haproxy_config):
        load_haproxy_config.return_value = 'stats auth foo:bar'

        password = hooks.get_monitoring_password()

        self.assertEqual(password, 'bar')

    @patch('hooks.load_haproxy_config')
    def test_gets_none_if_different_pattern(self, load_haproxy_config):
        load_haproxy_config.return_value = 'some other pattern'

        password = hooks.get_monitoring_password()

        self.assertIsNone(password)

    def test_gets_none_pass_if_config_doesnt_exist(self):
        password = hooks.get_monitoring_password('/some/foo/path')

        self.assertIsNone(password)

    @patch('hooks.load_haproxy_config')
    def test_gets_service_ports(self, load_haproxy_config):
        load_haproxy_config.return_value = '''
        listen foo.internal 1.2.3.4:123
        listen bar.internal 1.2.3.5:234
        '''

        ports = hooks.get_service_ports()

        self.assertEqual(ports, (123, 234))

    @patch('hooks.load_haproxy_config')
    def test_get_listen_stanzas(self, load_haproxy_config):
        load_haproxy_config.return_value = '''
        listen   foo.internal  1.2.3.4:123
        listen bar.internal    1.2.3.5:234
        '''

        stanzas = hooks.get_listen_stanzas()

        self.assertEqual((('foo.internal', '1.2.3.4', 123),
                          ('bar.internal', '1.2.3.5', 234)),
                         stanzas)

    @patch('hooks.load_haproxy_config')
    def test_get_empty_tuple_when_no_stanzas(self, load_haproxy_config):
        load_haproxy_config.return_value = '''
        '''

        stanzas = hooks.get_listen_stanzas()

        self.assertEqual((), stanzas)

    @patch('hooks.load_haproxy_config')
    def test_get_listen_stanzas_none_configured(self, load_haproxy_config):
        load_haproxy_config.return_value = ""

        stanzas = hooks.get_listen_stanzas()

        self.assertEqual((), stanzas)

    def test_gets_no_ports_if_config_doesnt_exist(self):
        ports = hooks.get_service_ports('/some/foo/path')
        self.assertEqual((), ports)

    @patch('subprocess.check_output')
    def test_gets_unit(self, check_output):
        check_output.return_value = ' some result   '

        result = hooks.unit_get('some-item')

        self.assertEqual(result, 'some result')
        check_output.assert_called_with(['unit-get', 'some-item'])

    @patch('subprocess.check_output')
    @patch.object(hooks, 'log')
    def test_logs_error_when_cant_get_unit(self, log, check_output):
        error = Exception('something wrong')
        check_output.side_effect = error

        result = hooks.unit_get('some-item')

        self.assertIsNone(result)
        log.assert_called_with(str(error))

    @patch('subprocess.call')
    def test_opens_a_port(self, mock_call):
        mock_call.return_value = 'some result'

        result = hooks.open_port(1234)

        self.assertEqual(result, 'some result')
        mock_call.assert_called_with(['open-port', '1234/TCP'])

    @patch('subprocess.call')
    def test_opens_a_port_with_different_protocol(self, mock_call):
        mock_call.return_value = 'some result'

        result = hooks.open_port(1234, protocol='UDP')

        self.assertEqual(result, 'some result')
        mock_call.assert_called_with(['open-port', '1234/UDP'])

    @patch('subprocess.call')
    def test_does_nothing_to_open_port_as_none(self, mock_call):
        self.assertIsNone(hooks.open_port())
        self.assertFalse(mock_call.called)

    @patch('subprocess.call')
    def test_closes_a_port(self, mock_call):
        mock_call.return_value = 'some result'

        result = hooks.close_port(1234)

        self.assertEqual(result, 'some result')
        mock_call.assert_called_with(['close-port', '1234/TCP'])

    @patch('subprocess.call')
    def test_closes_a_port_with_different_protocol(self, mock_call):
        mock_call.return_value = 'some result'

        result = hooks.close_port(1234, protocol='UDP')

        self.assertEqual(result, 'some result')
        mock_call.assert_called_with(['close-port', '1234/UDP'])

    @patch('subprocess.call')
    def test_does_nothing_to_close_port_as_none(self, mock_call):
        self.assertIsNone(hooks.close_port())
        self.assertFalse(mock_call.called)

    @patch('hooks.open_port')
    @patch('hooks.close_port')
    def test_updates_service_ports(self, close_port, open_port):
        old_service_ports = [123, 234, 345]
        new_service_ports = [345, 456, 567]

        hooks.update_service_ports(old_service_ports, new_service_ports)

        self.assertEqual(close_port.mock_calls, [call(123), call(234)])
        self.assertEqual(open_port.mock_calls, [call(456), call(567)])

    @patch('hooks.open_port')
    @patch('hooks.close_port')
    def test_updates_none_if_service_ports_not_provided(self, close_port,
                                                        open_port):
        hooks.update_service_ports()

        self.assertFalse(close_port.called)
        self.assertFalse(open_port.called)

    def test_generates_a_password(self):
        password = hooks.pwgen()

        self.assertIsInstance(password, str)
        self.assertEqual(len(password), 20)

    def test_generates_a_password_with_different_size(self):
        password = hooks.pwgen(pwd_length=15)

        self.assertIsInstance(password, str)
        self.assertEqual(len(password), 15)

    def test_generates_a_different_password_each_time(self):
        password1 = hooks.pwgen()
        password2 = hooks.pwgen()

        self.assertNotEqual(password1, password2)

    def test_creates_a_listen_stanza(self):
        service_name = 'some-name'
        service_ip = '10.11.12.13'
        service_port = 1234
        service_options = ('foo', 'bar')
        server_entries = [
            ('name-1', 'ip-1', 'port-1', ('foo1', 'bar1')),
            ('name-2', 'ip-2', 'port-2', ('foo2', 'bar2')),
        ]

        result = hooks.create_listen_stanza(service_name, service_ip,
                                            service_port, service_options,
                                            server_entries)

        expected = '\n'.join((
            'listen some-name 10.11.12.13:1234',
            '    foo',
            '    bar',
            '    server name-1 ip-1:port-1 foo1 bar1',
            '    server name-2 ip-2:port-2 foo2 bar2',
        ))

        self.assertEqual(expected, result)

    def test_creates_a_listen_stanza_with_tuple_entries(self):
        service_name = 'some-name'
        service_ip = '10.11.12.13'
        service_port = 1234
        service_options = ('foo', 'bar')
        server_entries = (
            ('name-1', 'ip-1', 'port-1', ('foo1', 'bar1')),
            ('name-2', 'ip-2', 'port-2', ('foo2', 'bar2')),
        )

        result = hooks.create_listen_stanza(service_name, service_ip,
                                            service_port, service_options,
                                            server_entries)

        expected = '\n'.join((
            'listen some-name 10.11.12.13:1234',
            '    foo',
            '    bar',
            '    server name-1 ip-1:port-1 foo1 bar1',
            '    server name-2 ip-2:port-2 foo2 bar2',
        ))

        self.assertEqual(expected, result)

    def test_doesnt_create_listen_stanza_if_args_not_provided(self):
        self.assertIsNone(hooks.create_listen_stanza())

    @patch('hooks.create_listen_stanza')
    @patch('hooks.config_get')
    @patch('hooks.get_monitoring_password')
    def test_creates_a_monitoring_stanza(self, get_monitoring_password,
                                         config_get, create_listen_stanza):
        config_get.return_value = {
            'enable_monitoring': True,
            'monitoring_allowed_cidr': 'some-cidr',
            'monitoring_password': 'some-pass',
            'monitoring_username': 'some-user',
            'monitoring_stats_refresh': 123,
            'monitoring_port': 1234,
        }
        create_listen_stanza.return_value = 'some result'

        result = hooks.create_monitoring_stanza(service_name="some-service")

        self.assertEqual('some result', result)
        get_monitoring_password.assert_called_with()
        create_listen_stanza.assert_called_with(
            'some-service', '0.0.0.0', 1234, [
                'mode http',
                'acl allowed_cidr src some-cidr',
                'block unless allowed_cidr',
                'stats enable',
                'stats uri /',
                'stats realm Haproxy\\ Statistics',
                'stats auth some-user:some-pass',
                'stats refresh 123',
            ])

    @patch('hooks.create_listen_stanza')
    @patch('hooks.config_get')
    @patch('hooks.get_monitoring_password')
    def test_doesnt_create_a_monitoring_stanza_if_monitoring_disabled(
            self, get_monitoring_password, config_get, create_listen_stanza):
        config_get.return_value = {
            'enable_monitoring': False,
        }

        result = hooks.create_monitoring_stanza(service_name="some-service")

        self.assertIsNone(result)
        self.assertFalse(get_monitoring_password.called)
        self.assertFalse(create_listen_stanza.called)

    @patch('hooks.create_listen_stanza')
    @patch('hooks.config_get')
    @patch('hooks.get_monitoring_password')
    def test_uses_monitoring_password_for_stanza(self, get_monitoring_password,
                                                 config_get,
                                                 create_listen_stanza):
        config_get.return_value = {
            'enable_monitoring': True,
            'monitoring_allowed_cidr': 'some-cidr',
            'monitoring_password': 'changeme',
            'monitoring_username': 'some-user',
            'monitoring_stats_refresh': 123,
            'monitoring_port': 1234,
        }
        create_listen_stanza.return_value = 'some result'
        get_monitoring_password.return_value = 'some-monitoring-pass'

        hooks.create_monitoring_stanza(service_name="some-service")

        get_monitoring_password.assert_called_with()
        create_listen_stanza.assert_called_with(
            'some-service', '0.0.0.0', 1234, [
                'mode http',
                'acl allowed_cidr src some-cidr',
                'block unless allowed_cidr',
                'stats enable',
                'stats uri /',
                'stats realm Haproxy\\ Statistics',
                'stats auth some-user:some-monitoring-pass',
                'stats refresh 123',
            ])

    @patch('hooks.pwgen')
    @patch('hooks.create_listen_stanza')
    @patch('hooks.config_get')
    @patch('hooks.get_monitoring_password')
    def test_uses_new_password_for_stanza(self, get_monitoring_password,
                                          config_get, create_listen_stanza,
                                          pwgen):
        config_get.return_value = {
            'enable_monitoring': True,
            'monitoring_allowed_cidr': 'some-cidr',
            'monitoring_password': 'changeme',
            'monitoring_username': 'some-user',
            'monitoring_stats_refresh': 123,
            'monitoring_port': 1234,
        }
        create_listen_stanza.return_value = 'some result'
        get_monitoring_password.return_value = None
        pwgen.return_value = 'some-new-pass'

        hooks.create_monitoring_stanza(service_name="some-service")

        get_monitoring_password.assert_called_with()
        create_listen_stanza.assert_called_with(
            'some-service', '0.0.0.0', 1234, [
                'mode http',
                'acl allowed_cidr src some-cidr',
                'block unless allowed_cidr',
                'stats enable',
                'stats uri /',
                'stats realm Haproxy\\ Statistics',
                'stats auth some-user:some-new-pass',
                'stats refresh 123',
            ])

    @patch('hooks.is_proxy')
    @patch('hooks.config_get')
    @patch('yaml.safe_load')
    def test_gets_config_services(self, safe_load, config_get, is_proxy):
        config_get.return_value = {
            'services': 'some-services',
        }
        safe_load.return_value = [
            {
                'service_name': 'foo',
                'service_options': {
                    'foo-1': 123,
                },
                'service_options': ['foo1', 'foo2'],
                'server_options': ['baz1', 'baz2'],
            },
            {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2'],
                'server_options': ['baz1', 'baz2'],
            },
        ]
        is_proxy.return_value = False

        result = hooks.get_config_services()
        expected = {
            None: {
                'service_name': 'foo',
            },
            'foo': {
                'service_name': 'foo',
                'service_options': ['foo1', 'foo2'],
                'server_options': ['baz1', 'baz2'],
            },
            'bar': {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2'],
                'server_options': ['baz1', 'baz2'],
            },
        }

        self.assertEqual(expected, result)

    @patch('hooks.is_proxy')
    @patch('hooks.config_get')
    @patch('yaml.safe_load')
    def test_gets_config_services_with_forward_option(self, safe_load,
                                                      config_get, is_proxy):
        config_get.return_value = {
            'services': 'some-services',
        }
        safe_load.return_value = [
            {
                'service_name': 'foo',
                'service_options': {
                    'foo-1': 123,
                },
                'service_options': ['foo1', 'foo2'],
                'server_options': ['baz1', 'baz2'],
            },
            {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2'],
                'server_options': ['baz1', 'baz2'],
            },
        ]
        is_proxy.return_value = True

        result = hooks.get_config_services()
        expected = {
            None: {
                'service_name': 'foo',
            },
            'foo': {
                'service_name': 'foo',
                'service_options': ['foo1', 'foo2', 'option forwardfor'],
                'server_options': ['baz1', 'baz2'],
            },
            'bar': {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2', 'option forwardfor'],
                'server_options': ['baz1', 'baz2'],
            },
        }

        self.assertEqual(expected, result)

    @patch('hooks.is_proxy')
    @patch('hooks.config_get')
    @patch('yaml.safe_load')
    def test_gets_config_services_with_options_string(self, safe_load,
                                                      config_get, is_proxy):
        config_get.return_value = {
            'services': 'some-services',
        }
        safe_load.return_value = [
            {
                'service_name': 'foo',
                'service_options': {
                    'foo-1': 123,
                },
                'service_options': ['foo1', 'foo2'],
                'server_options': 'baz1 baz2',
            },
            {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2'],
                'server_options': 'baz1 baz2',
            },
        ]
        is_proxy.return_value = False

        result = hooks.get_config_services()
        expected = {
            None: {
                'service_name': 'foo',
            },
            'foo': {
                'service_name': 'foo',
                'service_options': ['foo1', 'foo2'],
                'server_options': ['baz1', 'baz2'],
            },
            'bar': {
                'service_name': 'bar',
                'service_options': ['bar1', 'bar2'],
                'server_options': ['baz1', 'baz2'],
            },
        }

        self.assertEqual(expected, result)


class RelationHelpersTest(TestCase):

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

    @patch('subprocess.check_call')
    def test_sets_a_relation(self, check_call):
        hooks.relation_set('some-id', foo='bar')

        check_call.assert_called_with(['relation-set', '-r', 'some-id',
                                       'foo=bar'])

    @patch('subprocess.check_call')
    def test_sets_a_relation_with_default_id(self, check_call):
        hooks.relation_set(foo='bar')

        check_call.assert_called_with(['relation-set', 'foo=bar'])

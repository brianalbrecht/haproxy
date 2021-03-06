"Interactions with the Juju environment"
# Copyright 2013 Canonical Ltd.
#
# Authors:
#  Charm Helpers Developers <juju@lists.ubuntu.com>

import os
import json
import yaml
import subprocess
import UserDict

CRITICAL = "CRITICAL"
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"
DEBUG = "DEBUG"
MARKER = object()

cache = {}


def cached(func):
    ''' Cache return values for multiple executions of func + args

    For example:

        @cached
        def unit_get(attribute):
            pass

        unit_get('test')

    will cache the result of unit_get + 'test' for future calls.
    '''
    def wrapper(*args, **kwargs):
        global cache
        key = str((func, args, kwargs))
        try:
            return cache[key]
        except KeyError:
            res = func(*args, **kwargs)
            cache[key] = res
            return res
    return wrapper


def flush(key):
    ''' Flushes any entries from function cache where the
    key is found in the function+args '''
    flush_list = []
    for item in cache:
        if key in item:
            flush_list.append(item)
    for item in flush_list:
        del cache[item]


def log(message, level=None):
    "Write a message to the juju log"
    command = ['juju-log']
    if level:
        command += ['-l', level]
    command += [message]
    subprocess.call(command)


class Serializable(UserDict.IterableUserDict):
    "Wrapper, an object that can be serialized to yaml or json"

    def __init__(self, obj):
        # wrap the object
        UserDict.IterableUserDict.__init__(self)
        self.data = obj

    def __getattr__(self, attr):
        # See if this object has attribute.
        if attr in ("json", "yaml", "data"):
            return self.__dict__[attr]
        # Check for attribute in wrapped object.
        got = getattr(self.data, attr, MARKER)
        if got is not MARKER:
            return got
        # Proxy to the wrapped object via dict interface.
        try:
            return self.data[attr]
        except KeyError:
            raise AttributeError(attr)

    def __getstate__(self):
        # Pickle as a standard dictionary.
        return self.data

    def __setstate__(self, state):
        # Unpickle into our wrapper.
        self.data = state

    def json(self):
        "Serialize the object to json"
        return json.dumps(self.data)

    def yaml(self):
        "Serialize the object to yaml"
        return yaml.dump(self.data)


def execution_environment():
    """A convenient bundling of the current execution context"""
    context = {}
    context['conf'] = config()
    if relation_id():
        context['reltype'] = relation_type()
        context['relid'] = relation_id()
        context['rel'] = relation_get()
    context['unit'] = local_unit()
    context['rels'] = relations()
    context['env'] = os.environ
    return context


def in_relation_hook():
    "Determine whether we're running in a relation hook"
    return 'JUJU_RELATION' in os.environ


def relation_type():
    "The scope for the current relation hook"
    return os.environ.get('JUJU_RELATION', None)


def relation_id():
    "The relation ID for the current relation hook"
    return os.environ.get('JUJU_RELATION_ID', None)


def local_unit():
    "Local unit ID"
    return os.environ['JUJU_UNIT_NAME']


def remote_unit():
    "The remote unit for the current relation hook"
    return os.environ['JUJU_REMOTE_UNIT']


def service_name():
    "The name service group this unit belongs to"
    return local_unit().split('/')[0]


@cached
def config(scope=None):
    "Juju charm configuration"
    config_cmd_line = ['config-get']
    if scope is not None:
        config_cmd_line.append(scope)
    config_cmd_line.append('--format=json')
    try:
        return json.loads(subprocess.check_output(config_cmd_line))
    except ValueError:
        return None


@cached
def relation_get(attribute=None, unit=None, rid=None):
    _args = ['relation-get', '--format=json']
    if rid:
        _args.append('-r')
        _args.append(rid)
    _args.append(attribute or '-')
    if unit:
        _args.append(unit)
    try:
        return json.loads(subprocess.check_output(_args))
    except ValueError:
        return None


def relation_set(relation_id=None, relation_settings={}, **kwargs):
    relation_cmd_line = ['relation-set']
    if relation_id is not None:
        relation_cmd_line.extend(('-r', relation_id))
    for k, v in (relation_settings.items() + kwargs.items()):
        if v is None:
            relation_cmd_line.append('{}='.format(k))
        else:
            relation_cmd_line.append('{}={}'.format(k, v))
    subprocess.check_call(relation_cmd_line)
    # Flush cache of any relation-gets for local unit
    flush(local_unit())


@cached
def relation_ids(reltype=None):
    "A list of relation_ids"
    reltype = reltype or relation_type()
    relid_cmd_line = ['relation-ids', '--format=json']
    if reltype is not None:
        relid_cmd_line.append(reltype)
        return json.loads(subprocess.check_output(relid_cmd_line)) or []
    return []


@cached
def related_units(relid=None):
    "A list of related units"
    relid = relid or relation_id()
    units_cmd_line = ['relation-list', '--format=json']
    if relid is not None:
        units_cmd_line.extend(('-r', relid))
    return json.loads(subprocess.check_output(units_cmd_line)) or []


@cached
def relation_for_unit(unit=None, rid=None):
    "Get the json represenation of a unit's relation"
    unit = unit or remote_unit()
    relation = relation_get(unit=unit, rid=rid)
    for key in relation:
        if key.endswith('-list'):
            relation[key] = relation[key].split()
    relation['__unit__'] = unit
    return relation


@cached
def relations_for_id(relid=None):
    "Get relations of a specific relation ID"
    relation_data = []
    relid = relid or relation_ids()
    for unit in related_units(relid):
        unit_data = relation_for_unit(unit, relid)
        unit_data['__relid__'] = relid
        relation_data.append(unit_data)
    return relation_data


@cached
def relations_of_type(reltype=None):
    "Get relations of a specific type"
    relation_data = []
    reltype = reltype or relation_type()
    for relid in relation_ids(reltype):
        for relation in relations_for_id(relid):
            relation['__relid__'] = relid
            relation_data.append(relation)
    return relation_data


@cached
def relation_types():
    "Get a list of relation types supported by this charm"
    charmdir = os.environ.get('CHARM_DIR', '')
    mdf = open(os.path.join(charmdir, 'metadata.yaml'))
    md = yaml.safe_load(mdf)
    rel_types = []
    for key in ('provides', 'requires', 'peers'):
        section = md.get(key)
        if section:
            rel_types.extend(section.keys())
    mdf.close()
    return rel_types


@cached
def relations():
    rels = {}
    for reltype in relation_types():
        relids = {}
        for relid in relation_ids(reltype):
            units = {local_unit(): relation_get(unit=local_unit(), rid=relid)}
            for unit in related_units(relid):
                reldata = relation_get(unit=unit, rid=relid)
                units[unit] = reldata
            relids[relid] = units
        rels[reltype] = relids
    return rels


def open_port(port, protocol="TCP"):
    "Open a service network port"
    _args = ['open-port']
    _args.append('{}/{}'.format(port, protocol))
    subprocess.check_call(_args)


def close_port(port, protocol="TCP"):
    "Close a service network port"
    _args = ['close-port']
    _args.append('{}/{}'.format(port, protocol))
    subprocess.check_call(_args)


@cached
def unit_get(attribute):
    _args = ['unit-get', '--format=json', attribute]
    try:
        return json.loads(subprocess.check_output(_args))
    except ValueError:
        return None


def unit_private_ip():
    return unit_get('private-address')


class UnregisteredHookError(Exception):
    pass


class Hooks(object):
    def __init__(self):
        super(Hooks, self).__init__()
        self._hooks = {}

    def register(self, name, function):
        self._hooks[name] = function

    def execute(self, args):
        hook_name = os.path.basename(args[0])
        if hook_name in self._hooks:
            self._hooks[hook_name]()
        else:
            raise UnregisteredHookError(hook_name)

    def hook(self, *hook_names):
        def wrapper(decorated):
            for hook_name in hook_names:
                self.register(hook_name, decorated)
            else:
                self.register(decorated.__name__, decorated)
                if '_' in decorated.__name__:
                    self.register(
                        decorated.__name__.replace('_', '-'), decorated)
            return decorated
        return wrapper


def charm_dir():
    return os.environ.get('CHARM_DIR')

#!/usr/bin/env python3
"""Checks an OpenAPI 3.x spec for the API Gateway problems in this skill.

The script checks only the API Gateway rules that the skill describes. It does
not check general OpenAPI validity, such as a $ref to a schema that does not
exist. A PASS does not mean that API Gateway accepts the spec.
"gcloud api-gateway api-configs create" is the final check.

Errors are rules that make API Gateway reject the API config. An x-google-quota
at the root or path level is also an error: API Gateway accepts it but ignores
it, so no quota applies. Warnings are settings that API Gateway accepts but
applies in a way that the author often does not expect.

The checks cover:
- The OpenAPI version, and the OpenAPI 2.0 extensions and fields that a
  migration leaves, such as x-google-management or a parameter "type".
- x-google-api-management: the fields of each part, the backends, the metrics,
  and the quota limits.
- x-google-backend and x-google-quota: where they are and the names that they
  use, the backend path translation, and the path parameters that the backend
  gets as query parameters.
- Security: the requirement combinations that API Gateway rejects, the
  x-google-auth fields, and the API key schemes that API Gateway ignores.
- The server with x-google-endpoint, path templates, path parameters,
  operationIds, schema type lists, $ref targets, and YAML aliases.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
import dataclasses
import ipaddress
import json
import re
import sys
import types
from typing import Any
from urllib import parse

try:
  import yaml

  _HAS_YAML = True
except ImportError:
  _HAS_YAML = False

_OAS3_RE = re.compile(r'3\.[01]\.\d+')
_HTTP_METHODS = frozenset(
    {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
)
# A path variable, such as {itemId}. A whole path segment must match it.
_PATH_VARIABLE_RE = re.compile(r'\{([^{}]*)\}')
# A custom verb at the end of the last path segment, such as {shelf}:merge.
_CUSTOM_VERB_RE = re.compile(r'(?<=\}):[^/{}]+$')
# The characters that API Gateway removes from an operationId before it
# derives a method name. It keeps letters, digits, and underscores.
_SPECIAL_CHARACTERS_RE = re.compile(r'[^A-Za-z0-9_]')
_MAX_DEADLINE_SECONDS = 3600
_MAX_NON_STREAMING_DEADLINE_SECONDS = 600
_MAX_ALIAS_LINES = 5
_PATH_TRANSLATIONS = frozenset({'APPEND_PATH_TO_ADDRESS', 'CONSTANT_ADDRESS'})
_PROTOCOLS = frozenset({'http/1.1', 'h2'})
_URL_SCHEMES = frozenset({'http', 'https'})
# OpenAPI 2.0 parameter fields. In OpenAPI 3.x, they move into "schema", or
# "style" and "explode" replace them.
_V2_PARAMETER_FIELDS = frozenset(
    {'collectionFormat', 'format', 'items', 'type'}
)
# OpenAPI 2.0 root extensions that API Gateway rejects in OpenAPI 3.x, and the
# change to make for each.
_V2_ROOT_EXTENSIONS = types.MappingProxyType({
    'x-google-management': (
        'Move the metrics and limits into x-google-api-management as maps.'
    ),
    'x-google-endpoints': (
        'Move the settings to one servers entry with x-google-endpoint.'
    ),
    'x-google-api-name': 'Move the value to x-google-api-management.apiName.',
    'x-google-allow': 'Remove it, and list every path that clients call.',
    'x-google-deprecated': 'Remove it.',
    'x-google-experimental-authorization': 'Remove it.',
    'x-security': 'Use the OpenAPI "security" field.',
})
# OpenAPI 2.0 backend extensions. API Gateway rejects them on a path item or an
# operation in OpenAPI 3.x, and it ignores them at the root.
_V2_BACKEND_EXTENSIONS = types.MappingProxyType({
    'x-google-backend-url': (
        'Define a backend in x-google-api-management.backends, and set'
        ' x-google-backend to its name.'
    ),
    'x-google-backend-deadline': (
        'Set "deadline" on the backend in x-google-api-management.backends.'
    ),
})
# OpenAPI 2.0 security scheme extensions, and the x-google-auth field of each.
_V2_AUTH_EXTENSIONS = types.MappingProxyType({
    'x-google-issuer': 'issuer',
    'x-issuer': 'issuer',
    'x-google-jwks_uri': 'jwksUri',
    'x-jwks_uri': 'jwksUri',
    'x-google-audiences': 'audiences',
    'x-google-jwt-locations': 'jwtLocations',
})
# The OpenAPI 2.0 field names of a backend, and the OpenAPI 3.x name of each.
_SNAKE_CASE_BACKEND_FIELDS = types.MappingProxyType({
    'jwt_audience': 'jwtAudience',
    'disable_auth': 'disableAuth',
    'path_translation': 'pathTranslation',
})
# The fields that API Gateway accepts in each Google extension object. It
# reads each object strictly, so another field makes the API config fail.
_MANAGEMENT_FIELDS = frozenset({
    'ai',
    'apiName',
    'api_name',
    'backends',
    'mcp',
    'metrics',
    'modelRouter',
    'model_router',
    'quota',
})
_BACKEND_FIELDS = frozenset(
    {'address', 'deadline', 'protocol'}
    | set(_SNAKE_CASE_BACKEND_FIELDS)
    | set(_SNAKE_CASE_BACKEND_FIELDS.values())
)
_METRIC_FIELDS = frozenset({'displayName', 'display_name'})
_QUOTA_FIELDS = frozenset({'limits'})
_LIMIT_FIELDS = frozenset({'metric', 'values'})
_ENDPOINT_FIELDS = frozenset({'allowCors', 'allow_cors', 'target'})
_AUTH_FIELDS = frozenset({
    'audiences',
    'issuer',
    'jwksUri',
    'jwks_uri',
    'jwtLocations',
    'jwt_locations',
})
# The API key forms that API Gateway reads, as (location, lowercase name).
_API_KEY_FORMS = frozenset(
    {('query', 'key'), ('query', 'api_key'), ('header', 'x-api-key')}
)
# Keys whose values are data, not schemas, such as examples. The walk over the
# spec skips them, and it also skips vendor extensions (x-*).
_DATA_KEYS = frozenset({'const', 'default', 'enum', 'example', 'examples'})
# Maps whose keys are names that the author chooses. The walk skips no key in
# them, because a property or a response can have the name "default".
_NAMED_MAPS = frozenset({'properties', 'responses', 'schemas'})
# The part of API Gateway that reports an error. The OpenAPI importer reads the
# spec. The control plane checks the API config after the importer.
_IMPORTER = 'importer'
_CONTROL_PLANE = 'control plane'
# The error is a setting that API Gateway accepts but ignores.
_IGNORED = 'ignored'
_NOTE = (
    'This script checks only the API Gateway rules in this skill. It does not'
    ' check general OpenAPI validity. A PASS does not mean that API Gateway'
    ' accepts the spec. Run "gcloud api-gateway api-configs create" to'
    ' confirm.'
)


@dataclasses.dataclass
class _Validation:
  """The spec, the results, and the values that the checks share."""

  spec: dict[str, Any]
  errors: list[str] = dataclasses.field(default_factory=list)
  # The part of API Gateway that reports each error, in the order of errors.
  error_sources: list[str] = dataclasses.field(default_factory=list)
  warnings: list[str] = dataclasses.field(default_factory=list)
  base_path: str = ''
  backends: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
  path_translations: dict[str, str] = dataclasses.field(default_factory=dict)
  metric_names: set[str] = dataclasses.field(default_factory=set)
  limited_metrics: set[str] = dataclasses.field(default_factory=set)
  charged_metrics: set[str] = dataclasses.field(default_factory=set)
  schemes: dict[str, Any] = dataclasses.field(default_factory=dict)
  api_key_schemes: set[str] = dataclasses.field(default_factory=set)
  method_names: dict[str, str] = dataclasses.field(default_factory=dict)
  root_backend: str | None = None
  operation_backends: set[str] = dataclasses.field(default_factory=set)
  router_backends: set[str] = dataclasses.field(default_factory=set)
  query_operations: list[str] = dataclasses.field(default_factory=list)
  operation_count: int = 0

  def error(self, message: str, source: str = _IMPORTER) -> None:
    """Adds an error, and the part of API Gateway that reports it."""
    self.errors.append(message)
    self.error_sources.append(source)


def _load_spec(path: str) -> tuple[dict[str, Any], list[int]]:
  """Reads the spec file at path as JSON or YAML.

  Args:
    path: The path of the OpenAPI spec file.

  Returns:
    The parsed spec, and the line numbers of the YAML aliases to mappings.

  Raises:
    OSError: The file cannot be read.
    RuntimeError: The file is not JSON, and PyYAML is not installed.
    ValueError: The file is not a JSON or YAML mapping.
  """
  with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
  try:
    data = json.loads(content)
  except json.JSONDecodeError:
    pass
  else:
    if isinstance(data, dict):
      return data, []
  if not _HAS_YAML:
    raise RuntimeError(
        'PyYAML is required to parse YAML files. Install with: '
        'pip install "PyYAML>=6.0,<7.0". A JSON spec does not need PyYAML.'
    )
  # The C loader is much faster on a large spec. Both loaders are safe.
  loader_class = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
  try:
    data = yaml.load(content, Loader=loader_class)
    alias_lines = _mapping_alias_lines(content, loader_class)
  except yaml.YAMLError as exc:
    raise ValueError(f'{path} is not valid JSON or YAML: {exc}') from exc
  if not isinstance(data, dict):
    raise ValueError(f'{path} did not parse as a YAML/JSON mapping.')
  return data, alias_lines


def _mapping_alias_lines(content: str, loader_class: Any) -> list[int]:
  """Returns the line numbers of the YAML aliases to mappings in content."""
  if '*' not in content:
    return []
  is_mapping: dict[str, bool] = {}
  lines = []
  for event in yaml.parse(content, Loader=loader_class):
    if isinstance(event, yaml.AliasEvent):
      if is_mapping.get(event.anchor):
        lines.append(event.start_mark.line + 1)
    elif isinstance(event, yaml.NodeEvent) and event.anchor:
      is_mapping[event.anchor] = isinstance(event, yaml.MappingStartEvent)
  return lines


def _escape_pointer(key: str) -> str:
  """Escapes a mapping key for use in a JSON pointer."""
  return key.replace('~', '~0').replace('/', '~1')


def _is_data_key(key: str) -> bool:
  """Returns whether the value of key is data or a vendor extension."""
  return key in _DATA_KEYS or key.startswith('x-')


def _walk(node: Any) -> Iterator[tuple[str, dict[Any, Any]]]:
  """Yields the JSON pointer and the value of each mapping in node.

  The walk skips data values, such as examples, and vendor extensions. It
  visits each mapping and list one time, so YAML aliases cannot make it slow,
  and a recursive alias cannot make it loop.

  Args:
    node: A part of the OpenAPI spec.

  Yields:
    The JSON pointer and the value of each mapping.
  """
  seen: set[int] = set()
  stack: list[tuple[str, str, Any]] = [('', '', node)]
  while stack:
    location, container_key, current = stack.pop()
    if not isinstance(current, (dict, list)) or id(current) in seen:
      continue
    seen.add(id(current))
    if isinstance(current, list):
      children = [(str(index), item) for index, item in enumerate(current)]
    else:
      yield location or '/', current
      children = [
          (str(key), value)
          for key, value in current.items()
          if container_key in _NAMED_MAPS or not _is_data_key(str(key))
      ]
    for key, value in reversed(children):
      stack.append((f'{location}/{_escape_pointer(key)}', key, value))


def _resolve(spec: dict[str, Any], obj: Any) -> Any:
  """Follows local '#/...' $ref pointers. Returns obj if it cannot resolve."""
  seen: set[str] = set()
  while isinstance(obj, dict) and isinstance(obj.get('$ref'), str):
    reference = obj['$ref']
    if not reference.startswith('#/') or reference in seen:
      return obj
    seen.add(reference)
    target: Any = spec
    for part in reference[2:].split('/'):
      part = part.replace('~1', '/').replace('~0', '~')
      if not isinstance(target, dict) or part not in target:
        return obj
      target = target[part]
    obj = target
  return obj


def _as_number(value: Any) -> float | None:
  """Returns value as a number, or None if it is not a number."""
  if isinstance(value, bool):
    return None
  if isinstance(value, (int, float)):
    return float(value)
  if isinstance(value, str):
    try:
      return float(value)
    except ValueError:
      return None
  return None


def _as_integer(value: Any) -> int | None:
  """Returns value as an integer, or None if it is not an integer.

  API Gateway reads the protobuf JSON format. It also accepts an integral
  number, such as 100.0, and a number in a string, such as "100".

  Args:
    value: A value from the spec.

  Returns:
    The integer, or None.
  """
  if isinstance(value, int) and not isinstance(value, bool):
    return value
  number = _as_number(value)
  if number is None or not number.is_integer():
    return None
  return int(number)


def _method_name(operation_id: str) -> str:
  """Returns the method name that API Gateway derives from an operationId.

  API Gateway removes the characters other than letters, digits, and
  underscores, and then capitalizes the first letter. For example, getItem,
  GetItem, and get-Item all give GetItem.

  Args:
    operation_id: The operationId of an operation.

  Returns:
    The method name.
  """
  cleaned = _SPECIAL_CHARACTERS_RE.sub('', operation_id)
  return cleaned[:1].upper() + cleaned[1:]


def _unknown_fields(
    config: dict[Any, Any], allowed: frozenset[str]
) -> list[str]:
  """Returns the sorted keys of config that are not in allowed."""
  return sorted(str(key) for key in config if str(key) not in allowed)


def _unknown_fields_error(label: str, fields: list[str], hint: str) -> str:
  """Returns the error for fields that x-google-api-management rejects."""
  return (
      f'{label} has the fields {fields}, which OpenAPI 3.x does not support.'
      ' API Gateway then rejects the whole x-google-api-management block, and'
      f' it also reports each backend as not defined. {hint}'
  )


def _field(config: dict[str, Any], name: str, snake_name: str) -> Any:
  """Returns a field by its OpenAPI 3.x name or by its snake_case name."""
  return config[name] if name in config else config.get(snake_name)


def _check_url(
    check: _Validation, url: str, label: str, scheme_source: str
) -> bool:
  """Checks a backend address or a JWKS URI for the common mistakes.

  The control plane rejects more addresses than the script checks.

  Args:
    check: The validation state.
    url: The URL to check.
    label: The location of the URL, for the messages.
    scheme_source: The part of API Gateway that checks the URL scheme.

  Returns:
    Whether the URL passed the checks.
  """
  if '{' in url or '}' in url:
    check.error(
        f'{label} "{url}" has a {{placeholder}}. Replace it with the real'
        ' hostname.',
        _CONTROL_PLANE,
    )
    return False
  parsed = parse.urlparse(url)
  if parsed.scheme.lower() not in _URL_SCHEMES or not parsed.hostname:
    check.error(
        f'{label} must be an HTTP or HTTPS URL with a hostname, got "{url}".',
        scheme_source,
    )
    return False
  host = parsed.hostname.rstrip('.')
  try:
    ipaddress.ip_address(host)
  except ValueError:
    pass
  else:
    check.error(
        f'{label} "{url}" uses an IP address. API Gateway routes only to a'
        ' hostname.',
        _CONTROL_PLANE,
    )
    return False
  if '.' not in host:
    check.error(
        f'{label} "{url}" has a hostname with only one part, such as'
        ' localhost. Use a fully qualified hostname.',
        _CONTROL_PLANE,
    )
    return False
  return True


def _requirement_types(
    check: _Validation, requirement: dict[Any, Any], where: str
) -> list[Any]:
  """Returns the scheme types of one security requirement.

  Args:
    check: The validation state. It gets an error for each undefined scheme.
    requirement: One requirement object of a "security" list.
    where: The location of the "security" list, for the error messages.

  Returns:
    The type of each defined scheme in the requirement.
  """
  scheme_types = []
  for raw_name in requirement:
    scheme = check.schemes.get(str(raw_name))
    if isinstance(scheme, dict):
      scheme_types.append(scheme.get('type'))
    else:
      check.error(
          f'The "security" list of {where} names the security scheme'
          f' "{raw_name}", which components.securitySchemes does not define.'
          ' API Gateway rejects the API config.'
      )
  return scheme_types


def _check_security_list(check: _Validation, security: Any, where: str) -> None:
  """Checks a security list against the API Gateway rules.

  Args:
    check: The validation state.
    security: The value of a "security" list.
    where: The location of the "security" list, for the error messages.
  """
  if not isinstance(security, list):
    return
  requirements = [
      _requirement_types(check, requirement, where)
      for requirement in security
      if isinstance(requirement, dict) and requirement
  ]
  if any(scheme_types.count('oauth2') > 1 for scheme_types in requirements):
    check.error(
        f'The "security" list of {where} puts two JWT (oauth2) schemes in one'
        ' requirement object (AND). API Gateway rejects it. Put each JWT'
        ' scheme in its own requirement object (OR).'
    )
  has_empty = any(
      isinstance(requirement, dict) and not requirement
      for requirement in security
  )
  if has_empty:
    if any('oauth2' in scheme_types for scheme_types in requirements):
      check.error(
          f'The "security" list of {where} has an empty requirement ({{}})'
          ' that makes a JWT (oauth2) scheme optional. API Gateway supports'
          ' optional security only for API keys.'
      )
    return
  with_key = ['apiKey' in scheme_types for scheme_types in requirements]
  if any(with_key) and not all(with_key):
    check.error(
        f'The "security" list of {where} has alternative (OR) requirements,'
        ' and only some of them have an API key scheme. API Gateway supports'
        ' an OR only if every alternative has an API key scheme, or none of'
        ' them has one.'
    )


def _requires_api_key(security: Any, api_key_schemes: set[str]) -> bool:
  """Returns whether every alternative of a security list has an API key."""
  if not isinstance(security, list) or not security:
    return False
  return all(
      isinstance(requirement, dict)
      and any(str(name) in api_key_schemes for name in requirement)
      for requirement in security
  )


def _path_variables(path: str) -> list[str]:
  """Returns the variables of a path template, such as itemId or name=**."""
  return [match.group(1) for match in _PATH_VARIABLE_RE.finditer(path)]


def _check_path_template(check: _Validation, path: str) -> None:
  """Checks that each path variable is a whole segment in the 3.x syntax."""
  segments = path.split('/')
  segments[-1] = _CUSTOM_VERB_RE.sub('', segments[-1])
  for segment in segments:
    if ('{' in segment or '}' in segment) and not _PATH_VARIABLE_RE.fullmatch(
        segment
    ):
      check.error(
          f'Path "{path}" has the segment "{segment}". A path variable must'
          ' be a whole segment, such as /items/{itemId}. API Gateway rejects'
          ' a partial segment, such as /items/prefix_{id}.'
      )
  for variable in _path_variables(path):
    if '=' in variable:
      check.error(
          f'Path "{path}" uses "{{{variable}}}". OpenAPI 3.x does not support'
          ' the {var=*} or {var=**} syntax. Write {var}, and for a double'
          ' wildcard, set x-google-parameter: {pattern: "**"} on the'
          ' parameter.'
      )


def _check_structure(check: _Validation) -> None:
  """Checks that the main parts of the spec have the right JSON types.

  A part with the wrong type gets one error, and the other checks skip it.

  Args:
    check: The validation state.
  """
  spec = check.spec
  parts = (
      ('paths', spec.get('paths'), dict),
      ('servers', spec.get('servers'), list),
      ('components', spec.get('components'), dict),
  )
  for name, value, expected in parts:
    if name in spec and not isinstance(value, expected):
      kind = 'a mapping' if expected is dict else 'a list'
      check.error(f'"{name}" must be {kind}. API Gateway rejects the spec.')
  components = spec.get('components')
  if isinstance(components, dict) and 'securitySchemes' in components:
    if not isinstance(components['securitySchemes'], dict):
      check.error(
          '"components.securitySchemes" must be a map from each scheme name'
          ' to the scheme. API Gateway rejects the spec.'
      )


def _check_version_and_root_extensions(check: _Validation) -> None:
  """Checks the openapi version and the extensions at the root."""
  version = str(check.spec.get('openapi', ''))
  if not _OAS3_RE.fullmatch(version):
    check.error(
        'Expected openapi version 3.0.x or 3.1.x (for example, 3.0.4 or'
        f' 3.1.0), got "{version}".'
    )
  for extension, change in _V2_ROOT_EXTENSIONS.items():
    if extension in check.spec:
      check.error(
          f'Found the OpenAPI 2.0 extension "{extension}" at the root. API'
          f' Gateway rejects it in OpenAPI 3.x. {change}'
      )
  for extension, change in _V2_BACKEND_EXTENSIONS.items():
    if extension in check.spec:
      check.warnings.append(
          f'Found the OpenAPI 2.0 extension "{extension}" at the root. API'
          f' Gateway ignores it there in OpenAPI 3.x. {change}'
      )
  if 'x-google-quota' in check.spec:
    check.error(
        'Found x-google-quota at the root. API Gateway accepts it in OpenAPI'
        ' 3.x, but ignores it, so no quota applies. Set x-google-quota on'
        ' each operation.',
        _IGNORED,
    )


def _check_schemas_and_refs(check: _Validation, alias_lines: list[int]) -> None:
  """Checks schema type lists, $ref values, and YAML aliases."""
  for location, node in _walk(check.spec):
    node_type = node.get('type')
    if isinstance(node_type, list) and len(node_type) > 1:
      check.error(
          f'The schema at {location} has more than one type'
          f' ({json.dumps(node_type)}). API Gateway rejects a type list. Give'
          ' the schema one type.'
      )
    reference = node.get('$ref')
    if isinstance(reference, str):
      _check_ref(check, location, reference)
  if alias_lines:
    lines = ', '.join(str(line) for line in alias_lines[:_MAX_ALIAS_LINES])
    more = ', and more' if len(alias_lines) > _MAX_ALIAS_LINES else ''
    check.error(
        f'Found {len(alias_lines)} YAML alias(es) to a mapping, at lines'
        f' {lines}{more}. API Gateway rejects an alias to a mapping with'
        ' "string found, object expected", and the error does not name the'
        ' alias. Use a $ref, or copy the mapping. If a program writes the'
        ' YAML, turn off aliases, for example with a PyYAML Dumper whose'
        ' ignore_aliases() returns True.'
    )


def _check_ref(check: _Validation, location: str, reference: str) -> None:
  """Checks one $ref value."""
  if reference.startswith('#/definitions/'):
    check.error(
        f'The $ref "{reference}" at {location} uses the OpenAPI 2.0 path'
        ' #/definitions/. Move the schema to components.schemas, and use'
        ' #/components/schemas/{name}.'
    )
    return
  if reference.startswith('#'):
    return
  parsed = parse.urlparse(reference)
  if parsed.scheme or parsed.netloc:
    check.error(
        f'The $ref "{reference}" at {location} points to a URL. API Gateway'
        ' accepts only local references. Copy the schema into'
        ' components.schemas.'
    )
  else:
    check.warnings.append(
        f'The $ref "{reference}" at {location} points to another file.'
        ' Prefer a local #/components/schemas reference. If you keep it,'
        ' upload that file in the same --openapi-spec list.'
    )


def _check_servers(check: _Validation) -> None:
  """Checks the servers list, and records the base path."""
  servers = check.spec.get('servers')
  if not isinstance(servers, list) or not servers:
    return
  if not all(isinstance(server, dict) for server in servers):
    check.error(
        'Each "servers" entry must be a mapping with a "url". API Gateway'
        ' rejects the spec.'
    )
    return
  endpoint_servers = [
      server for server in servers if 'x-google-endpoint' in server
  ]
  if not endpoint_servers:
    check.warnings.append(
        'No servers entry has x-google-endpoint, so API Gateway ignores'
        ' "servers" and applies no base path. Add "x-google-endpoint: {}" to'
        ' the server whose URL path is the base path.'
    )
    return
  if len(endpoint_servers) > 1:
    check.error(
        f'Found {len(endpoint_servers)} servers with "x-google-endpoint". API'
        ' Gateway permits at most one.'
    )
  server = endpoint_servers[0]
  if 'url' in server:
    check.base_path = _server_base_path(check, server['url'])
  endpoint = server.get('x-google-endpoint')
  if endpoint is None:
    return
  if not isinstance(endpoint, dict):
    check.error(
        'x-google-endpoint must be a mapping, such as {} or {allowCors:'
        ' true}. API Gateway rejects another value.'
    )
    return
  unknown = _unknown_fields(endpoint, _ENDPOINT_FIELDS)
  if unknown:
    check.error(
        f'x-google-endpoint has the fields {unknown}. API Gateway rejects the'
        ' API config. In OpenAPI 3.x, x-google-endpoint has only allowCors'
        ' and target. Remove the other fields, such as the OpenAPI 2.0'
        ' "name".'
    )
  if _field(endpoint, 'allowCors', 'allow_cors'):
    check.warnings.append(
        'x-google-endpoint sets allowCors: true. API Gateway then passes CORS'
        ' requests, including OPTIONS preflight requests, to the backend. It'
        ' does not add CORS headers, so the backend must answer them.'
    )


def _server_base_path(check: _Validation, url: Any) -> str:
  """Checks the URL of the server with x-google-endpoint.

  Args:
    check: The validation state.
    url: The value of the "url" field of the server.

  Returns:
    The base path that the URL gives, without a trailing "/".
  """
  if not isinstance(url, str):
    check.error(
        'The server with x-google-endpoint has a null url. Set it to a base'
        ' path, such as /v1, or to an HTTPS URL.'
    )
    return ''
  if '{' in url or '}' in url or any(char.isspace() for char in url):
    check.error(
        f'The server url "{url}" has a {{variable}} or a space. API Gateway'
        ' does not support server variables. Replace each {placeholder} with'
        ' its value.'
    )
    return ''
  if not url or url.startswith('/'):
    return url.rstrip('/')
  parsed = parse.urlparse(url)
  if parsed.scheme.lower() not in _URL_SCHEMES or not parsed.hostname:
    check.error(
        f'The server url "{url}" must be an HTTPS URL or a relative path'
        ' that starts with "/", such as /v1.'
    )
    return ''
  try:
    port = parsed.port
  except ValueError:
    port = -1
  if port is not None:
    check.error(
        f'The server url "{url}" has a custom port. API Gateway does not'
        ' support custom ports.'
    )
    return ''
  return parsed.path.rstrip('/')


def _check_management(check: _Validation) -> None:
  """Checks the root x-google-api-management extension."""
  if 'x-google-api-management' not in check.spec:
    check.error(
        'Missing the required root "x-google-api-management" mapping with'
        ' "backends".',
        _CONTROL_PLANE,
    )
    return
  management = check.spec['x-google-api-management']
  if not isinstance(management, dict):
    check.error('x-google-api-management must be a mapping.')
    return
  unknown = _unknown_fields(management, _MANAGEMENT_FIELDS)
  if unknown:
    check.error(
        _unknown_fields_error(
            'x-google-api-management',
            unknown,
            'Use backends, metrics, quota, apiName, mcp, ai, or modelRouter.',
        )
    )
  _check_backends(check, management.get('backends'))
  _check_metrics(check, management.get('metrics'))
  _check_limits(check, management.get('quota'))
  check.router_backends = _router_backends(management.get('ai'))
  if 'mcp' in management:
    check.warnings.append(
        'x-google-api-management.mcp enables MCP tools. MCP has more rules.'
        ' Check them with the api-gateway-mcp-server skill.'
    )


def _router_backends(ai: Any) -> set[str]:
  """Returns the backend names that the model routers in ai use.

  Args:
    ai: The value of x-google-api-management.ai.

  Returns:
    The value of each "backend" field in ai.
  """
  names: set[str] = set()
  seen: set[int] = set()
  stack = [ai]
  while stack:
    node = stack.pop()
    if not isinstance(node, (dict, list)) or id(node) in seen:
      continue
    seen.add(id(node))
    if isinstance(node, list):
      stack.extend(node)
      continue
    if isinstance(node.get('backend'), str):
      names.add(node['backend'])
    stack.extend(node.values())
  return names


def _check_backends(check: _Validation, backends: Any) -> None:
  """Checks x-google-api-management.backends, and records the valid ones."""
  if not backends:
    check.error(
        '"x-google-api-management.backends" must define at least one named'
        ' backend.',
        _CONTROL_PLANE,
    )
    return
  if not isinstance(backends, dict):
    check.error(
        '"x-google-api-management.backends" must be a map from each backend'
        ' name to its settings, not a list.'
    )
    return
  for raw_name, config in backends.items():
    name = str(raw_name)
    if not isinstance(config, dict):
      check.error(f'Backend "{name}" must be a mapping.')
      continue
    check.backends[name] = config
    _check_backend_fields(check, name, config)
    _check_backend_address(check, name, config)
    _check_backend_settings(check, name, config)


def _check_backend_fields(
    check: _Validation, name: str, config: dict[str, Any]
) -> None:
  """Checks the field names of one backend."""
  unknown = _unknown_fields(config, _BACKEND_FIELDS)
  if unknown:
    check.error(
        _unknown_fields_error(
            f'Backend "{name}"',
            unknown,
            'A backend has only address, jwtAudience, disableAuth,'
            ' pathTranslation, deadline, and protocol.',
        )
    )
  for snake_field, camel_field in _SNAKE_CASE_BACKEND_FIELDS.items():
    if snake_field in config:
      check.warnings.append(
          f'Backend "{name}" uses the OpenAPI 2.0 field name'
          f' "{snake_field}". Use "{camel_field}", as the OpenAPI 3.x'
          ' documentation shows.'
      )
  if (
      _field(config, 'jwtAudience', 'jwt_audience') is not None
      and _field(config, 'disableAuth', 'disable_auth') is not None
  ):
    check.error(
        f'Backend "{name}" sets both jwtAudience and disableAuth. API Gateway'
        ' rejects the API config. Set only one of them.'
    )


def _check_backend_address(
    check: _Validation, name: str, config: dict[str, Any]
) -> None:
  """Checks the address of one backend, and the settings that use it."""
  address = config.get('address')
  if not isinstance(address, str) or not address:
    check.error(
        f'Backend "{name}" is missing a required "address".', _CONTROL_PLANE
    )
    return
  parsed = parse.urlparse(address)
  protocol = str(config.get('protocol', '')).lower()
  if protocol == 'h2' and parsed.scheme.lower() == 'http':
    check.error(
        f'Backend "{name}" sets protocol "h2" with an http:// address. API'
        ' Gateway allows "h2" only for https:// backends.'
    )
  if not _check_url(
      check, address, f'The address of backend "{name}"', _IMPORTER
  ):
    return
  hostname = parsed.hostname or ''
  if (
      hostname.endswith('.run.app')
      and parsed.path.strip('/')
      and _field(config, 'jwtAudience', 'jwt_audience') is None
      and not _field(config, 'disableAuth', 'disable_auth')
  ):
    check.warnings.append(
        f'Backend "{name}" has a path in its Cloud Run address and no'
        ' jwtAudience. The default audience is the full address, but Cloud'
        ' Run expects its service URL. Set jwtAudience to'
        f' "{parsed.scheme}://{hostname}".'
    )


def _check_backend_settings(
    check: _Validation, name: str, config: dict[str, Any]
) -> None:
  """Checks the pathTranslation, protocol, and deadline of one backend."""
  path_translation = _field(config, 'pathTranslation', 'path_translation')
  if (
      path_translation is not None
      and path_translation not in _PATH_TRANSLATIONS
  ):
    check.error(
        f'Backend "{name}" has pathTranslation "{path_translation}". Use'
        ' APPEND_PATH_TO_ADDRESS or CONSTANT_ADDRESS.'
    )
  protocol = config.get('protocol')
  if protocol is not None and str(protocol).lower() not in _PROTOCOLS:
    check.error(
        f'Backend "{name}" has protocol "{protocol}". Use "http/1.1" or "h2".'
    )
  if 'deadline' not in config:
    return
  deadline = _as_number(config['deadline'])
  if deadline is None:
    check.error(f'Backend "{name}" deadline must be a number.')
  elif deadline > _MAX_DEADLINE_SECONDS:
    check.error(
        f'Backend "{name}" deadline is {deadline:g} seconds. The maximum is'
        f' {_MAX_DEADLINE_SECONDS}.',
        _CONTROL_PLANE,
    )
  elif deadline > _MAX_NON_STREAMING_DEADLINE_SECONDS:
    check.warnings.append(
        f'Backend "{name}" deadline is {deadline:g} seconds. Some gateways'
        f' reject a value above {_MAX_NON_STREAMING_DEADLINE_SECONDS} when you'
        ' create or update the gateway. A streaming gateway accepts up to'
        f' {_MAX_DEADLINE_SECONDS}.'
    )


def _check_metrics(check: _Validation, metrics: Any) -> None:
  """Checks x-google-api-management.metrics, and records the metric names."""
  if metrics is None:
    return
  if not isinstance(metrics, dict):
    check.error(
        '"x-google-api-management.metrics" must be a map from each metric'
        ' name to its settings, such as {read-requests: {displayName: "Read'
        ' requests"}}, not a list (the OpenAPI 2.0 form).'
    )
    return
  for raw_name, config in metrics.items():
    name = str(raw_name)
    check.metric_names.add(name)
    if config is None:
      continue
    if not isinstance(config, dict):
      check.error(f'Metric "{name}" must be a mapping.')
      continue
    unknown = _unknown_fields(config, _METRIC_FIELDS)
    if unknown:
      check.error(
          _unknown_fields_error(
              f'Metric "{name}"',
              unknown,
              'A metric has only displayName. The map key is the metric'
              ' name, and API Gateway sets the value type and the kind.',
          )
      )


def _check_limits(check: _Validation, quota: Any) -> None:
  """Checks x-google-api-management.quota.limits."""
  if quota is None:
    return
  if not isinstance(quota, dict):
    check.error('"x-google-api-management.quota" must be a mapping.')
    return
  unknown = _unknown_fields(quota, _QUOTA_FIELDS)
  if unknown:
    check.error(
        _unknown_fields_error(
            'x-google-api-management.quota', unknown, 'Use only "limits".'
        )
    )
  limits = quota.get('limits')
  if limits is None:
    return
  if not isinstance(limits, dict):
    check.error(
        '"x-google-api-management.quota.limits" must be a map from each limit'
        ' name to {metric, values}, not a list (the OpenAPI 2.0 form).'
    )
    return
  for raw_name, limit in limits.items():
    _check_limit(check, str(raw_name), limit)


def _check_limit(check: _Validation, name: str, limit: Any) -> None:
  """Checks one quota limit, and records the metric that it limits."""
  if not isinstance(limit, dict):
    check.error(f'Quota limit "{name}" must be a mapping.')
    return
  unknown = _unknown_fields(limit, _LIMIT_FIELDS)
  if unknown:
    check.error(
        _unknown_fields_error(
            f'Quota limit "{name}"',
            unknown,
            'A quota limit has only metric and values. API Gateway uses the'
            ' unit 1/min/{project}.',
        )
    )
  metric = str(limit.get('metric'))
  if metric in check.metric_names:
    check.limited_metrics.add(metric)
  else:
    check.error(
        f'Quota limit "{name}" names the metric "{metric}", which'
        ' x-google-api-management.metrics does not define.'
    )
  values = limit.get('values')
  if isinstance(values, dict):
    check.error(
        f'Quota limit "{name}" sets values as a map {values}. In OpenAPI 3.x,'
        ' values is a plain integer, such as "values: 100".'
    )
  elif _as_integer(values) is None:
    check.error(f'Quota limit "{name}" must set values to an integer.')


def _check_security(check: _Validation) -> None:
  """Checks the security schemes and the root security list."""
  components = check.spec.get('components')
  schemes = (
      components.get('securitySchemes')
      if isinstance(components, dict)
      else None
  )
  check.schemes = schemes if isinstance(schemes, dict) else {}
  for raw_name, scheme in check.schemes.items():
    name = str(raw_name)
    if not isinstance(scheme, dict):
      check.error(f'Security scheme "{name}" must be a mapping.')
      continue
    for old_extension, new_field in _V2_AUTH_EXTENSIONS.items():
      if old_extension in scheme:
        check.error(
            f'Security scheme "{name}" uses the OpenAPI 2.0 extension'
            f' "{old_extension}". API Gateway rejects it in OpenAPI 3.x. Move'
            f' the value to "x-google-auth.{new_field}".'
        )
    if scheme.get('type') == 'apiKey':
      _check_api_key_scheme(check, name, scheme)
    elif scheme.get('type') == 'oauth2':
      _check_oauth_scheme(check, name, scheme)
  _check_security_list(check, check.spec.get('security'), 'the root')


def _check_api_key_scheme(
    check: _Validation, name: str, scheme: dict[str, Any]
) -> None:
  """Records an API key scheme that API Gateway reads, or warns."""
  location = str(scheme.get('in', ''))
  key_name = str(scheme.get('name', ''))
  if (location.lower(), key_name.lower()) in _API_KEY_FORMS:
    check.api_key_schemes.add(name)
    return
  check.warnings.append(
      f'API key scheme "{name}" uses the name "{key_name}" in "{location}".'
      ' API Gateway ignores this scheme, so an operation that requires only'
      ' this scheme accepts calls without a key. Use x-api-key in a header,'
      ' or key or api_key in the query.'
  )


def _check_oauth_scheme(
    check: _Validation, name: str, scheme: dict[str, Any]
) -> None:
  """Checks the scopes and the x-google-auth extension of a JWT scheme."""
  flows = scheme.get('flows')
  if isinstance(flows, dict) and any(
      isinstance(flow, dict) and flow.get('scopes') for flow in flows.values()
  ):
    check.warnings.append(
        f'Security scheme "{name}" defines OAuth scopes. API Gateway does'
        ' not check scopes. Check them in the backend if you need them.'
    )
  auth = scheme.get('x-google-auth')
  if auth is None:
    if not any(old in scheme for old in _V2_AUTH_EXTENSIONS):
      check.error(
          f'Security scheme "{name}" is oauth2 without x-google-auth. API'
          ' Gateway adds a JWT provider for every oauth2 scheme, also for a'
          ' scheme that no operation uses, and it rejects a provider without'
          ' a JWKS URI. Add x-google-auth with issuer, jwksUri, and'
          ' audiences, or remove the scheme.',
          _CONTROL_PLANE,
      )
    return
  label = f'x-google-auth of security scheme "{name}"'
  if not isinstance(auth, dict):
    check.error(f'{label} must be a mapping.')
    return
  unknown = _unknown_fields(auth, _AUTH_FIELDS)
  if unknown:
    check.error(
        f'{label} has the fields {unknown}. API Gateway rejects the API'
        ' config. x-google-auth has only issuer, jwksUri, audiences, and'
        ' jwtLocations.'
    )
  audiences = auth.get('audiences')
  if audiences is not None and not isinstance(audiences, list):
    check.error(
        f'{label}: audiences must be a list, not a comma-separated string'
        ' (the OpenAPI 2.0 form).'
    )
  jwks_uri = _field(auth, 'jwksUri', 'jwks_uri')
  if not jwks_uri:
    check.error(
        f'{label} has no jwksUri. API Gateway rejects a JWT provider without'
        ' a JWKS URI, also for a scheme that no operation uses. Set jwksUri'
        ' to the URL of the public keys of the issuer.',
        _CONTROL_PLANE,
    )
  elif isinstance(jwks_uri, str):
    _check_url(check, jwks_uri, f'The jwksUri of {label}', _CONTROL_PLANE)


def _check_root_backend(check: _Validation) -> None:
  """Checks the root x-google-backend, and records the backend name."""
  root_backend = check.spec.get('x-google-backend')
  if root_backend is None:
    return
  if isinstance(root_backend, dict):
    check.error(
        'The root "x-google-backend" is an inline object (the OpenAPI 2.0'
        ' form). Define the backend under x-google-api-management.backends,'
        ' and set x-google-backend to its name.'
    )
    return
  check.root_backend = str(root_backend)
  if check.root_backend not in check.backends:
    check.error(
        f'The root x-google-backend "{root_backend}" is not defined in'
        ' x-google-api-management.backends.'
    )


def _check_paths(check: _Validation) -> None:
  """Checks every path item and operation in the spec."""
  paths = check.spec.get('paths')
  if not isinstance(paths, dict):
    return
  for raw_path, path_item in paths.items():
    path = str(raw_path)
    _check_path_template(check, path)
    if not isinstance(path_item, dict):
      check.error(f'Path "{path}" must map to a path item object.')
      continue
    for extension in ('x-google-backend', *_V2_BACKEND_EXTENSIONS):
      if extension in path_item:
        check.error(
            f'Path "{path}" sets {extension} at the path level. API Gateway'
            ' rejects it. Set x-google-backend at the root or on each'
            ' operation.'
        )
    if 'x-google-quota' in path_item:
      check.error(
          f'Path "{path}" sets x-google-quota at the path level. API Gateway'
          ' accepts it, but ignores it, so no quota applies. Set it on each'
          ' operation.',
          _IGNORED,
      )
    for raw_method, operation in path_item.items():
      method = str(raw_method).lower()
      if method not in _HTTP_METHODS:
        continue
      if not isinstance(operation, dict):
        check.error(f'Operation {method.upper()} {path} must be a mapping.')
        continue
      _check_operation(
          check, method, path, operation, path_item.get('parameters')
      )


def _check_operation(
    check: _Validation,
    method: str,
    path: str,
    operation: dict[str, Any],
    path_parameters: Any,
) -> None:
  """Checks one operation of a path item.

  Args:
    check: The validation state.
    method: The lowercase HTTP method of the operation.
    path: The path key of the operation.
    operation: The operation object.
    path_parameters: The "parameters" list of the path item.
  """
  check.operation_count += 1
  label = f'{method.upper()} {path}'
  _check_operation_id(check, label, operation.get('operationId'))
  for extension, change in _V2_BACKEND_EXTENSIONS.items():
    if extension in operation:
      check.error(
          f'Operation {label} uses the OpenAPI 2.0 extension "{extension}".'
          f' API Gateway rejects it in OpenAPI 3.x. {change}'
      )
  if 'x-security' in operation:
    check.error(
        f'Operation {label} uses the OpenAPI 2.0 extension "x-security". API'
        ' Gateway rejects it in OpenAPI 3.x. Use the OpenAPI "security"'
        ' field.'
    )
  if 'security' in operation:
    _check_security_list(check, operation['security'], f'operation {label}')
  _check_operation_quota(check, label, operation)
  # A model router operation has no x-google-backend.
  if 'x-google-model-router' not in operation:
    _check_operation_backend(check, label, path, operation)
  _check_parameters(
      check,
      label,
      path,
      _operation_parameters(check, path_parameters, operation),
  )


def _check_operation_id(check: _Validation, label: str, raw_id: Any) -> None:
  """Checks that an operationId is present and unique."""
  operation_id = str(raw_id or '').strip()
  if not operation_id:
    check.error(
        f'Operation {label} has no operationId. API Gateway rejects every'
        ' operation without one.'
    )
    return
  method_name = _method_name(operation_id)
  other = check.method_names.get(method_name)
  if other is None:
    check.method_names[method_name] = operation_id
  elif other == operation_id:
    check.error(f'The operationId "{operation_id}" is not unique.')
  else:
    check.error(
        f'The operationIds "{other}" and "{operation_id}" both give the'
        f' method name "{method_name}". API Gateway removes the characters'
        ' other than letters, digits, and underscores, and capitalizes the'
        ' first letter. Make the operationIds differ after that change.'
    )


def _check_operation_quota(
    check: _Validation, label: str, operation: dict[str, Any]
) -> None:
  """Checks the x-google-quota extension of one operation."""
  quota = operation.get('x-google-quota')
  if quota is None:
    return
  if not isinstance(quota, dict):
    check.error(
        f'x-google-quota on {label} must be a map from each metric name to'
        ' its cost.'
    )
    return
  if 'metricCosts' in quota:
    check.error(
        f'x-google-quota on {label} uses the OpenAPI 2.0 "metricCosts"'
        ' wrapper. Remove the wrapper, such as "x-google-quota:'
        ' {read-requests: 1}".'
    )
    return
  for raw_metric, cost in quota.items():
    metric = str(raw_metric)
    check.charged_metrics.add(metric)
    if metric not in check.metric_names:
      check.error(
          f'x-google-quota on {label} names the metric "{metric}", which'
          ' x-google-api-management.metrics does not define.'
      )
    integer_cost = _as_integer(cost)
    if integer_cost is None or integer_cost < 0:
      check.error(
          f'x-google-quota on {label} gives the metric "{metric}" the cost'
          f' {cost!r}. Use a non-negative integer.'
      )
  security = operation.get('security', check.spec.get('security'))
  if not _requires_api_key(security, check.api_key_schemes):
    check.warnings.append(
        f'Operation {label} has x-google-quota, but it does not require an'
        ' API key. API Gateway uses the API key to identify the consumer'
        ' project that the quota counts. Require an API key in every'
        ' security alternative of the operation.'
    )


def _check_operation_backend(
    check: _Validation, label: str, path: str, operation: dict[str, Any]
) -> None:
  """Checks the backend of one operation, and records its path translation."""
  operation_backend = operation.get('x-google-backend')
  if isinstance(operation_backend, dict):
    check.error(
        f'Operation {label} uses an inline "x-google-backend" object (the'
        ' OpenAPI 2.0 form). Set x-google-backend to the name of a backend in'
        ' x-google-api-management.backends.'
    )
    return
  if operation_backend is not None:
    backend_name = str(operation_backend)
    default_translation = 'CONSTANT_ADDRESS'
    check.operation_backends.add(backend_name)
    if backend_name not in check.backends:
      check.error(
          f'Operation {label} references the backend "{backend_name}", which'
          ' x-google-api-management.backends does not define.'
      )
  elif 'x-google-backend' in check.spec:
    backend_name = check.root_backend
    default_translation = 'APPEND_PATH_TO_ADDRESS'
  else:
    check.error(
        f'Operation {label} has no x-google-backend, and the spec has no root'
        ' x-google-backend. API Gateway rejects an operation that has no'
        ' backend configured at the operation or API level.',
        _CONTROL_PLANE,
    )
    return
  config = check.backends.get(backend_name or '')
  if config is None:
    return
  translation = (
      _field(config, 'pathTranslation', 'path_translation')
      or default_translation
  )
  if translation == 'CONSTANT_ADDRESS' and _path_variables(path):
    check.query_operations.append(label)


def _operation_parameters(
    check: _Validation, path_parameters: Any, operation: dict[str, Any]
) -> list[dict[str, Any]]:
  """Returns the parameters of an operation, with path-level parameters.

  An operation parameter replaces a path-level parameter that has the same
  name and location.

  Args:
    check: The validation state.
    path_parameters: The "parameters" list of the path item.
    operation: The operation object.

  Returns:
    The resolved parameter objects.
  """
  merged: dict[tuple[str, str], dict[str, Any]] = {}
  for parameter_list in (path_parameters, operation.get('parameters')):
    if not isinstance(parameter_list, list):
      continue
    for raw_parameter in parameter_list:
      parameter = _resolve(check.spec, raw_parameter)
      if isinstance(parameter, dict):
        key = (str(parameter.get('name', '')), str(parameter.get('in', '')))
        merged[key] = parameter
  return list(merged.values())


def _check_parameters(
    check: _Validation,
    label: str,
    path: str,
    parameters: list[dict[str, Any]],
) -> None:
  """Checks the parameters of one operation.

  Args:
    check: The validation state.
    label: The method and path of the operation, for the messages.
    path: The path key of the operation.
    parameters: The resolved parameters of the operation.
  """
  path_names = {variable.split('=')[0] for variable in _path_variables(path)}
  declared = set()
  for parameter in parameters:
    name = str(parameter.get('name', ''))
    location = str(parameter.get('in', ''))
    if location in ('body', 'formData'):
      check.error(
          f'Parameter "{name}" of {label} has "in: {location}". OpenAPI 3.x'
          ' has no body or formData parameters. Move the body to'
          ' requestBody.'
      )
      continue
    old_fields = sorted(_V2_PARAMETER_FIELDS & set(parameter))
    if old_fields:
      check.error(
          f'Parameter "{name}" of {label} has the OpenAPI 2.0 fields'
          f' {old_fields}. Move type, format, and items into the parameter'
          ' "schema", and replace collectionFormat with "style" and'
          ' "explode".'
      )
    if location != 'path':
      continue
    declared.add(name)
    _check_path_parameter(check, label, path, name, parameter, path_names)
  for variable in _path_variables(path):
    if '=' not in variable and variable not in declared:
      check.error(
          f'The path of {label} has {{{variable}}}, but the operation has no'
          f' path parameter "{variable}". API Gateway rejects it. Add a'
          f' parameter with name: {variable}, in: path, and required: true.'
      )


def _check_path_parameter(
    check: _Validation,
    label: str,
    path: str,
    name: str,
    parameter: dict[str, Any],
    path_names: set[str],
) -> None:
  """Checks one path parameter against the path template."""
  if name not in path_names:
    check.error(
        f'Parameter "{name}" of {label} is a path parameter, but the path has'
        f' no {{{name}}}. API Gateway rejects it. Add {{{name}}} to the path,'
        ' or remove the parameter.'
    )
  required = parameter.get('required')
  if not isinstance(required, bool) or not required:
    check.error(
        f'Path parameter "{name}" of {label} must set "required: true".'
        ' OpenAPI 3.x requires it.'
    )
  extension = parameter.get('x-google-parameter')
  if extension is None:
    return
  if not isinstance(extension, dict):
    check.error(
        f'x-google-parameter of parameter "{name}" of {label} must be a'
        ' mapping, such as {pattern: "**"}.'
    )
    return
  pattern = extension.get('pattern')
  if not pattern:
    return
  if pattern != '**':
    check.error(
        f'Parameter "{name}" of {label} sets x-google-parameter.pattern to'
        f' {pattern!r}. The only allowed value is "**".'
    )
  elif not path.endswith(f'{{{name}}}'):
    check.error(
        f'Parameter "{name}" of {label} uses x-google-parameter: {{pattern:'
        ' "**"}, so it must be the last segment of the path.'
    )


def _check_charged_metrics(check: _Validation) -> None:
  """Checks that each metric that an operation charges has a quota limit."""
  charged = check.charged_metrics & check.metric_names
  for metric in sorted(charged - check.limited_metrics):
    check.error(
        f'x-google-quota charges the metric "{metric}", but no quota limit'
        ' uses it. API Gateway rejects the API config. Add a limit in'
        ' x-google-api-management.quota.limits.'
    )


def _default_path_translation(
    name: str, at_root: bool, on_operation: bool
) -> tuple[str, str]:
  """Describes the default path translation of a backend.

  Args:
    name: The backend name.
    at_root: Whether the root x-google-backend uses the backend.
    on_operation: Whether an operation-level x-google-backend uses it.

  Returns:
    The path translation for the report, and a warning.
  """
  if at_root and on_operation:
    return (
        (
            'APPEND_PATH_TO_ADDRESS at the root, CONSTANT_ADDRESS on operations'
            ' (defaults)'
        ),
        (
            f'Backend "{name}" has no pathTranslation, and both the root and an'
            ' operation-level x-google-backend use it. It uses'
            ' APPEND_PATH_TO_ADDRESS for the root and CONSTANT_ADDRESS for the'
            ' operation. Set pathTranslation, or define two backends.'
        ),
    )
  if on_operation:
    return (
        'CONSTANT_ADDRESS (default for an operation-level x-google-backend)',
        (
            f'Backend "{name}" has no pathTranslation, and an operation-level'
            ' x-google-backend uses it. There, the default is'
            ' CONSTANT_ADDRESS: API Gateway sends every request to the address'
            ' as it is, and sends path parameters as query parameters. Set'
            ' pathTranslation on the backend.'
        ),
    )
  if at_root:
    return (
        'APPEND_PATH_TO_ADDRESS (default for the root x-google-backend)',
        (
            f'Backend "{name}" has no pathTranslation. At the root, the default'
            ' is APPEND_PATH_TO_ADDRESS. Set it explicitly, because the default'
            ' changes to CONSTANT_ADDRESS if an operation uses this backend.'
        ),
    )
  return (
      'not set (not used)',
      (
          f'Backend "{name}" is not used by any x-google-backend. Remove it, or'
          ' set pathTranslation on it before you use it.'
      ),
  )


def _check_backend_usage(check: _Validation) -> None:
  """Records the path translation of each backend, and warns about defaults."""
  for name, config in check.backends.items():
    explicit = _field(config, 'pathTranslation', 'path_translation')
    if explicit is not None:
      check.path_translations[name] = str(explicit)
    elif name in check.router_backends:
      check.path_translations[name] = 'not set (model router backend)'
    else:
      translation, warning = _default_path_translation(
          name,
          at_root=name == check.root_backend,
          on_operation=name in check.operation_backends,
      )
      check.path_translations[name] = translation
      check.warnings.append(warning)


def _swagger_error(spec: dict[str, Any]) -> str:
  """Returns the error for an OpenAPI 2.0 spec, with its Google extensions."""
  extensions = sorted(
      str(key)
      for key in spec
      if str(key).startswith('x-google-') or str(key) == 'x-security'
  )
  message = (
      'This is an OpenAPI 2.0 (swagger) spec. Convert it to OpenAPI 3.0.x or'
      ' 3.1.x first, then run this validator on the converted spec.'
  )
  if extensions:
    message += (
        f' Move these root extensions to their OpenAPI 3.x form: {extensions}.'
    )
  return message


def _validate(spec: dict[str, Any], alias_lines: list[int]) -> _Validation:
  """Runs every check on a parsed spec, and returns the validation state."""
  check = _Validation(spec=spec)
  if 'swagger' in spec:
    check.error(_swagger_error(spec))
    return check
  _check_structure(check)
  _check_version_and_root_extensions(check)
  _check_schemas_and_refs(check, alias_lines)
  _check_servers(check)
  _check_management(check)
  _check_security(check)
  _check_root_backend(check)
  _check_paths(check)
  _check_charged_metrics(check)
  _check_backend_usage(check)
  return check


def validate_spec(
    spec: dict[str, Any], alias_lines: list[int] | None = None
) -> tuple[list[str], list[str], dict[str, Any]]:
  """Validates an OpenAPI spec against the API Gateway rules in this skill.

  Args:
    spec: The parsed OpenAPI spec.
    alias_lines: The line numbers of the YAML aliases to mappings in the file.

  Returns:
    The errors, the warnings, and a summary of the backends and operations.
  """
  check = _validate(spec, alias_lines or [])
  summary = {
      'base_path': check.base_path,
      'backends': check.path_translations,
      'path_parameters_as_query': check.query_operations,
      'operations': check.operation_count,
  }
  return check.errors, check.warnings, summary


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description=(
          'Check an OpenAPI 3.x spec for the Google Cloud API Gateway problems'
          ' in this skill. Prints a JSON report on stdout. It does not check'
          ' general OpenAPI validity.'
      ),
      epilog=(
          'Exit codes: 0 = PASS (read the warnings), 1 = FAIL (fix the'
          ' errors), 2 = the file cannot be read or parsed, or PyYAML is not'
          ' installed. Example, from the skill directory: python3'
          ' scripts/validate_apigw_openapi.py --spec=/path/to/openapi.yaml'
      ),
  )
  parser.add_argument(
      '--spec',
      required=True,
      help='Path to the OpenAPI YAML or JSON spec file to validate.',
  )
  args = parser.parse_args(argv)

  try:
    spec, alias_lines = _load_spec(args.spec)
  except (OSError, RuntimeError, ValueError) as exc:
    print(f'Error: {exc}', file=sys.stderr)
    return 2
  errors, warnings, summary = validate_spec(spec, alias_lines)

  report = {
      'status': 'FAIL' if errors else 'PASS',
      'spec': args.spec,
      'openapi': str(spec.get('openapi', spec.get('swagger', ''))),
      'base_path': summary['base_path'],
      'backend_path_translation': summary['backends'],
      'path_parameters_as_query': summary['path_parameters_as_query'],
      'operation_count': summary['operations'],
      'errors': errors,
      'warnings': warnings,
      'note': _NOTE,
  }
  print(json.dumps(report, indent=2))
  if errors:
    print(
        f'API Gateway OpenAPI validation failed with {len(errors)} error(s).',
        file=sys.stderr,
    )
    return 1
  return 0


if __name__ == '__main__':
  sys.exit(main())

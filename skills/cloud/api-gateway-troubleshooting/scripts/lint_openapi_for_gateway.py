#!/usr/bin/env python3
"""Lints OpenAPI documents for documented API Gateway limitations.

The linter works offline and only reads the files that it is given. It reports
the OpenAPI features that the public API Gateway documentation describes as
unsupported, rejected, or ignored, so that you can fix them before you create
an API config. Each finding links to the page that documents the limitation.
Pass all OpenAPI files of one API config together. JSON input needs only the
Python standard library. YAML input needs PyYAML.
"""

from __future__ import annotations

import argparse
import collections
from collections.abc import Iterator
import json
import os
import re
import sys
from typing import Any
from urllib import parse

try:
  import yaml  # pylint: disable=g-import-not-at-top

  _HAS_YAML = True
except ImportError:
  _HAS_YAML = False

_DOCS = 'https://docs.cloud.google.com/api-gateway/docs/'
# LIMITS and EXTENSIONS resolve to the page for the OpenAPI version of a file.
_PAGES = {
    ('LIMITS', False): _DOCS + 'openapi-limitations.md.txt',
    ('LIMITS', True): _DOCS + 'openapi-v3-limitations.md.txt',
    ('EXTENSIONS', False): _DOCS + 'oasv2-extensions.md.txt',
    ('EXTENSIONS', True): _DOCS + 'oasv3-extensions.md.txt',
}
_V3_LIMITS = _PAGES[('LIMITS', True)]
_BACKENDS = _DOCS + 'securing-backend-services.md.txt'
_OVERVIEW = _DOCS + 'openapi-overview.md.txt'

# Documented limits. The messages in _FINDINGS repeat them.
_MAX_YAML_ALIASES = 200
_MAX_DEADLINE_SECONDS = 3600
_MAX_NON_STREAMING_DEADLINE_SECONDS = 600
_OAS3_MAX_FILES = 50
# The documented limit is 10MB. The binary reading is the larger one, so the
# check never flags files that are within the limit under either reading.
_OAS3_MAX_BYTES = 10 * 1024 * 1024

# Rule ID, with an optional ":variant" suffix: (severity, page, message).
# fmt: off
_FINDINGS = {
    'PARTIAL_SEGMENT_PATH_TEMPLATE': ('ERROR', 'LIMITS', (
        'Make each parameter in path {path} an entire path segment, such as'
        ' /items/{{itemId}}, because API Gateway rejects partial segments.')),
    'EXTERNAL_REF': ('ERROR', 'LIMITS', (
        'Replace $ref {ref} with a local reference (#/...), because API Gateway'
        ' does not support references outside the provided OpenAPI document.')),
    'EXTERNAL_REF:between_files': ('WARNING', 'LIMITS', (
        'Prefer a local reference (#/...) over $ref {ref}, because the docs do'
        ' not say whether references between uploaded files are supported.')),
    'HOST_CUSTOM_PORT': ('ERROR', 'LIMITS', (
        'Remove the port from {field} {value}, because API Gateway does not'
        ' allow custom ports in {field}.')),
    'API_KEY_IN_LOGICAL_OR': ('ERROR', 'LIMITS', (
        'Use one requirement instead of these alternatives (logical OR),'
        ' because API Gateway does not support alternatives when one is an API'
        ' key.')),
    'API_KEY_IN_LOGICAL_OR:oas2': ('WARNING', 'LIMITS', (
        'Use one requirement instead of these alternatives (logical OR),'
        ' because API Gateway does not support alternatives when one is an API'
        ' key.')),
    'OAUTH_LOGICAL_AND': ('ERROR', 'LIMITS', (
        'Keep one of the OAuth2 schemes {names} or make them alternatives,'
        ' because API Gateway does not support a logical AND of OAuth2'
        ' schemes.')),
    'OPTIONAL_SECURITY_WITH_OAUTH': ('ERROR', 'LIMITS', (
        'Remove the empty requirement ({{}}) from this list, because API'
        ' Gateway supports optional security for API keys but not for OAuth.')),
    'OPTIONAL_SECURITY_WITH_OAUTH:oas2': ('WARNING', 'LIMITS', (
        'Remove the empty requirement ({{}}) from this list, because API'
        ' Gateway supports optional security for API keys but not for OAuth.')),
    'UNDEFINED_SECURITY_SCHEME': ('ERROR', 'LIMITS', (
        'Define security scheme {name} in {definitions} or remove it, because'
        ' API Gateway rejects a requirement without a matching definition.')),
    'UNDEFINED_SECURITY_SCHEME:oas2': ('WARNING', 'LIMITS', (
        'Define security scheme {name} in {definitions} or remove it. The docs'
        ' say that API Gateway rejects an undefined scheme in OpenAPI 3.x, and'
        ' they don\'t say what happens in OpenAPI 2.0.')),
    'SCOPES_NOT_ENFORCED': ('INFO', 'LIMITS', (
        'Enforce the scopes of {name} in your backend if you need them, because'
        ' API Gateway does not check or enforce scopes.')),
    'YAML_ALIAS_LIMIT': ('ERROR', 'LIMITS', (
        'Reduce the YAML alias nodes from {count} to 200 or fewer, because API'
        ' Gateway accepts at most 200 per document.')),
    'DEADLINE_ABOVE_MAX': ('ERROR', 'EXTENSIONS', (
        'Lower deadline {deadline} to 3600 seconds or less, because 3600'
        ' seconds is the maximum configurable deadline.')),
    'DEADLINE_ABOVE_NON_STREAMING_MAX': ('WARNING', 'EXTENSIONS', (
        'Lower deadline {deadline} to 600 seconds or less unless all gateways'
        ' for this config are streaming-enabled, because a non-streaming'
        ' gateway rejects it at gateway create or update.')),
    'GOOGLEAPIS_BACKEND': ('ERROR', _BACKENDS, (
        'Route this backend to your own service instead of {host}, because API'
        ' Gateway does not support proxying to other Google Cloud APIs.')),
    'JWT_AUDIENCE_AND_DISABLE_AUTH': ('ERROR', 'EXTENSIONS', (
        'Set only one of {audience} and {disable} on this backend.')),
    'WRONG_VERSION_EXTENSION': ('WARNING', 'EXTENSIONS', (
        '{fix}, because {extension} is documented only for OpenAPI'
        ' {other}.')),
    'X_GOOGLE_ALLOW_IN_OAS3': ('ERROR', _V3_LIMITS, (
        'Remove x-google-allow and define every path the gateway serves,'
        ' because API Gateway does not support x-google-allow for OpenAPI'
        ' 3.x.')),
    'MULTIPLE_X_GOOGLE_ENDPOINT_SERVERS': ('ERROR', _V3_LIMITS, (
        'Keep x-google-endpoint on only one of {servers}, because API Gateway'
        ' permits only one server with x-google-endpoint.')),
    'INVALID_SERVER_URL': ('ERROR', _V3_LIMITS, (
        'Change server URL {url!r} to a URL with a scheme or a base path that'
        ' begins with /, because API Gateway rejects other server URLs.')),
    'OAS3_SIZE_OR_FILE_COUNT': ('ERROR', _V3_LIMITS, (
        'Reduce the OpenAPI 3.x files ({count} files, {size} bytes) to at most'
        ' 50 files and 10 MB in total, because API Gateway enforces both.')),
    'UNSUPPORTED_OPENAPI_VERSION': ('ERROR', _OVERVIEW, (
        'Declare swagger: "2.0", openapi: 3.0.x, or openapi: 3.1.x (found'
        ' {found}), because API Gateway supports only these versions.')),
}
# fmt: on
_SEVERITY_RANK = {'ERROR': 0, 'WARNING': 1, 'INFO': 2}
_SUMMARY_KEYS = {'errors': 'ERROR', 'warnings': 'WARNING', 'info': 'INFO'}

# Extensions that only the extensions page of one OpenAPI version documents,
# mapped to the fix in a document of the other version, or None if the other
# version has no replacement.
_V2_ONLY_EXTENSIONS = {
    'x-google-api-name': 'Use x-google-api-management.apiName instead',
    'x-google-audiences': 'Use x-google-auth.audiences instead',
    'x-google-endpoints': 'Use x-google-endpoint on a server object instead',
    'x-google-issuer': 'Use x-google-auth.issuer instead',
    'x-google-jwks_uri': 'Use x-google-auth.jwksUri instead',
    'x-google-jwt-locations': 'Use x-google-auth.jwtLocations instead',
    'x-google-management': 'Use x-google-api-management instead',
}
_V3_ONLY_EXTENSIONS = {
    'x-google-api-management': (
        'Use x-google-management, x-google-backend, and x-google-api-name'
    ),
    'x-google-auth': (
        'Use x-google-issuer, x-google-jwks_uri, x-google-audiences, and'
        ' x-google-jwt-locations instead'
    ),
    'x-google-endpoint': 'Use a top-level x-google-endpoints list instead',
    'x-google-mcp-tool': None,
    'x-google-model-router': None,
    'x-google-parameter': 'Use the {name=**} path template syntax instead',
}

_HTTP_METHODS = 'get put post delete options head patch trace'.split()
_PARAM_RE = re.compile(r'\{[^{}]*\}')

_EPILOG = """\
examples:
  python3 scripts/lint_openapi_for_gateway.py openapi.yaml
  python3 scripts/lint_openapi_for_gateway.py main.yaml extra.yaml --format text

stdout: {files, openapi_version, findings, summary}; each finding has rule,
severity, file, location, message, and doc. Diagnostics go to stderr.

exit codes:
  0  no ERROR findings (WARNING and INFO findings are allowed)
  1  at least one ERROR finding
  2  usage, file, parse, or dependency error
"""


class InputError(Exception):
  """A file, parse, or dependency problem that ends the run with exit code 2."""


def _child(location: str, key: Any) -> str:
  return f'{location}.{key}' if location else str(key)


def _items(node: Any) -> list[tuple[Any, Any]]:
  return list(node.items()) if isinstance(node, dict) else []


def _list(node: Any) -> list[Any]:
  return node if isinstance(node, list) else []


def _get(node: Any, *keys: str) -> Any:
  """Returns node[key1][key2]..., or None if a level is not a mapping."""
  for key in keys:
    node = node.get(key) if isinstance(node, dict) else None
  return node


def _mappings(node: Any) -> Iterator[tuple[str, dict[Any, Any]]]:
  """Yields (location, mapping) for each mapping in node, in document order.

  The walk is iterative and visits each object once, so YAML aliases and
  recursive anchors cannot make it loop or repeat work.

  Args:
    node: A parsed document, or any part of one.

  Yields:
    A (location, mapping) tuple for each mapping, where location is the
    dotted path of the mapping in the document.
  """
  seen: set[int] = set()
  stack: list[tuple[str, Any]] = [('', node)]
  while stack:
    location, current = stack.pop()
    if not isinstance(current, (dict, list)) or id(current) in seen:
      continue
    seen.add(id(current))
    if isinstance(current, dict):
      yield location, current
      children = [(_child(location, k), v) for k, v in current.items()]
    else:
      children = [(f'{location}[{i}]', v) for i, v in enumerate(current)]
    stack.extend(reversed(children))


def _operations(doc: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
  for path, item in _items(doc.get('paths')):
    for method in _HTTP_METHODS:
      if isinstance(_get(item, method), dict):
        yield f'paths.{path}.{method}', item[method]


def _is_partial_segment(path: str) -> bool:
  """Returns whether a parameter of a path template is a partial segment.

  The last segment can end with a custom method, such as /items/{id}:undelete.

  Args:
    path: A path template from the paths object, such as /items/{id}.
  """
  if re.search(r'[{}]', _PARAM_RE.sub('', path)):
    return True  # Nested or unbalanced braces.
  for match in _PARAM_RE.finditer(path):
    starts_segment = path[: match.start()].endswith('/')
    rest = path[match.end() :]
    custom_method = rest[:1] == ':' and '/' not in rest
    if not starts_segment or not (rest[:1] in ('', '/') or custom_method):
      return True
  return False


def _host(url: str) -> str:
  """Returns the lowercase host of a URL, which may omit its scheme."""
  try:
    host = parse.urlsplit(url if '://' in url else '//' + url).hostname
  except ValueError:
    return ''
  return (host or '').rstrip('.')


def _has_port(url: str) -> bool:
  try:
    return parse.urlsplit(url).port is not None
  except ValueError:
    return False


def _version(doc: dict[str, Any]) -> str:
  """Returns '2.0', '3.0.x', '3.1.x', or 'unknown' for a parsed document."""
  if str(doc.get('swagger')) == '2.0':
    return '2.0'
  match = re.fullmatch(r'3\.([01])(\.\d+)?', str(doc.get('openapi')))
  return f'3.{match.group(1)}.x' if match else 'unknown'


def _model_router_backends(doc: dict[str, Any]) -> set[str]:
  """Returns the names of the backends that model routers send requests to."""
  routers = _get(
      doc, 'x-google-api-management', 'ai', 'models', 'routing', 'routers'
  )
  names = set()
  for _, router in _items(routers):
    names.add(_get(router, 'defaultModel', 'backend'))
    names.update(_get(rule, 'backend') for rule in _list(_get(router, 'rules')))
  return {name for name in names if isinstance(name, str)}


def load_spec(path: str) -> tuple[dict[str, Any], int, int | None]:
  """Returns the parsed document, its size, and its YAML alias count.

  Args:
    path: The path of a JSON or YAML OpenAPI file.

  Returns:
    A tuple of the parsed document, its size in bytes, and its YAML alias
    count. The alias count is None for JSON input.

  Raises:
    InputError: If the file cannot be read or parsed, or if it is YAML and
      PyYAML is not installed.
  """
  try:
    with open(path, 'rb') as f:
      raw = f.read()
    text = raw.decode('utf-8-sig')
  except (OSError, UnicodeDecodeError) as exc:
    raise InputError(f'Cannot read {path}: {exc}') from exc
  aliases = None
  try:
    doc = json.loads(text)
  except (ValueError, RecursionError) as exc:
    if path.lower().endswith('.json'):
      raise InputError(f'{path} is not valid JSON: {exc}') from exc
    if not _HAS_YAML:
      raise InputError(
          f'{path} is not JSON, and reading YAML requires PyYAML. Install it'
          ' with: pip install "PyYAML>=6.0,<7.0"'
      ) from exc
    try:
      events = yaml.parse(text, Loader=yaml.SafeLoader)
      aliases = sum(isinstance(event, yaml.AliasEvent) for event in events)
      doc = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError) as yaml_exc:
      raise InputError(f'{path} is not valid YAML: {yaml_exc}') from yaml_exc
  if not isinstance(doc, dict):
    raise InputError(f'{path} must contain a JSON object or a YAML mapping.')
  return doc, len(raw), aliases


class Linter:
  """Collects the findings for the OpenAPI files of one API config."""

  def __init__(self, paths: list[str]):
    self.findings: list[dict[str, Any]] = []
    self._all_files = {os.path.abspath(path) for path in paths}
    self._multi_file = len(paths) > 1
    self._file: str | None = None
    self._v3 = False

  def _add(self, finding: str, location: str, /, **values: Any) -> None:
    severity, page, message = _FINDINGS[finding]
    self.findings.append({
        'rule': finding.split(':')[0],
        'severity': severity,
        'file': self._file,
        'location': location,
        'message': message.format(**values),
        'doc': _PAGES.get((page, self._v3), page),
    })

  def lint_file(
      self, path: str, doc: dict[str, Any], version: str, aliases: int | None
  ) -> None:
    """Checks one parsed file that declares the given OpenAPI version."""
    self._file, self._v3 = path, version.startswith('3')
    if version == 'unknown':
      found = {k: doc[k] for k in ('swagger', 'openapi') if k in doc}
      self._add(
          'UNSUPPORTED_OPENAPI_VERSION',
          '(document)',
          found=found or 'no version field',
      )
    if aliases is not None and aliases > _MAX_YAML_ALIASES:
      self._add('YAML_ALIAS_LIMIT', '(document)', count=aliases)
    for template, _ in _items(doc.get('paths')):
      if isinstance(template, str) and _is_partial_segment(template):
        self._add(
            'PARTIAL_SEGMENT_PATH_TEMPLATE', f'paths.{template}', path=template
        )
    self._check_keys(doc, version != 'unknown')
    if version == 'unknown':
      return
    self._check_security(doc)
    if self._v3:
      self._check_servers(doc)
      model_backends = _model_router_backends(doc)
      backends = _get(doc, 'x-google-api-management', 'backends')
      for name, backend in _items(backends):
        self._check_backend(
            f'x-google-api-management.backends.{name}',
            backend,
            ('jwtAudience', 'disableAuth'),
            name in model_backends,
        )
      return
    host = doc.get('host')
    if isinstance(host, str) and re.search(r':\d+$', host):
      self._add('HOST_CUSTOM_PORT', 'host', field='host', value=host)
    backends = [('x-google-backend', doc.get('x-google-backend'))] + [
        (f'{location}.x-google-backend', operation.get('x-google-backend'))
        for location, operation in _operations(doc)
    ]
    for location, backend in backends:
      self._check_backend(
          location, backend, ('jwt_audience', 'disable_auth'), False
      )

  def lint_set(self, sizes: list[int]) -> None:
    """Checks the limits for the OpenAPI 3.x files of an API config."""
    self._file, self._v3 = None, True
    if len(sizes) > _OAS3_MAX_FILES or sum(sizes) > _OAS3_MAX_BYTES:
      self._add(
          'OAS3_SIZE_OR_FILE_COUNT',
          '(all files)',
          count=len(sizes),
          size=sum(sizes),
      )

  def _check_keys(self, doc: dict[str, Any], known_version: bool) -> None:
    """Checks $ref values and version-specific extensions in all mappings."""
    if self._v3:
      wrong, other, backend_form = _V2_ONLY_EXTENSIONS, '2.0', (dict, 'object')
      backend_fix = (
          'Set x-google-backend to the name of a backend in'
          ' x-google-api-management.backends'
      )
    else:
      wrong, other, backend_form = _V3_ONLY_EXTENSIONS, '3.x', (str, 'string')
      backend_fix = 'Set x-google-backend to an object with an address field'
    for location, mapping in _mappings(doc):
      for key, value in mapping.items():
        where = _child(location, key)
        if key == '$ref' and isinstance(value, str) and value[:1] != '#':
          self._check_ref(where, value)
        elif not known_version:
          continue
        elif key == 'x-google-allow' and self._v3:
          self._add('X_GOOGLE_ALLOW_IN_OAS3', where)
        elif key in wrong:
          self._add(
              'WRONG_VERSION_EXTENSION',
              where,
              fix=wrong[key] or f'Remove {key} or migrate to OpenAPI 3.x',
              extension=key,
              other=other,
          )
        elif key == 'x-google-backend' and isinstance(value, backend_form[0]):
          self._add(
              'WRONG_VERSION_EXTENSION',
              where,
              fix=backend_fix,
              extension=f'its {backend_form[1]} form',
              other=other,
          )

  def _check_ref(self, location: str, ref: str) -> None:
    """Checks a $ref that does not point inside the same document."""
    base = os.path.dirname(os.path.abspath(self._file or ''))
    target = os.path.normpath(os.path.join(base, ref.split('#', 1)[0]))
    if self._multi_file and '://' not in ref and target in self._all_files:
      self._add('EXTERNAL_REF:between_files', location, ref=ref)
    else:
      self._add('EXTERNAL_REF', location, ref=ref)

  def _check_security(self, doc: dict[str, Any]) -> None:
    """Checks the top-level and operation-level security requirements."""
    if self._v3:
      definitions = 'components.securitySchemes'
      schemes = _get(doc, 'components', 'securitySchemes')
    else:
      definitions = 'securityDefinitions'
      schemes = doc.get('securityDefinitions')
    types = {name: _get(scheme, 'type') for name, scheme in _items(schemes)}
    # The limitations pages document these rejections for OpenAPI 3.x only.
    variant = '' if self._v3 else ':oas2'
    lists = [('security', doc.get('security'))] + [
        (f'{location}.security', operation.get('security'))
        for location, operation in _operations(doc)
    ]
    scoped = set()
    for location, requirements in lists:
      for index, requirement in enumerate(_list(requirements)):
        for name, scopes in _items(requirement):
          where = f'{location}[{index}].{name}'
          if name not in types:
            self._add(
                'UNDEFINED_SECURITY_SCHEME' + variant,
                where,
                name=name,
                definitions=definitions,
            )
          if _list(scopes) and name not in scoped:
            scoped.add(name)
            self._add('SCOPES_NOT_ENFORCED', where, name=name)
        oauth = [
            str(name)
            for name, _ in _items(requirement)
            if types.get(name) == 'oauth2'
        ]
        if len(oauth) > 1:
          self._add(
              'OAUTH_LOGICAL_AND',
              f'{location}[{index}]',
              names=', '.join(oauth),
          )
      objects = [r for r in _list(requirements) if isinstance(r, dict)]
      alternatives = [r for r in objects if r]
      kinds = set()
      for alternative in alternatives:
        kinds.update(types.get(name) for name in alternative)
      if len(alternatives) > 1 and 'apiKey' in kinds:
        self._add('API_KEY_IN_LOGICAL_OR' + variant, location)
      if len(alternatives) < len(objects) and 'oauth2' in kinds:
        self._add('OPTIONAL_SECURITY_WITH_OAUTH' + variant, location)

  def _check_servers(self, doc: dict[str, Any]) -> None:
    """Checks the server URLs and x-google-endpoint of an OpenAPI 3.x file."""
    endpoints = []
    for index, server in enumerate(_list(doc.get('servers'))):
      if not isinstance(server, dict):
        continue
      if 'x-google-endpoint' in server:
        endpoints.append(f'servers[{index}]')
      url, where = server.get('url'), f'servers[{index}].url'
      if not isinstance(url, str) or not (url[:1] == '/' or '://' in url):
        self._add('INVALID_SERVER_URL', where, url=url)
      elif _has_port(url):
        self._add('HOST_CUSTOM_PORT', where, field='servers.url', value=url)
    if len(endpoints) > 1:
      self._add(
          'MULTIPLE_X_GOOGLE_ENDPOINT_SERVERS',
          'servers',
          servers=', '.join(endpoints),
      )

  def _check_backend(
      self,
      location: str,
      backend: Any,
      auth_keys: tuple[str, str],
      model_backend: bool,
  ) -> None:
    """Checks an OpenAPI 2.0 x-google-backend or an OpenAPI 3.x backend."""
    if not isinstance(backend, dict):
      return
    deadline = backend.get('deadline')
    if isinstance(deadline, (int, float)) and not isinstance(deadline, bool):
      if deadline > _MAX_DEADLINE_SECONDS:
        self._add(
            'DEADLINE_ABOVE_MAX', f'{location}.deadline', deadline=deadline
        )
      elif deadline > _MAX_NON_STREAMING_DEADLINE_SECONDS:
        self._add(
            'DEADLINE_ABOVE_NON_STREAMING_MAX',
            f'{location}.deadline',
            deadline=deadline,
        )
    address = backend.get('address')
    host = _host(address) if isinstance(address, str) else ''
    # The documented model routing example uses a googleapis.com backend.
    if not model_backend and (
        host == 'googleapis.com' or host.endswith('.googleapis.com')
    ):
      self._add('GOOGLEAPIS_BACKEND', f'{location}.address', host=host)
    audience, disable = auth_keys
    if audience in backend and disable in backend:
      self._add(
          'JWT_AUDIENCE_AND_DISABLE_AUTH',
          location,
          audience=audience,
          disable=disable,
      )


def _format_text(report: dict[str, Any]) -> str:
  """Returns the report as human-readable text, for --format text."""
  lines = []
  for finding in report['findings']:
    where = finding['location']
    if finding['file']:
      where = f'{finding["file"]}: {where}'
    lines.append(f'{finding["severity"]} {finding["rule"]} at {where}')
    lines.append(f'  {finding["message"]}\n  {finding["doc"]}')
  summary = report['summary']
  lines.append(
      f'{len(report["files"])} file(s), OpenAPI {report["openapi_version"]}:'
      f' {summary["errors"]} error(s), {summary["warnings"]} warning(s),'
      f' {summary["info"]} info finding(s).'
  )
  return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description=__doc__,
      epilog=_EPILOG,
      formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  parser.add_argument(
      'specs',
      nargs='+',
      metavar='SPEC',
      help='OpenAPI file of the API config (JSON, or YAML with PyYAML).',
  )
  parser.add_argument(
      '--format',
      choices=('json', 'text'),
      default='json',
      help='Output format on stdout (default: json).',
  )
  args = parser.parse_args(argv)

  paths = list(dict.fromkeys(args.specs))
  try:
    loaded = [(path, *load_spec(path)) for path in paths]
  except InputError as exc:
    print(f'Error: {exc}', file=sys.stderr)
    return 2
  versions = {path: _version(doc) for path, doc, _, _ in loaded}
  known = sorted(set(versions.values()) - {'unknown'})
  if len(known) > 1:
    print(
        f'Error: This linter checks one OpenAPI version per run ({versions}).'
        ' Lint files that use different versions in separate runs.',
        file=sys.stderr,
    )
    return 2
  version = known[0] if known else 'unknown'

  linter = Linter(paths)
  for path, doc, _, aliases in loaded:
    linter.lint_file(path, doc, versions[path], aliases)
  if version.startswith('3'):
    linter.lint_set([size for _, _, size, _ in loaded])
  findings = sorted(
      linter.findings, key=lambda finding: _SEVERITY_RANK[finding['severity']]
  )
  counts = collections.Counter(finding['severity'] for finding in findings)
  summary = {key: counts[severity] for key, severity in _SUMMARY_KEYS.items()}
  report = {'files': paths, 'openapi_version': version, 'findings': findings}
  report['summary'] = summary
  if args.format == 'json':
    print(json.dumps(report, indent=2))
  else:
    print(_format_text(report))
  if summary['errors']:
    print(
        f'Found {summary["errors"]} ERROR finding(s). Fix them before you'
        ' create the API config.',
        file=sys.stderr,
    )
  return 1 if summary['errors'] else 0


if __name__ == '__main__':
  sys.exit(main())

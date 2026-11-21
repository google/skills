#!/usr/bin/env python3
"""Validates an OpenAPI spec against Google Cloud API Gateway MCP rules.

Errors are rules that the API Gateway documentation states. Warnings are
documented limits that need a decision from the user.

The script checks that the specification uses OpenAPI 3.0.x or 3.1.x, omits
x-google-allow, gives each schema one type, declares
x-google-api-management.backends, references only
defined backends, uses at most one server with x-google-endpoint, gives every
operation an operationId, and places x-google-mcp-tool only at the operation
level. It checks that an MCP
specification has no x-google-model-router operation, and that each exposed
tool has a backend, a unique name that matches [A-Za-z0-9_.-]{1,128}, a
non-empty description, and no header parameter with the reserved x-google-
prefix. It checks that tools-list.security names exactly one JWT or API key
scheme, that a JWT scheme is also in the root security list, and that no
security list gives alternative (OR) requirements with an API key scheme.

It warns about HTTP 204 responses, request parameters that are not primitive
types, API key schemes that are not read from the x-api-key header, the
OpenAPI 2.0 x-google-management extension, a model routing "ai" block in an
MCP specification, operations that an mcp object exposes by default, and
operations that global MCP enablement skips because they have no backend.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

try:
  import yaml

  _HAS_YAML = True
except ImportError:
  _HAS_YAML = False

_TOOL_NAME_RE = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
_OAS3_RE = re.compile(r'^3\.[01]\.\d+$')
_HTTP_METHODS = frozenset(
    {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}
)
_SUPPORTED_MCP_METHODS = frozenset({'get', 'post', 'put', 'patch', 'delete'})
_MAX_TOOLS_PER_GATEWAY = 1000
# Keys whose values are data, not schemas. A "type" list inside them is not a
# schema type list. The check also skips vendor extensions (x-*).
_NON_SCHEMA_KEYS = frozenset(
    {'const', 'default', 'enum', 'example', 'examples'}
)


def _load_spec(path: str) -> dict[str, Any]:
  """Reads the OpenAPI specification file at path as JSON or YAML."""
  with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
  try:
    data = json.loads(content)
  except json.JSONDecodeError:
    pass
  else:
    if isinstance(data, dict):
      return data
  if not _HAS_YAML:
    raise RuntimeError(
        'PyYAML is required to parse YAML files. Install with: '
        'pip install "PyYAML>=6.0,<7.0"'
    )
  try:
    data = yaml.safe_load(content)
  except yaml.YAMLError as exc:
    raise ValueError(f'{path} is not valid JSON or YAML: {exc}') from exc
  if not isinstance(data, dict):
    raise ValueError(f'{path} did not parse as a YAML/JSON mapping.')
  return data


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


def _requirement_names(security: Any) -> list[set[str]]:
  """Returns the scheme names of each non-empty security requirement."""
  if not isinstance(security, list):
    return []
  return [
      {str(name) for name in requirement}
      for requirement in security
      if isinstance(requirement, dict) and requirement
  ]


def _or_with_api_key_error(
    security: Any, schemes: dict[str, Any], where: str
) -> str | None:
  """Returns an error if a security list has OR requirements with an API key.

  Args:
    security: The value of a "security" list.
    schemes: The security schemes from components.securitySchemes.
    where: The location of the "security" list, for the error message.

  Returns:
    The error message, or None if the security list is valid.
  """
  requirements = _requirement_names(security)
  uses_api_key = False
  for requirement in requirements:
    for name in requirement:
      scheme = schemes.get(name)
      if isinstance(scheme, dict) and scheme.get('type') == 'apiKey':
        uses_api_key = True
  if len(requirements) > 1 and uses_api_key:
    return (
        f'The "security" list of {where} gives alternative (OR)'
        ' requirements, and one of them uses an API key scheme. API Gateway'
        ' does not support OR requirements with an API key. Put the schemes'
        ' in one requirement object (AND).'
    )
  return None


def _type_list_schemas(node: Any, location: str) -> list[tuple[str, str]]:
  """Finds the schemas whose "type" is a list of more than one type.

  API Gateway rejects such a schema, for example `type: ["string", "null"]`,
  when you create the API config.

  Args:
    node: A part of the OpenAPI specification.
    location: The JSON pointer of node in the specification.

  Returns:
    The JSON pointer and the type list of each schema with more than one type.
  """
  found: list[tuple[str, str]] = []
  if isinstance(node, dict):
    node_type = node.get('type')
    if isinstance(node_type, list) and len(node_type) > 1:
      found.append((location or '/', json.dumps(node_type)))
    for key, value in node.items():
      key_text = str(key)
      if key_text in _NON_SCHEMA_KEYS or key_text.startswith('x-'):
        continue
      escaped_key = key_text.replace('~', '~0').replace('/', '~1')
      found.extend(_type_list_schemas(value, f'{location}/{escaped_key}'))
  elif isinstance(node, list):
    for index, item in enumerate(node):
      found.extend(_type_list_schemas(item, f'{location}/{index}'))
  return found


def validate_mcp_spec(
    spec: dict[str, Any],
) -> tuple[list[str], list[str], list[dict[str, str]]]:
  """Returns (errors, warnings, exposed_tools) for an OpenAPI spec."""
  errors: list[str] = []
  warnings: list[str] = []
  exposed_tools: list[dict[str, str]] = []

  openapi_version = str(spec.get('openapi', ''))
  if 'swagger' in spec:
    errors.append(
        'OpenAPI 2.0 (swagger: "2.0") is not supported for API Gateway MCP.'
        ' Convert the specification to OpenAPI 3.0.x or 3.1.x (for example,'
        ' openapi: 3.0.4).'
    )
  elif not _OAS3_RE.match(openapi_version):
    errors.append(
        'Expected openapi version 3.0.x or 3.1.x (for example, 3.0.4 or'
        f' 3.1.0), got "{openapi_version}".'
    )

  if 'x-google-allow' in spec:
    errors.append(
        'Extension "x-google-allow" is not supported in OpenAPI 3.x and must '
        'be removed.'
    )

  for location, type_list in _type_list_schemas(spec, ''):
    errors.append(
        f'The schema at {location} has more than one type ({type_list}). API'
        ' Gateway rejects a type list when you create the API config. Give the'
        ' schema one type.'
    )

  if 'x-google-management' in spec:
    warnings.append(
        'Found the OpenAPI 2.0 extension "x-google-management". In OpenAPI'
        ' 3.x, move the metrics and quota settings into'
        ' "x-google-api-management".'
    )

  servers = spec.get('servers', [])
  if isinstance(servers, list):
    endpoint_count = sum(
        1
        for server in servers
        if isinstance(server, dict) and 'x-google-endpoint' in server
    )
    if endpoint_count > 1:
      errors.append(
          f'Found {endpoint_count} servers with "x-google-endpoint"; API'
          ' Gateway permits at most one server with x-google-endpoint.'
      )

  management = spec.get('x-google-api-management')
  if not isinstance(management, dict):
    errors.append('Missing required root "x-google-api-management" mapping.')
    return errors, warnings, exposed_tools

  backends = management.get('backends')
  backend_names: set[str] = set()
  if not isinstance(backends, dict) or not backends:
    errors.append(
        '"x-google-api-management.backends" must define at least one named'
        ' backend.'
    )
  else:
    for backend_name, backend_config in backends.items():
      backend_names.add(str(backend_name))
      if not isinstance(backend_config, dict) or not backend_config.get(
          'address'
      ):
        errors.append(
            f'Backend "{backend_name}" is missing a required "address".'
        )

  components = spec.get('components')
  schemes = (
      components.get('securitySchemes', {})
      if isinstance(components, dict)
      else {}
  )
  if not isinstance(schemes, dict):
    schemes = {}

  root_or_error = _or_with_api_key_error(
      spec.get('security'), schemes, 'the root'
  )
  if root_or_error:
    errors.append(root_or_error)

  mcp_config = management.get('mcp')
  global_mcp_enabled = False
  if isinstance(mcp_config, bool):
    global_mcp_enabled = mcp_config
    if mcp_config:
      warnings.append(
          'tools/list is unauthenticated ("mcp: true"). Configure '
          'x-google-api-management.mcp.tools-list.security with a JWT or API '
          'key scheme for production.'
      )
  elif isinstance(mcp_config, dict):
    global_mcp_enabled = True
    tools_list = mcp_config.get('tools-list', {})
    if isinstance(tools_list, dict) and 'security' in tools_list:
      tools_list_security = tools_list.get('security')
      if (
          not isinstance(tools_list_security, dict)
          or len(tools_list_security) != 1
      ):
        errors.append(
            '"x-google-api-management.mcp.tools-list.security" must be a map '
            'naming exactly one JWT or API key security scheme.'
        )
      else:
        scheme_name = str(next(iter(tools_list_security.keys())))
        scheme_def = schemes.get(scheme_name)
        is_jwt = isinstance(scheme_def, dict) and (
            scheme_def.get('type') == 'oauth2'
            and isinstance(scheme_def.get('x-google-auth'), dict)
        )
        is_api_key = (
            isinstance(scheme_def, dict) and scheme_def.get('type') == 'apiKey'
        )
        if not isinstance(scheme_def, dict):
          errors.append(
              'tools-list.security references unknown security scheme'
              f' "{scheme_name}" not defined under components.securitySchemes.'
          )
        elif not is_jwt and not is_api_key:
          errors.append(
              f'tools-list.security scheme "{scheme_name}" must be a JWT scheme'
              ' (type "oauth2" with an "x-google-auth" configuration) or an API'
              ' key scheme (type "apiKey").'
          )
        elif is_api_key:
          if (
              scheme_def.get('in') != 'header'
              or str(scheme_def.get('name', '')).lower() != 'x-api-key'
          ):
            warnings.append(
                f'tools-list.security names API key scheme "{scheme_name}",'
                ' but tools/list reads API keys only from the "x-api-key"'
                ' header. Define the scheme with "in: header" and "name:'
                ' x-api-key".'
            )
        else:
          root_requirements = _requirement_names(spec.get('security'))
          if not any(
              scheme_name in requirement for requirement in root_requirements
          ):
            errors.append(
                f'tools-list.security names JWT scheme "{scheme_name}", but the'
                ' root "security" list does not reference it. API Gateway'
                f' rejects this config. Add "{scheme_name}: []" to the root'
                ' "security" list (in the same requirement object as an API'
                ' key scheme, if there is one).'
            )
          elif all(
              scheme_name in requirement for requirement in root_requirements
          ):
            warnings.append(
                f'The root "security" list requires "{scheme_name}" on every'
                ' REST operation that does not set its own "security". Tell the'
                ' user that the gateway rejects REST callers without this JWT.'
            )
          else:
            warnings.append(
                f'The root "security" list names "{scheme_name}" as one of'
                ' several alternatives. REST operations that do not set their'
                ' own "security" accept any of the alternatives.'
            )
    else:
      warnings.append(
          'x-google-api-management.mcp does not configure tools-list.security; '
          'tools/list will be unauthenticated.'
      )

  root_backend = spec.get('x-google-backend')
  if isinstance(root_backend, dict):
    errors.append(
        'Root "x-google-backend" must be a string referencing a backend in '
        'x-google-api-management.backends, not an inline OpenAPI 2.0 object.'
    )
  elif (
      isinstance(root_backend, str)
      and backend_names
      and root_backend not in backend_names
  ):
    errors.append(
        f'Root x-google-backend "{root_backend}" is not defined in '
        'x-google-api-management.backends.'
    )

  seen_names: set[str] = set()
  router_operations: list[str] = []
  explicit_opt_in = False
  implicit_tool_count = 0
  paths = spec.get('paths', {})
  if isinstance(paths, dict):
    for path_str, path_item in paths.items():
      if not isinstance(path_item, dict):
        continue
      if 'x-google-mcp-tool' in path_item:
        errors.append(
            f'Path "{path_str}" declares "x-google-mcp-tool" at the path level.'
            ' It must only be specified at the individual operation level.'
        )
      path_parameters = path_item.get('parameters')
      for raw_method, operation in path_item.items():
        method = str(raw_method).lower()
        if method not in _HTTP_METHODS or not isinstance(operation, dict):
          continue
        label = f'{method.upper()} {path_str}'
        if not str(operation.get('operationId') or '').strip():
          errors.append(
              f'Operation {label} has no operationId. API Gateway requires an'
              ' operationId on every operation, with or without MCP.'
          )
        mcp_tool = operation.get('x-google-mcp-tool')
        if 'x-google-model-router' in operation:
          router_operations.append(label)
          if mcp_tool is True or isinstance(mcp_tool, dict):
            explicit_opt_in = True
          continue
        if 'security' in operation:
          operation_or_error = _or_with_api_key_error(
              operation.get('security'), schemes, f'operation {label}'
          )
          if operation_or_error:
            errors.append(operation_or_error)
        operation_backend = operation.get('x-google-backend', root_backend)
        if isinstance(operation.get('x-google-backend'), dict):
          errors.append(
              f'Operation {label} uses an inline "x-google-backend" object'
              ' instead of a string backend name.'
          )
        elif (
            isinstance(operation_backend, str)
            and backend_names
            and operation_backend not in backend_names
        ):
          errors.append(
              f'Operation {label} references undefined backend'
              f' "{operation_backend}".'
          )

        if mcp_tool is not None and not isinstance(mcp_tool, (bool, dict)):
          errors.append(
              f'Operation {label} has invalid x-google-mcp-tool type (must be'
              ' boolean or object).'
          )
          continue
        if mcp_tool is False:
          continue
        explicit = mcp_tool is True or isinstance(mcp_tool, dict)
        if explicit:
          explicit_opt_in = True
        elif not global_mcp_enabled:
          continue

        if method not in _SUPPORTED_MCP_METHODS:
          if explicit:
            errors.append(
                f'Operation {label} explicitly opts into MCP, but HTTP method'
                f' {method.upper()} is not supported (only GET, POST, PUT,'
                ' PATCH, DELETE).'
            )
          continue

        if not operation_backend:
          if explicit:
            errors.append(
                f'Operation {label} opts into MCP, but it has no'
                ' x-google-backend. Each exposed operation needs a backend.'
            )
          else:
            warnings.append(
                f'Operation {label} has no x-google-backend, so it is not'
                ' eligible as an MCP tool.'
            )
          continue

        parameters = []
        for parameter_list in (path_parameters, operation.get('parameters')):
          if isinstance(parameter_list, list):
            parameters.extend(
                _resolve(spec, parameter) for parameter in parameter_list
            )
        for parameter in parameters:
          if not isinstance(parameter, dict):
            continue
          parameter_name = str(parameter.get('name', ''))
          if str(parameter.get('in', '')).lower() == 'header' and (
              parameter_name.lower().startswith('x-google-')
          ):
            errors.append(
                f'Operation {label} binds a header parameter to reserved'
                f' prefix "{parameter_name}".'
            )
          schema = _resolve(spec, parameter.get('schema'))
          if isinstance(schema, dict) and (
              schema.get('type') in ('array', 'object')
              or 'items' in schema
              or 'properties' in schema
          ):
            warnings.append(
                f'Operation {label} parameter "{parameter_name}" is not a'
                ' primitive type. API Gateway supports only primitive types in'
                ' request parameters. Change it to a primitive type, or set'
                ' "x-google-mcp-tool: false" on the operation.'
            )

        if isinstance(mcp_tool, dict) and 'name' in mcp_tool:
          raw_name = mcp_tool['name']
          if not isinstance(raw_name, str) or not _TOOL_NAME_RE.match(raw_name):
            errors.append(
                f'x-google-mcp-tool.name on {label} must be a string that'
                f' matches [A-Za-z0-9_.-]{{1,128}}, got {raw_name!r}.'
            )
            continue
          tool_name = raw_name
        else:
          tool_name = str(operation.get('operationId') or '')
          if not tool_name:
            # Reported above: every operation needs an operationId.
            continue
          if not _TOOL_NAME_RE.match(tool_name):
            errors.append(
                f'Tool name "{tool_name}" (the operationId of {label}) does not'
                ' match [A-Za-z0-9_.-]{1,128}. Set x-google-mcp-tool.name.'
            )
        if tool_name in seen_names:
          errors.append(f'Duplicate MCP tool name "{tool_name}".')
        seen_names.add(tool_name)

        override_description = (
            mcp_tool.get('description') if isinstance(mcp_tool, dict) else None
        )
        tool_description = str(
            override_description
            or operation.get('description')
            or operation.get('summary')
            or ''
        ).strip()
        if not tool_description:
          errors.append(
              f'Exposed MCP operation {label} ("{tool_name}") has no'
              ' resolvable description or summary.'
          )

        responses = operation.get('responses', {})
        if isinstance(responses, dict) and (
            '204' in responses or 204 in responses
        ):
          warnings.append(
              f'Operation {label} ("{tool_name}") declares an HTTP 204'
              ' response. MCP does not support operations that return an empty'
              ' body. Return 200 with a JSON body, or set'
              ' "x-google-mcp-tool: false".'
          )

        if not explicit:
          implicit_tool_count += 1
        exposed_tools.append({
            'name': tool_name,
            'method': method.upper(),
            'path': path_str,
        })

  if global_mcp_enabled or explicit_opt_in:
    for label in router_operations:
      errors.append(
          f'Operation {label} uses "x-google-model-router". MCP and model'
          ' routing cannot be used in the same API configuration.'
      )
    if 'ai' in management and not router_operations:
      warnings.append(
          '"x-google-api-management.ai" configures model routing. MCP and model'
          ' routing cannot be used in the same API configuration. Remove the'
          ' "ai" block, or move model routing to a separate API config.'
      )
  if isinstance(mcp_config, dict) and implicit_tool_count:
    warnings.append(
        'x-google-api-management.mcp is an object, so MCP also exposes'
        f' {implicit_tool_count} operation(s) that do not set'
        ' x-google-mcp-tool. Check exposed_tools, and set'
        ' "x-google-mcp-tool: false" on operations that agents must not call.'
    )

  if not exposed_tools:
    warnings.append(
        'No operations resolved as exposed MCP tools; /mcp will expose 0 tools.'
    )
  elif len(exposed_tools) > _MAX_TOOLS_PER_GATEWAY:
    errors.append(
        f'This file exposes {len(exposed_tools)} MCP tools. A gateway serves at'
        f' most {_MAX_TOOLS_PER_GATEWAY:,} MCP tools.'
    )

  return errors, warnings, exposed_tools


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(
      description=(
          'Validate an OpenAPI specification against Google Cloud API Gateway '
          'MCP Public Preview constraints.'
      )
  )
  parser.add_argument(
      '--spec',
      required=True,
      help='Path to the OpenAPI YAML or JSON specification file to validate.',
  )
  args = parser.parse_args(argv)

  try:
    spec = _load_spec(args.spec)
    errors, warnings, exposed_tools = validate_mcp_spec(spec)
  except (OSError, RuntimeError, ValueError) as exc:
    print(f'Error: {exc}', file=sys.stderr)
    return 2

  status = 'FAIL' if errors else 'PASS'
  report = {
      'status': status,
      'spec': args.spec,
      'exposed_tool_count': len(exposed_tools),
      'exposed_tools': exposed_tools,
      'errors': errors,
      'warnings': warnings,
  }
  print(json.dumps(report, indent=2))
  if errors:
    print(
        f'MCP OpenAPI validation failed with {len(errors)} error(s).',
        file=sys.stderr,
    )
    return 1
  return 0


if __name__ == '__main__':
  sys.exit(main())

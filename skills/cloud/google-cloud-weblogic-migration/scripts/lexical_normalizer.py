"""Lexical normalizer and token-classified scanner for Java source code analysis.

This module implements an in-memory, dependency-free lexical tokenizer and
normalizer for legacy Java and WebLogic source files (`.java`, `.ejb`, `.jws`).
It solves regex parsing vulnerabilities caused by multi-line formatting, line
breaks, string literal traps, and comment contamination without requiring heavy
AST parsers.

Specifically, it scans code in a single pass to separate text into isolated
buckets:
- Code text (comments removed, whitespace collapsed, safe for keyword and
annotation scanning).
- Javadoc comments (preserved intact to extract WebLogic `@ejbgen` and
`@target-ejb` annotations).
- String literals (extracted and automatically merging multi-line string
concatenations `+` for SQL query scanning).
- Ordinary comments (`//` and `/*...*/` stripped safely to prevent false
positive imports).
"""

import os
import re

# =====================================================================
# LEXICAL REGEX PATTERNS AND CONSTANTS
# =====================================================================

# Master regex to tokenize Java code into Javadoc, block comments, line
# comments, text blocks, strings, and chars.
JAVA_LEXER_REGEX = re.compile(
    r'(?P<javadoc>/\*\*.*?\*/)|'
    r'(?P<block_comment>/\*.*?\*/)|'
    r'(?P<line_comment>//[^\r\n]*)|'
    r'(?P<text_block>""".*?""")|'
    r'(?P<string>"(?:\\.|[^"\\])*")|'
    r'(?P<char>\'(?:\\.|[^\'\\])*\')',
    re.DOTALL,
)


# =====================================================================
# CORE TOKENIZER AND NORMALIZATION ENGINE
# =====================================================================


def tokenize_java_content(content):
  """Tokenizes raw Java source content into isolated lexical buckets (code, javadocs, strings).

  Collapses multi-line whitespace and automatically merges concatenated string
  literals.

  Args:
      content (str): Raw Java source file text.

  Returns:
      dict: A dictionary containing:
          - 'code_text_with_strings': Clean code with comments stripped and
          whitespace collapsed, strings kept.
          - 'code_text_no_strings': Clean code with comments and strings
          stripped, whitespace collapsed.
          - 'javadocs': List of Javadoc comment contents (with /** and */
          stripped).
          - 'string_literals': List of extracted string literals, merging
          multi-line '+' concatenations.
  """
  code_with_strings_parts = []
  code_no_strings_parts = []
  javadocs = []
  string_literals = []

  last_idx = 0
  last_token_was_string = False

  for match in JAVA_LEXER_REGEX.finditer(content):
    # 1. Process unmatched intervening text as ordinary code
    intervening_code = content[last_idx : match.start()]
    if intervening_code:
      code_with_strings_parts.append(intervening_code)
      code_no_strings_parts.append(intervening_code)

    # Check if the intervening code was strictly whitespace and a string
    # concatenation '+'
    is_concat = last_token_was_string and bool(
        re.match(r'^\s*\+\s*$', intervening_code)
    )
    last_token_was_string = False

    # 2. Process the matched token bucket
    if match.group('javadoc'):
      raw_javadoc = match.group('javadoc')
      # Strip /** and */ and clean leading asterisks on wrapped lines
      inner = raw_javadoc[3:-2]
      cleaned_lines = [
          re.sub(r'^\s*\*\s?', '', line) for line in inner.splitlines()
      ]
      javadocs.append('\n'.join(cleaned_lines).strip())
      # Replace comment with space in code text to prevent token merging
      code_with_strings_parts.append(' ')
      code_no_strings_parts.append(' ')

    elif match.group('block_comment') or match.group('line_comment'):
      # Strip ordinary comments, replace with space
      code_with_strings_parts.append(' ')
      code_no_strings_parts.append(' ')

    elif match.group('text_block') or match.group('string'):
      raw_str = match.group(0)
      if raw_str.startswith('"""'):
        val = raw_str[3:-3]
      else:
        # Strip quotes and unescape basic escape sequences
        val = raw_str[1:-1].replace(r'\"', '"').replace(r'\\', '\\')

      if is_concat and string_literals:
        string_literals[-1] += val
      else:
        string_literals.append(val)

      last_token_was_string = True
      code_with_strings_parts.append(raw_str)
      code_no_strings_parts.append('""')

    elif match.group('char'):
      code_with_strings_parts.append(match.group(0))
      code_no_strings_parts.append("''")

    last_idx = match.end()

  # Append remaining trailing code
  trailing_code = content[last_idx:]
  if trailing_code:
    code_with_strings_parts.append(trailing_code)
    code_no_strings_parts.append(trailing_code)

  # Collapse consecutive whitespace and line breaks into single spaces for
  # robust regex matching
  code_with_strings = re.sub(
      r'\s+', ' ', ''.join(code_with_strings_parts)
  ).strip()
  code_no_strings = re.sub(r'\s+', ' ', ''.join(code_no_strings_parts)).strip()

  return {
      'code_text_with_strings': code_with_strings,
      'code_text_no_strings': code_no_strings,
      'javadocs': javadocs,
      'string_literals': string_literals,
  }


# =====================================================================
# FILE HELPERS AND CONVENIENCE WRAPPERS
# =====================================================================


def tokenize_java_file(file_path):
  """Reads a Java source file from disk and returns its tokenized lexical buckets.

  Args:
      file_path (str): Absolute or relative path to the Java source file.

  Returns:
      dict: The tokenized buckets dictionary, or an empty default dict on read
      failure.
  """
  try:
    with open(file_path, 'r', errors='ignore') as f:
      content = f.read()
    return tokenize_java_content(content)
  except Exception:
    return {
        'code_text_with_strings': '',
        'code_text_no_strings': '',
        'javadocs': [],
        'string_literals': [],
    }


def clean_java_code(content):
  """Convenience helper that strips comments and collapses whitespace for fast pattern counting.

  Args:
      content (str): Raw Java source text or file path.

  Returns:
      str: Cleaned code text with string literals preserved and multi-line
      formatting normalized.
  """
  if os.path.exists(content) and os.path.isfile(content):
    tokens = tokenize_java_file(content)
  else:
    tokens = tokenize_java_content(content)
  return tokens['code_text_with_strings']


def get_package_name(content_or_path):
  """Extracts the package declaration namespace from a file path or raw Java content string.

  Immune to commented-out package statements or multi-line formatting.

  Args:
      content_or_path (str): File path ending in .java/.ejb/.jws or raw source
        string.

  Returns:
      str | None: The extracted package FQCN (e.g. 'com.medimed.service') or
      None.
  """
  if os.path.exists(content_or_path) and os.path.isfile(content_or_path):
    tokens = tokenize_java_file(content_or_path)
  else:
    tokens = tokenize_java_content(content_or_path)

  match = re.search(
      r'\bpackage\s+([a-zA-Z0-9_\.]+)\s*;', tokens['code_text_no_strings']
  )
  if match:
    return match.group(1)
  return None

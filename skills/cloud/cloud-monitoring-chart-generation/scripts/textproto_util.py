"""Lightweight grammar-based textproto parser and SDUI Widget models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimeSeriesQuery:
  prometheus_query: str = ""
  unit_override: str = ""


@dataclass
class DataSet:
  time_series_query: TimeSeriesQuery = field(default_factory=TimeSeriesQuery)
  plot_type: str = "LINE"
  target_axis: str = "Y1"


@dataclass
class YAxis:
  label: str = ""
  scale: str = "LINEAR"


@dataclass
class ChartOptions:
  mode: str = "COLOR"


@dataclass
class XyChart:
  chart_options: ChartOptions = field(default_factory=ChartOptions)
  data_sets: list[DataSet] = field(default_factory=list)
  y_axis: YAxis = field(default_factory=YAxis)


@dataclass
class Widget:
  title: str = ""
  xy_chart: XyChart | None = None

  def HasField(self, field_name: str) -> bool:
    return getattr(self, field_name, None) is not None


def tokenize_textproto(text: str) -> list[tuple[str, str]]:
  """Tokenizes textproto string into (token_type, value) tuples."""
  tokens = []
  i = 0
  n = len(text)
  while i < n:
    c = text[i]
    if c.isspace():
      i += 1
      continue
    if c == "#":
      while i < n and text[i] != "\n":
        i += 1
      continue
    if c in ("{", "}", ":", ";", ","):
      if c in ("{", "}", ":"):
        tokens.append((c, c))
      i += 1
      continue
    if c in ('"', "'"):
      quote = c
      j = i + 1
      val_chars = []
      while j < n and text[j] != quote:
        if text[j] == "\\" and j + 1 < n:
          val_chars.append(text[j + 1])
          j += 2
        else:
          val_chars.append(text[j])
          j += 1
      tokens.append(("STR", "".join(val_chars)))
      i = j + 1
      continue
    j = i
    while (
        j < n
        and not text[j].isspace()
        and text[j] not in ("{", "}", ":", ";", ",", "#")
    ):
      j += 1
    tokens.append(("SYM", text[i:j]))
    i = j
  return tokens


def parse_textproto_tokens(
    tokens: list[tuple[str, str]], idx: int = 0
) -> tuple[dict[str, Any], int]:
  """Parses token stream into a nested dictionary structure similar to json.loads."""
  obj: dict[str, Any] = {}
  n = len(tokens)
  while idx < n:
    ttype, tval = tokens[idx]
    if ttype == "}":
      return obj, idx + 1
    if ttype == "SYM":
      key = tval
      idx += 1
      if idx < n and tokens[idx][0] == ":":
        idx += 1
      if idx < n and tokens[idx][0] == "{":
        nested_obj, idx = parse_textproto_tokens(tokens, idx + 1)
        val = nested_obj
      elif idx < n and tokens[idx][0] in ("STR", "SYM"):
        val = tokens[idx][1]
        idx += 1
      else:
        continue

      if key in obj:
        if not isinstance(obj[key], list):
          obj[key] = [obj[key]]
        obj[key].append(val)
      else:
        obj[key] = val
    else:
      idx += 1
  return obj, idx


def dict_to_widget(data: dict[str, Any]) -> Widget:
  """Converts a parsed textproto dictionary into a structured Widget hierarchy."""
  if "widget" in data and isinstance(data["widget"], dict):
    data = data["widget"]

  title = str(data.get("title", ""))

  xy_data = data.get("xy_chart")
  if not xy_data or not isinstance(xy_data, dict):
    return Widget(title=title, xy_chart=None)

  opts_data = xy_data.get("chart_options", {})
  mode = (
      str(opts_data.get("mode", "COLOR"))
      if isinstance(opts_data, dict)
      else "COLOR"
  )
  chart_options = ChartOptions(mode=mode)

  yaxis_data = xy_data.get("y_axis", {})
  if isinstance(yaxis_data, dict):
    label = str(yaxis_data.get("label", ""))
    scale = str(yaxis_data.get("scale", "LINEAR"))
  else:
    label, scale = "", "LINEAR"
  y_axis = YAxis(label=label, scale=scale)

  raw_ds_list = xy_data.get("data_sets", [])
  if isinstance(raw_ds_list, dict):
    raw_ds_list = [raw_ds_list]
  elif not isinstance(raw_ds_list, list):
    raw_ds_list = []

  data_sets: list[DataSet] = []
  for ds_dict in raw_ds_list:
    if not isinstance(ds_dict, dict):
      continue
    ts_dict = ds_dict.get("time_series_query", {})
    if isinstance(ts_dict, dict):
      promql = str(ts_dict.get("prometheus_query", ""))
      unit = str(ts_dict.get("unit_override", ""))
    else:
      promql, unit = "", ""
    ts_query = TimeSeriesQuery(prometheus_query=promql, unit_override=unit)
    plot_type = str(ds_dict.get("plot_type", "LINE"))
    target_axis = str(ds_dict.get("target_axis", "Y1"))
    data_sets.append(
        DataSet(
            time_series_query=ts_query,
            plot_type=plot_type,
            target_axis=target_axis,
        )
    )

  xy_chart = XyChart(
      chart_options=chart_options,
      data_sets=data_sets,
      y_axis=y_axis,
  )
  return Widget(title=title, xy_chart=xy_chart)


def parse_and_validate_widget(text: str) -> Widget:
  """Parses a textproto string into a Widget message hierarchy."""
  tokens = tokenize_textproto(text)
  raw_dict, _ = parse_textproto_tokens(tokens)
  return dict_to_widget(raw_dict)

#!/usr/bin/env python3
"""Unit tests for db_output_match_analyzer."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_output_match_analyzer  # pylint: disable=g-import-not-at-top
import db_resources_loader  # pylint: disable=g-import-not-at-top


def _fw_name(fw_id: str) -> str:
  return f"organizations/123/locations/global/frameworks/{fw_id}"


def _cc_name(cc_id: str) -> str:
  return f"organizations/123/locations/global/cloudControls/{cc_id}"


_REGULATORY_FRAMEWORK_PARAMETER_SPEC = {
    "name": "framework",
    "valueType": "STRING",
    "isRequired": True,
    "validation": {
        "allowedValues": {
            "values": [
                {"stringValue": "DATA_BOUNDARY_FOR_FEDRAMP_HIGH"},
                {"stringValue": "DATA_BOUNDARY_FOR_IL4"},
            ]
        }
    },
}


def _make_sample_resources() -> db_resources_loader.DBResourcesStore:
  return db_resources_loader.DBResourcesStore(
      last_synced_epoch=1_790_000_000.0,
      frameworks={
          "builtin-australia-data-boundary": {
              "name": _fw_name("builtin-australia-data-boundary"),
              "displayName": "Australia Data Boundary",
              "description": "Enforces Australia regional data residency.",
              "majorRevisionId": "4",
              "cloudControlDetails": [
                  {
                      "name": _cc_name(
                          "builtin-cloud-logging-storage-locations"
                      ),
                      "majorRevisionId": "3",
                      "parameters": [{
                          "name": "cloudLoggingStorageLocations",
                          "parameterValue": {
                              "stringListValue": {
                                  "values": [
                                      "australia-southeast1",
                                      "australia-southeast2",
                                  ]
                              }
                          },
                      }],
                  },
                  {
                      "name": _cc_name("builtin-require-cmek"),
                      "majorRevisionId": "2",
                  },
              ],
          },
          "builtin-il4": {
              "name": _fw_name("builtin-il4"),
              "displayName": "Impact Level 4 (IL4)",
              "majorRevisionId": "2",
              "cloudControlDetails": [{
                  "name": _cc_name(
                      "builtin-gemini-enterprise-regulatory-settings"
                  ),
                  "majorRevisionId": "2",
              }],
          },
          "builtin-il5": {
              "name": _fw_name("builtin-il5"),
              "displayName": "Impact Level 5 (IL5)",
              "majorRevisionId": "2",
              "cloudControlDetails": [
                  {
                      "name": _cc_name(
                          "builtin-iam-disable-service-account-key-creation"
                      ),
                      "majorRevisionId": "3",
                  },
                  {
                      "name": _cc_name(
                          "builtin-gemini-enterprise-regulatory-settings"
                      ),
                      "majorRevisionId": "2",
                  },
              ],
          },
          "builtin-japan-data-boundary": {
              "name": _fw_name("builtin-japan-data-boundary"),
              "displayName": "Japan Data Boundary",
              "majorRevisionId": "1",
              "cloudControlDetails": [{
                  "name": _cc_name("builtin-only-in-japan"),
                  "majorRevisionId": "1",
              }],
          },
      },
      cloud_controls={
          "builtin-cloud-logging-storage-locations": {
              "name": _cc_name("builtin-cloud-logging-storage-locations"),
              "displayName": "Cloud Logging Storage Locations",
              "parameterSpec": [{
                  "name": "cloudLoggingStorageLocations",
                  "valueType": "STRINGLIST",
                  "isRequired": True,
              }],
              "rules": [{
                  "ruleActionTypes": ["RULE_ACTION_TYPE_PREVENTIVE"],
              }],
          },
          "builtin-require-cmek": {
              "name": _cc_name("builtin-require-cmek"),
              "displayName": "Require CMEK",
              "rules": [{
                  "celExpression": {"expression": "has(resource.kmsKey)"},
                  "ruleActionTypes": ["RULE_ACTION_TYPE_DETECTIVE"],
              }],
          },
          "builtin-iam-disable-service-account-key-creation": {
              "name": _cc_name(
                  "builtin-iam-disable-service-account-key-creation"
              ),
              "displayName": "Disable Service Account Key Creation",
              "description": (
                  "Prevents creation of user-managed service account keys."
              ),
              "relatedFrameworks": ["builtin-il5"],
              "rules": [
                  {"ruleActionTypes": ["RULE_ACTION_TYPE_PREVENTIVE"]},
              ],
          },
          "builtin-gemini-enterprise-regulatory-settings": {
              "name": _cc_name("builtin-gemini-enterprise-regulatory-settings"),
              "displayName": "Regulatory Framework",
              "relatedFrameworks": ["builtin-il4", "builtin-il5"],
              "parameterSpec": [_REGULATORY_FRAMEWORK_PARAMETER_SPEC],
              "rules": [
                  {"ruleActionTypes": ["RULE_ACTION_TYPE_PREVENTIVE"]},
              ],
          },
          "builtin-only-in-japan": {
              "name": _cc_name("builtin-only-in-japan"),
              "displayName": "Japan Specific Control",
              "relatedFrameworks": ["builtin-japan-data-boundary"],
              "rules": [
                  {"ruleActionTypes": ["RULE_ACTION_TYPE_PREVENTIVE"]},
              ],
          },
          # Not part of any framework in this sample.
          "builtin-in-no-framework": {
              "name": _cc_name("builtin-in-no-framework"),
              "displayName": "Control In No Framework",
              "rules": [
                  {"ruleActionTypes": ["RULE_ACTION_TYPE_DETECTIVE"]},
              ],
          },
      },
  )


def _intent(*requirements) -> db_output_match_analyzer.NavigatorIntentSpec:
  return db_output_match_analyzer.NavigatorIntentSpec(
      source_type="DIRECT_NL",
      organization_id="123",
      user_prompt="test",
      requirements=list(requirements),
  )


def _req(
    text: str, importance: str = "MAJOR"
) -> db_output_match_analyzer.RequirementItem:
  return db_output_match_analyzer.RequirementItem(
      requirement=text, importance=importance
  )


def _fw(fw_id: str, *satisfied: str) -> db_output_match_analyzer.MatchedFW:
  return db_output_match_analyzer.MatchedFW(
      fw_id=fw_id,
      fw_type="BUILT_IN",
      major_revision_id=1,
      display_name=fw_id,
      satisfied_requirements=list(satisfied),
  )


def _cc(
    cc_id: str, requirement: str = "", importance: str = "MAJOR"
) -> db_output_match_analyzer.MatchedCC:
  return db_output_match_analyzer.MatchedCC(
      cc_id=cc_id,
      cc_type="BUILT_IN",
      display_name=cc_id,
      requirement=requirement,
      importance=importance,
  )


class DBOutputMatchAnalyzerTest(unittest.TestCase):

  def test_omits_underlying_ccs_by_default_and_includes_when_requested(self):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt="Australia data residency with CMEK",
        requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Store logs in Australia regions",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Enforce CMEK encryption",
                importance="MAJOR",
            ),
        ],
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-australia-data-boundary",
                fw_type="BUILT_IN",
                major_revision_id=1,
                display_name="Australia Data Boundary",
                match_rationale=(
                    "Enforces Australia regional data residency and CMEK."
                ),
                satisfied_requirements=[
                    "Store logs in Australia regions",
                    "Enforce CMEK encryption",
                ],
            )
        ]
    )

    default_report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertIsNone(default_report.matched_frameworks[0].underlying_ccs)
    self.assertNotIn(
        "underlying_ccs", default_report.to_dict()["matched_frameworks"][0]
    )
    self.assertIsNone(default_report.custom_authoring_handoff)

    expanded_report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources, include_underlying_ccs=True
    )
    fw = expanded_report.matched_frameworks[0]
    self.assertIsNotNone(fw.underlying_ccs)
    self.assertEqual(
        [c.cc_id for c in fw.underlying_ccs or []],
        [
            "builtin-cloud-logging-storage-locations",
            "builtin-require-cmek",
        ],
    )

  def test_multiple_ccs_sharing_common_builtin_fw_do_not_suggest_custom_fw(
      self,
  ):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt=(
            "AU data boundary + SA key creation disabled + Gemini settings"
        ),
        requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Australia regional data residency",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Disable service account key creation",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Gemini regulatory settings",
                importance="MAJOR",
            ),
        ],
    )
    # Both standalone CCs are in builtin-il5 -> common_builtin_frameworks has
    # builtin-il5, so suggest_custom_framework_for_additional_ccs is False.
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-australia-data-boundary",
                fw_type="BUILT_IN",
                major_revision_id=4,
                display_name="Australia Data Boundary",
                satisfied_requirements=["Australia regional data residency"],
            )
        ],
        standalone_matched_ccs=[
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-iam-disable-service-account-key-creation",
                cc_type="BUILT_IN",
                display_name="Disable Service Account Key Creation",
                requirement="Disable service account key creation",
                importance="MAJOR",
            ),
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-gemini-enterprise-regulatory-settings",
                cc_type="BUILT_IN",
                display_name="Regulatory Framework",
                requirement="Gemini regulatory settings",
                importance="MAJOR",
                selected_parameters={"framework": "DATA_BOUNDARY_FOR_IL4"},
            ),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertEqual(
        [f.fw_id for f in report.common_builtin_frameworks_for_additional_ccs],
        ["builtin-il5"],
    )
    self.assertFalse(report.suggest_custom_framework_for_additional_ccs)
    self.assertIsNone(report.custom_authoring_handoff)

  def test_disjoint_multiple_ccs_with_no_common_builtin_fw_suggests_custom_fw(
      self,
  ):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt=(
            "AU data boundary + SA key creation disabled + Japan control"
        ),
        requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Australia regional data residency",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Disable service account key creation",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Japan specific control",
                importance="MAJOR",
            ),
        ],
    )
    # One CC is only in builtin-il5, the other is only in
    # builtin-japan-data-boundary. No single built-in FW contains both ->
    # suggest_custom_framework_for_additional_ccs is True.
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-australia-data-boundary",
                fw_type="BUILT_IN",
                major_revision_id=4,
                display_name="Australia Data Boundary",
                satisfied_requirements=["Australia regional data residency"],
            )
        ],
        standalone_matched_ccs=[
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-iam-disable-service-account-key-creation",
                cc_type="BUILT_IN",
                display_name="Disable Service Account Key Creation",
                requirement="Disable service account key creation",
                importance="MAJOR",
            ),
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-only-in-japan",
                cc_type="BUILT_IN",
                display_name="Japan Specific Control",
                requirement="Japan specific control",
                importance="MAJOR",
            ),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertEqual(report.common_builtin_frameworks_for_additional_ccs, [])
    self.assertTrue(report.suggest_custom_framework_for_additional_ccs)
    self.assertIsNotNone(report.custom_authoring_handoff)

  def test_single_additional_cc_in_no_builtin_fw_suggests_custom_fw(self):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Australia regional data residency"),
        _req("Detect the control that no built-in framework has"),
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw(
                "builtin-australia-data-boundary",
                "Australia regional data residency",
            )
        ],
        standalone_matched_ccs=[
            _cc(
                "builtin-in-no-framework",
                requirement="Detect the control that no built-in framework has",
            )
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(
        [c.cc_id for c in report.additional_cloud_controls],
        ["builtin-in-no-framework"],
    )
    self.assertEqual(
        report.additional_cloud_controls[0].part_of_builtin_frameworks, []
    )
    self.assertEqual(report.common_builtin_frameworks_for_additional_ccs, [])
    self.assertTrue(report.suggest_custom_framework_for_additional_ccs)
    # The match is 100 percent, so only the additional control asks for it.
    self.assertEqual(report.match_score_percentage, 100.0)
    self.assertFalse(report.suggest_custom_resources_for_unmet_requirements)
    handoff = report.custom_authoring_handoff
    self.assertIsNotNone(handoff)
    self.assertEqual(
        [c["cc_id"] for c in handoff["additional_existing_ccs_to_bundle"]],
        ["builtin-in-no-framework"],
    )

  def test_single_additional_cc_in_a_builtin_fw_does_not_suggest_custom_fw(
      self,
  ):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Australia regional data residency"),
        _req("Japan specific control"),
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw(
                "builtin-australia-data-boundary",
                "Australia regional data residency",
            )
        ],
        standalone_matched_ccs=[
            _cc("builtin-only-in-japan", requirement="Japan specific control")
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(
        [f.fw_id for f in report.common_builtin_frameworks_for_additional_ccs],
        ["builtin-japan-data-boundary"],
    )
    self.assertFalse(report.suggest_custom_framework_for_additional_ccs)
    self.assertIsNone(report.custom_authoring_handoff)

  def test_standalone_cc_already_in_a_selected_fw_is_dropped(self):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Impact Level 5 compliance"),
        _req("Disable service account key creation"),
    )
    # The control is in builtin-il5, which is selected, so it is not an
    # additional one, and its requirement counts as met.
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[_fw("builtin-il5", "Impact Level 5 compliance")],
        standalone_matched_ccs=[
            _cc(
                "builtin-iam-disable-service-account-key-creation",
                requirement="Disable service account key creation",
            )
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(report.additional_cloud_controls, [])
    self.assertEqual(report.common_builtin_frameworks_for_additional_ccs, [])
    self.assertFalse(report.suggest_custom_framework_for_additional_ccs)
    self.assertEqual(report.unmet_major_requirements, [])
    self.assertEqual(report.match_score_percentage, 100.0)
    self.assertIsNone(report.custom_authoring_handoff)

  def test_standalone_cc_is_still_validated_before_it_is_dropped(self):
    resources = _make_sample_resources()
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[_fw("builtin-il5")],
        standalone_matched_ccs=[
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-gemini-enterprise-regulatory-settings",
                cc_type="BUILT_IN",
                display_name="Regulatory Framework",
                selected_parameters={"framework": "INVALID_ENUM_VALUE"},
            )
        ],
    )

    with self.assertRaisesRegex(
        ValueError, "Invalid value 'INVALID_ENUM_VALUE'"
    ):
      db_output_match_analyzer.analyze_output_matches(
          _intent(), match_result, resources
      )

  def test_ignores_minor_unmet_and_minor_standalone_ccs_when_builtin_fw_matched(
      self,
  ):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt="AU data residency with minor preferences",
        requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Australia regional data residency",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Optional SA key rotation preference",
                importance="MINOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Optional custom audit label",
                importance="MINOR",
            ),
        ],
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-australia-data-boundary",
                fw_type="BUILT_IN",
                major_revision_id=4,
                display_name="Australia Data Boundary",
                satisfied_requirements=["Australia regional data residency"],
            )
        ],
        standalone_matched_ccs=[
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-iam-disable-service-account-key-creation",
                cc_type="BUILT_IN",
                display_name="Disable Service Account Key Creation",
                requirement="Optional SA key rotation preference",
                importance="MINOR",
            )
        ],
        unmatched_requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Optional custom audit label",
                importance="MINOR",
            )
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertEqual(len(report.additional_cloud_controls), 0)
    self.assertEqual(len(report.unmet_major_requirements), 0)
    self.assertIsNone(report.custom_authoring_handoff)

  def test_surfaces_unmet_major_requirement_and_builds_custom_handoff(self):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt="AU data boundary + custom AlloyDB port 5433",
        requirements=[
            db_output_match_analyzer.RequirementItem(
                requirement="Australia regional data residency",
                importance="MAJOR",
            ),
            db_output_match_analyzer.RequirementItem(
                requirement="Restrict AlloyDB to custom non-default port 5433",
                importance="MAJOR",
                suggested_custom_cc_summary=(
                    "Enforce port 5433 on alloydb.googleapis.com/Cluster."
                ),
            ),
        ],
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-australia-data-boundary",
                fw_type="BUILT_IN",
                major_revision_id=4,
                display_name="Australia Data Boundary",
                satisfied_requirements=["Australia regional data residency"],
            )
        ]
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertEqual(
        [r.requirement for r in report.unmet_major_requirements],
        ["Restrict AlloyDB to custom non-default port 5433"],
    )
    self.assertIsNotNone(report.custom_authoring_handoff)
    self.assertEqual(report.match_score_percentage, 50.0)

  def test_score_ignores_unmet_requirements_that_are_not_in_the_intent(self):
    resources = _make_sample_resources()
    intent = _intent(_req("Requirement one"), _req("Requirement two"))
    # The agent put three requirements that the customer never stated into
    # `unmatched_requirements`; they must not push the score below 100.
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw("builtin-il4", "Requirement one", "Requirement two")
        ],
        unmatched_requirements=[
            _req("Invented requirement A"),
            _req("Invented requirement B"),
            _req("Invented requirement C"),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(report.match_score_percentage, 100.0)
    # They stay in the unmet list, but the match is still 100 percent, so no
    # custom resources are suggested and there is no hand-off.
    self.assertEqual(len(report.unmet_major_requirements), 3)
    self.assertFalse(report.suggest_custom_resources_for_unmet_requirements)
    self.assertIsNone(report.custom_authoring_handoff)

  def test_score_is_between_zero_and_one_hundred(self):
    resources = _make_sample_resources()
    intent = _intent(_req("Requirement one"), _req("Requirement two"))
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[_fw("builtin-il4", "Requirement two")],
        unmatched_requirements=[_req("Requirement one")],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )
    self.assertEqual(report.match_score_percentage, 50.0)

    nothing_met = db_output_match_analyzer.analyze_output_matches(
        intent, db_output_match_analyzer.CatalogMatchResult(), resources
    )
    self.assertEqual(nothing_met.match_score_percentage, 0.0)

  def test_matched_frameworks_are_sorted_from_best_to_weakest_match(self):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Requirement one"),
        _req("Requirement two"),
        _req("Requirement three"),
        _req("Requirement four"),
    )
    # The agent lists the Frameworks in another order than their match.
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw("builtin-il4", "Requirement one"),
            _fw(
                "builtin-il5",
                "Requirement one",
                "Requirement two",
                "Requirement three",
            ),
            _fw(
                "builtin-japan-data-boundary",
                "Requirement one",
                "Requirement two",
            ),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(
        [f.fw_id for f in report.matched_frameworks],
        ["builtin-il5", "builtin-japan-data-boundary", "builtin-il4"],
    )
    self.assertEqual(
        [f.match_percentage for f in report.matched_frameworks],
        [75.0, 50.0, 25.0],
    )
    self.assertEqual(
        [f["match_percentage"] for f in report.to_dict()["matched_frameworks"]],
        [75.0, 50.0, 25.0],
    )
    # The hand-off lists the base Frameworks in the same order.
    self.assertEqual(
        report.custom_authoring_handoff["base_frameworks"],
        ["builtin-il5", "builtin-japan-data-boundary", "builtin-il4"],
    )

  def test_frameworks_with_the_same_match_keep_their_selection_order(self):
    resources = _make_sample_resources()
    intent = _intent(_req("Requirement one"), _req("Requirement two"))
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw("builtin-il5", "Requirement one"),
            _fw("builtin-il4", "Requirement two"),
            _fw(
                "builtin-japan-data-boundary",
                "Requirement one",
                "Requirement two",
            ),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(
        [f.fw_id for f in report.matched_frameworks],
        ["builtin-japan-data-boundary", "builtin-il5", "builtin-il4"],
    )

  def test_framework_percentage_ignores_requirements_outside_the_intent(self):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Requirement one"),
        _req("Requirement two"),
        _req("Optional preference", importance="MINOR"),
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            # The text of the second requirement differs in case and spaces
            # only. The MINOR requirement and the unknown text do not count.
            _fw(
                "builtin-il4",
                "Requirement one",
                "  REQUIREMENT TWO ",
                "Optional preference",
                "Text the customer never stated",
            ),
            _fw("builtin-il5", "Requirement one"),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(
        [(f.fw_id, f.match_percentage) for f in report.matched_frameworks],
        [("builtin-il4", 100.0), ("builtin-il5", 50.0)],
    )

  def test_framework_percentage_is_100_when_the_intent_has_no_major(self):
    resources = _make_sample_resources()
    intent = _intent(_req("Optional preference", importance="MINOR"))
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[_fw("builtin-il4")],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    self.assertEqual(report.matched_frameworks[0].match_percentage, 100.0)
    self.assertEqual(report.match_score_percentage, 100.0)

  def test_a_framework_is_kept_whatever_its_match_percentage(self):
    resources = _make_sample_resources()
    intent = _intent(
        _req("Requirement one"),
        _req("Requirement two"),
        _req("Requirement three"),
        _req("Requirement four"),
        _req("Requirement five"),
    )
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            _fw("builtin-il5"),
            _fw("builtin-il4", "Requirement one"),
        ],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    # Neither Framework is dropped, not even the one with 0 percent.
    self.assertEqual(
        [(f.fw_id, f.match_percentage) for f in report.matched_frameworks],
        [("builtin-il4", 20.0), ("builtin-il5", 0.0)],
    )
    # Custom resources are offered in addition to them.
    self.assertTrue(report.suggest_custom_resources_for_unmet_requirements)

  def test_a_match_percentage_in_the_input_is_ignored(self):
    resources = _make_sample_resources()
    match_result = db_output_match_analyzer.CatalogMatchResult.from_dict({
        "selected_frameworks": [{
            "fw_id": "builtin-il4",
            "satisfied_requirements": ["Requirement one"],
            "match_percentage": 99.0,
        }]
    })

    report = db_output_match_analyzer.analyze_output_matches(
        _intent(_req("Requirement one"), _req("Requirement two")),
        match_result,
        resources,
    )

    self.assertEqual(report.matched_frameworks[0].match_percentage, 50.0)

  def test_custom_resources_are_suggested_only_below_eighty_percent(self):
    resources = _make_sample_resources()
    # (MAJOR requirements in the intent, how many the Framework satisfies,
    # the expected overall match, whether custom resources are suggested)
    cases = [
        (10, 10, 100.0, False),
        (10, 9, 90.0, False),
        (5, 4, 80.0, False),
        (24, 19, 79.17, True),
        (4, 3, 75.0, True),
        (5, 3, 60.0, True),
        (3, 0, 0.0, True),
    ]
    for total, met, expected_match, expected_suggestion in cases:
      with self.subTest(total=total, met=met):
        texts = [f"Requirement {i}" for i in range(total)]
        match_result = db_output_match_analyzer.CatalogMatchResult(
            selected_frameworks=[_fw("builtin-il4", *texts[:met])],
        )

        report = db_output_match_analyzer.analyze_output_matches(
            _intent(*[_req(text) for text in texts]), match_result, resources
        )

        self.assertEqual(report.match_score_percentage, expected_match)
        self.assertEqual(
            report.suggest_custom_resources_for_unmet_requirements,
            expected_suggestion,
        )
        # The Framework is recommended in every case.
        self.assertEqual(
            [f.fw_id for f in report.matched_frameworks], ["builtin-il4"]
        )
        # The unmet requirements are always reported; only the suggestion
        # and the hand-off depend on the threshold.
        self.assertEqual(len(report.unmet_major_requirements), total - met)
        self.assertEqual(
            report.custom_authoring_handoff is not None, expected_suggestion
        )

  def test_report_and_handoff_carry_the_location_of_the_catalog(self):
    resources = _make_sample_resources()
    resources.location = "europe-west1"
    intent = _intent(_req("Requirement one"))
    match_result = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[_fw("builtin-il4")],
        unmatched_requirements=[_req("Requirement one")],
    )

    report = db_output_match_analyzer.analyze_output_matches(
        intent, match_result, resources
    )

    handoff = report.custom_authoring_handoff
    self.assertEqual(report.location, "europe-west1")
    self.assertEqual(report.to_dict()["location"], "europe-west1")
    self.assertEqual(handoff["location"], "europe-west1")

  def test_location_defaults_to_global(self):
    report = db_output_match_analyzer.analyze_output_matches(
        _intent(),
        db_output_match_analyzer.CatalogMatchResult(),
        _make_sample_resources(),
    )

    self.assertEqual(report.location, "global")

  def test_rejects_hallucinated_ids_and_invalid_parameters(self):
    resources = _make_sample_resources()
    intent = db_output_match_analyzer.NavigatorIntentSpec(
        source_type="DIRECT_NL",
        organization_id="123",
        user_prompt="Test validation",
    )

    bad_fw_match = db_output_match_analyzer.CatalogMatchResult(
        selected_frameworks=[
            db_output_match_analyzer.MatchedFW(
                fw_id="builtin-nonexistent-fw",
                fw_type="BUILT_IN",
                major_revision_id=1,
                display_name="Fake",
            )
        ]
    )
    with self.assertRaisesRegex(ValueError, "Unknown framework ID"):
      db_output_match_analyzer.analyze_output_matches(
          intent, bad_fw_match, resources
      )

    bad_param_val_match = db_output_match_analyzer.CatalogMatchResult(
        standalone_matched_ccs=[
            db_output_match_analyzer.MatchedCC(
                cc_id="builtin-gemini-enterprise-regulatory-settings",
                cc_type="BUILT_IN",
                display_name="Regulatory Framework",
                selected_parameters={"framework": "INVALID_ENUM_VALUE"},
            )
        ]
    )
    with self.assertRaisesRegex(
        ValueError, "Invalid value 'INVALID_ENUM_VALUE'"
    ):
      db_output_match_analyzer.analyze_output_matches(
          intent, bad_param_val_match, resources
      )


class MainTest(unittest.TestCase):
  """Runs the command line entry point on files in a temporary directory."""

  def _run_main(self, tmp_dir, match_result, requirement_texts):
    tmp = pathlib.Path(tmp_dir)
    (tmp / "intent.json").write_text(
        json.dumps({
            "source_type": "DIRECT_NL",
            "organization_id": "123",
            "user_prompt": "test",
            "requirements": [
                {"requirement": text, "importance": "MAJOR"}
                for text in requirement_texts
            ],
        })
    )
    (tmp / "match.json").write_text(json.dumps(match_result))
    (tmp / "resources.json").write_text(_make_sample_resources().to_json())
    argv = [
        "db_output_match_analyzer.py",
        "--intent_spec_json",
        str(tmp / "intent.json"),
        "--match_result_json",
        str(tmp / "match.json"),
        "--resources_json",
        str(tmp / "resources.json"),
        "--output_dir",
        str(tmp / "out"),
    ]
    with mock.patch.object(sys, "argv", argv):
      with contextlib.redirect_stdout(io.StringIO()):
        db_output_match_analyzer.main()
    return tmp / "out"

  def test_writes_the_author_handoff_next_to_the_report(self):
    match_result = {
        "selected_frameworks": [{"fw_id": "builtin-il4"}],
        "unmatched_requirements": [{"requirement": "Custom port rule"}],
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_dir = self._run_main(tmp_dir, match_result, ["Custom port rule"])

      report = json.loads((out_dir / "analysis_report.json").read_text())
      handoff = json.loads((out_dir / "author_handoff.json").read_text())

    self.assertEqual(handoff, report["custom_authoring_handoff"])
    self.assertEqual(handoff["organization_id"], "123")
    self.assertEqual(handoff["location"], "global")
    self.assertEqual(handoff["base_frameworks"], ["builtin-il4"])
    self.assertEqual(
        [
            r["requirement"]
            for r in handoff["unmet_major_requirements_needing_custom_ccs"]
        ],
        ["Custom port rule"],
    )

  def test_writes_no_handoff_when_none_is_needed(self):
    match_result = {
        "selected_frameworks": [
            {"fw_id": "builtin-il4", "satisfied_requirements": ["IL4"]}
        ]
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_dir = self._run_main(tmp_dir, match_result, ["IL4"])

      self.assertTrue((out_dir / "analysis_report.json").exists())
      self.assertFalse((out_dir / "author_handoff.json").exists())
      report = json.loads((out_dir / "analysis_report.json").read_text())
    self.assertIsNone(report["custom_authoring_handoff"])

  def test_removes_the_handoff_of_an_earlier_run(self):
    match_result = {
        "selected_frameworks": [
            {"fw_id": "builtin-il4", "satisfied_requirements": ["IL4"]}
        ]
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
      stale = pathlib.Path(tmp_dir, "out", "author_handoff.json")
      stale.parent.mkdir()
      stale.write_text('{"stale": true}')

      out_dir = self._run_main(tmp_dir, match_result, ["IL4"])

      self.assertFalse((out_dir / "author_handoff.json").exists())

  def test_writes_the_handoff_only_below_eighty_percent(self):
    texts = [f"Requirement {i}" for i in range(5)]
    for met, expect_handoff in [(5, False), (4, False), (3, True)]:
      with self.subTest(met=met):
        match_result = {
            "selected_frameworks": [
                {"fw_id": "builtin-il4", "satisfied_requirements": texts[:met]}
            ],
            "unmatched_requirements": [
                {"requirement": text} for text in texts[met:]
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
          out_dir = self._run_main(tmp_dir, match_result, texts)

          self.assertEqual(
              (out_dir / "author_handoff.json").exists(), expect_handoff
          )
          report = json.loads((out_dir / "analysis_report.json").read_text())
        self.assertEqual(report["match_score_percentage"], met * 20.0)
        self.assertEqual(
            report["matched_frameworks"][0]["match_percentage"], met * 20.0
        )
        self.assertEqual(
            report["suggest_custom_resources_for_unmet_requirements"],
            expect_handoff,
        )


if __name__ == "__main__":
  unittest.main()

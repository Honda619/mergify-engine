# -*- encoding: utf-8 -*-
#
# Copyright © 2018 Mehdi Abaakouk <sileht@sileht.net>
# Copyright © 2018 Julien Danjou <jd@mergify.io>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from unittest import mock

import pytest
import voluptuous

from mergify_engine import mergify_context
from mergify_engine import rules


def test_pull_request_rule():
    for valid in (
        {"name": "hello", "conditions": ["head:master"], "actions": {}},
        {"name": "hello", "conditions": ["base:foo", "base:baz"], "actions": {}},
    ):
        rules.load_pull_request_rules_schema([valid])


def test_same_names():
    pull_request_rules = rules.load_pull_request_rules_schema(
        [
            {"name": "hello", "conditions": [], "actions": {}},
            {"name": "foobar", "conditions": [], "actions": {}},
            {"name": "hello", "conditions": [], "actions": {}},
        ]
    )
    assert [rule["name"] for rule in pull_request_rules] == [
        "hello #1",
        "foobar",
        "hello #2",
    ]


def test_user_configuration_schema():
    with pytest.raises(voluptuous.Invalid) as exc_info:
        rules.UserConfigurationSchema("- no\n* way")
    assert exc_info.value.__class__.__name__, "YamlInvalid"
    assert str(exc_info.value.path) == "[at position 2:2]"
    assert exc_info.value.path == [{"line": 2, "column": 2}]

    with pytest.raises(voluptuous.Invalid):
        rules.UserConfigurationSchema(
            """
pull_request_rules:
  - name: ahah
    key: not really what we expected
"""
        )

    with pytest.raises(voluptuous.Invalid):
        rules.UserConfigurationSchema(
            """
pull_request_rules:
"""
        )

    with pytest.raises(voluptuous.Invalid):
        rules.UserConfigurationSchema("")


def test_pull_request_rule_schema_invalid():
    for invalid, match in (
        (
            {"name": "hello", "conditions": ["this is wrong"], "actions": {}},
            "Invalid condition ",
        ),
        (
            {"name": "invalid regexp", "conditions": ["head~=(lol"], "actions": {}},
            r"Invalid condition 'head~=\(lol'. Invalid arguments: "
            r"missing \), "
            r"unterminated subpattern at position 0 @ ",
        ),
        (
            {"name": "hello", "conditions": ["head|4"], "actions": {}},
            "Invalid condition ",
        ),
        (
            {"name": "hello", "conditions": [{"foo": "bar"}], "actions": {}},
            r"expected str @ data\[0\]\['conditions'\]\[0\]",
        ),
        (
            {"name": "hello", "conditions": [], "actions": {}, "foobar": True},
            "extra keys not allowed",
        ),
        (
            {"name": "hello", "conditions": [], "actions": {"merge": True}},
            r"expected a dictionary for dictionary value "
            r"@ data\[0\]\['actions'\]\['merge'\]",
        ),
        (
            {
                "name": "hello",
                "conditions": [],
                "actions": {"backport": {"regexes": ["(azerty"]}},
            },
            r"missing \), unterminated subpattern at position 0 "
            r"@ data\[0\]\['actions'\]\['backport'\]\['regexes'\]\[0\]",
        ),
        (
            {"name": "hello", "conditions": [], "actions": {"backport": True}},
            r"expected a dictionary for dictionary value "
            r"@ data\[0\]\['actions'\]\['backport'\]",
        ),
        (
            {
                "name": "hello",
                "conditions": [],
                "actions": {"merge": {"strict": "yes"}},
            },
            r"expected bool for dictionary value @ "
            r"data\[0\]\['actions'\]\['merge'\]\['strict'\]",
        ),
    ):
        with pytest.raises(voluptuous.MultipleInvalid, match=match):
            print(invalid)
            rules.PullRequestRules([invalid])


def test_get_pull_request_rule():

    client = mock.Mock()

    get_reviews = [
        {
            "user": {"login": "sileht", "type": "User"},
            "state": "APPROVED",
            "author_association": "MEMBER",
        }
    ]
    get_files = [{"filename": "README.rst"}, {"filename": "setup.py"}]
    get_team_members = [{"login": "sileht"}, {"login": "jd"}]

    get_checks = []
    get_statuses = [{"context": "continuous-integration/fake-ci", "state": "success"}]
    client.item.return_value = {"permission": "write"}  # get review user perm
    client.items.side_effect = [
        get_reviews,
        get_files,
        get_checks,
        get_statuses,
        get_team_members,
    ]

    ctxt = mergify_context.MergifyContext(
        client,
        {
            "number": 1,
            "html_url": "<html_url>",
            "state": "closed",
            "merged_by": None,
            "merged_at": None,
            "merged": False,
            "milestone": None,
            "mergeable_state": "unstable",
            "assignees": [],
            "labels": [],
            "author": "jd",
            "base": {"ref": "master", "repo": {"name": "name", "private": False},},
            "head": {"ref": "myfeature", "sha": "<sha>"},
            "locked": False,
            "requested_reviewers": [],
            "requested_teams": [],
            "title": "My awesome job",
            "body": "I rock",
            "user": {"login": "another-jd"},
        },
    )

    # Don't catch data in these tests
    ctxt.to_dict = ctxt._get_consolidated_data

    # Empty conditions
    pull_request_rules = rules.PullRequestRules(
        [{"name": "default", "conditions": [], "actions": {}}]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]
    assert [(r, []) for r in match.rules] == match.matching_rules
    for rule in match.rules:
        assert rule["actions"] == {}

    pull_request_rules = rules.PullRequestRules(
        [{"name": "hello", "conditions": ["base:master"], "actions": {}}]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["hello"]
    assert [r["name"] for r, _ in match.matching_rules] == ["hello"]
    assert [(r, []) for r in match.rules] == match.matching_rules
    for rule in match.rules:
        assert rule["actions"] == {}

    pull_request_rules = rules.PullRequestRules(
        [
            {"name": "hello", "conditions": ["base:master"], "actions": {}},
            {"name": "backport", "conditions": ["base:master"], "actions": {}},
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["hello", "backport"]
    assert [r["name"] for r, _ in match.matching_rules] == ["hello", "backport"]
    assert [(r, []) for r in match.rules] == match.matching_rules
    for rule in match.rules:
        assert rule["actions"] == {}

    pull_request_rules = rules.PullRequestRules(
        [
            {"name": "hello", "conditions": ["#files=3"], "actions": {}},
            {"name": "backport", "conditions": ["base:master"], "actions": {}},
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["hello", "backport"]
    assert [r["name"] for r, _ in match.matching_rules] == ["backport"]
    for rule in match.rules:
        assert rule["actions"] == {}

    pull_request_rules = rules.PullRequestRules(
        [
            {"name": "hello", "conditions": ["#files=2"], "actions": {}},
            {"name": "backport", "conditions": ["base:master"], "actions": {}},
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["hello", "backport"]
    assert [r["name"] for r, _ in match.matching_rules] == ["hello", "backport"]
    assert [(r, []) for r in match.rules] == match.matching_rules
    for rule in match.rules:
        assert rule["actions"] == {}

    # No match
    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "merge",
                "conditions": [
                    "base=xyz",
                    "status-success=continuous-integration/fake-ci",
                    "#approved-reviews-by>=1",
                ],
                "actions": {},
            }
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["merge"]
    assert [r["name"] for r, _ in match.matching_rules] == []

    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "merge",
                "conditions": [
                    "base=master",
                    "status-success=continuous-integration/fake-ci",
                    "#approved-reviews-by>=1",
                ],
                "actions": {},
            }
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["merge"]
    assert [r["name"] for r, _ in match.matching_rules] == ["merge"]
    assert [(r, []) for r in match.rules] == match.matching_rules
    for rule in match.rules:
        assert rule["actions"] == {}

    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "merge",
                "conditions": [
                    "base=master",
                    "status-success=continuous-integration/fake-ci",
                    "#approved-reviews-by>=2",
                ],
                "actions": {},
            },
            {
                "name": "fast merge",
                "conditions": [
                    "base=master",
                    "label=fast-track",
                    "status-success=continuous-integration/fake-ci",
                    "#approved-reviews-by>=1",
                ],
                "actions": {},
            },
            {
                "name": "fast merge with alternate ci",
                "conditions": [
                    "base=master",
                    "label=fast-track",
                    "status-success=continuous-integration/fake-ci-bis",
                    "#approved-reviews-by>=1",
                ],
                "actions": {},
            },
            {
                "name": "fast merge from a bot",
                "conditions": [
                    "base=master",
                    "author=mybot",
                    "status-success=continuous-integration/fake-ci",
                ],
                "actions": {},
            },
        ]
    )
    match = pull_request_rules.get_pull_request_rule(ctxt)

    assert [r["name"] for r in match.rules] == [
        "merge",
        "fast merge",
        "fast merge with alternate ci",
        "fast merge from a bot",
    ]
    assert [r["name"] for r, _ in match.matching_rules] == [
        "merge",
        "fast merge",
        "fast merge with alternate ci",
    ]
    for rule in match.rules:
        assert rule["actions"] == {}

    assert match.matching_rules[0][0]["name"] == "merge"
    assert len(match.matching_rules[0][1]) == 1
    assert str(match.matching_rules[0][1][0]) == "#approved-reviews-by>=2"

    assert match.matching_rules[1][0]["name"] == "fast merge"
    assert len(match.matching_rules[1][1]) == 1
    assert str(match.matching_rules[1][1][0]) == "label=fast-track"

    assert match.matching_rules[2][0]["name"] == "fast merge with alternate ci"
    assert len(match.matching_rules[2][1]) == 2
    assert str(match.matching_rules[2][1][0]) == "label=fast-track"
    assert (
        str(match.matching_rules[2][1][1])
        == "status-success=continuous-integration/fake-ci-bis"
    )

    # Team conditions with one review missing
    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "default",
                "conditions": [
                    "approved-reviews-by=@orgs/my-reviewers",
                    "#approved-reviews-by>=2",
                ],
                "actions": {},
            }
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]

    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 1
    assert str(match.matching_rules[0][1][0]) == "#approved-reviews-by>=2"

    get_reviews.append(
        {
            "user": {"login": "jd", "type": "User"},
            "state": "APPROVED",
            "author_association": "MEMBER",
        }
    )
    client.items.side_effect = [
        get_reviews,
        get_files,
        get_checks,
        get_statuses,
        get_team_members,
    ]
    # Drop caches
    del ctxt.__dict__["checks"]
    del ctxt.__dict__["reviews"]
    del ctxt.__dict__["files"]
    del ctxt.__dict__["consolidated_reviews"]

    # Team conditions with no review missing
    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "default",
                "conditions": [
                    "approved-reviews-by=@orgs/my-reviewers",
                    "#approved-reviews-by>=2",
                ],
                "actions": {},
            }
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]

    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 0

    # Forbidden labels, when no label set
    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "default",
                "conditions": ["-label~=^(status/wip|status/blocked|review/need2)$"],
                "actions": {},
            }
        ]
    )

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]
    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 0

    # Forbidden labels, when forbiden label set
    ctxt.pull["labels"] = [{"name": "status/wip"}]

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]
    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 1
    assert str(match.matching_rules[0][1][0]) == (
        "-label~=^(status/wip|status/blocked|review/need2)$"
    )

    # Forbidden labels, when other label set
    ctxt.pull["labels"] = [{"name": "allowed"}]

    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]
    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 0

    # Test team expander
    pull_request_rules = rules.PullRequestRules(
        [
            {
                "name": "default",
                "conditions": ["author~=^(user1|user2|another-jd)$"],
                "actions": {},
            }
        ]
    )
    match = pull_request_rules.get_pull_request_rule(ctxt)
    assert [r["name"] for r in match.rules] == ["default"]
    assert [r["name"] for r, _ in match.matching_rules] == ["default"]
    assert match.matching_rules[0][0]["name"] == "default"
    assert len(match.matching_rules[0][1]) == 0

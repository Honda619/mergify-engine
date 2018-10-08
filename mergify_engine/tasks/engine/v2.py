# -*- encoding: utf-8 -*-
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

import daiquiri

from mergify_engine import check_api
from mergify_engine import config
from mergify_engine import mergify_pull
from mergify_engine import rules
from mergify_engine.worker import app

LOG = daiquiri.getLogger(__name__)


def post_summary(pull, match, checks):
    # Set the summary
    summary_name = "Mergify — Summary"
    summary = ""

    completed_rules = 0
    for rule, missing_conditions in match.matching_rules:
        summary += "#### Rule: %s" % rule['name']
        summary += " (%s)" % ", ".join(rule['actions'])
        for cond in rule['conditions']:
            checked = " " if cond in missing_conditions else "X"
            summary += "\n- [%s] `%s`" % (checked, cond)
        if not missing_conditions:
            completed_rules += 1
        summary += "\n\n"

    potential_rules = len(match.matching_rules) - completed_rules

    summary_title = []
    if completed_rules == 1:
        summary_title.append("%d rule matches" % completed_rules)
    elif completed_rules > 1:
        summary_title.append("%d rules match" % completed_rules)

    if potential_rules == 1:
        summary_title.append("%s potential rule" % potential_rules)
    elif potential_rules > 1:
        summary_title.append("%s potential rules" % potential_rules)

    if completed_rules == 0 and potential_rules == 0:
        summary_title.append("no rules match, no planned actions")

    summary_title = " and ".join(summary_title)

    summary_check = checks.get(summary_name)
    summary_changed = (not summary_check or
                       summary_check.output["title"] != summary_title or
                       summary_check.output["summary"] != summary)

    if summary_changed:
        check_api.set_check_run(
            pull.g_pull, summary_name, "completed", "success",
            output={"title": summary_title, "summary": summary})


def exec_action(method_name, rule, action,
                installation_id, installation_token, subscription,
                event_type, data, pull):
    try:
        method = getattr(rule['actions'][action], method_name)
        return method(
            installation_id, installation_token, subscription,
            event_type, data, pull)
    except Exception as e:  # pragma: no cover
        pull.log.error("action failed", action=action, rule=rule,
                       exc_info=True)
        # TODO(sileht): extract sentry event id and post it, so
        # we can track it easly
        if rule["actions"][action].dedicated_check:
            return "failure", "action '%s' have failed" % action, " "
        else:
            return


def run_actions(installation_id, installation_token, subscription,
                event_type, data, pull, match, checks):

    # Run actions
    for rule, missing_conditions in match.matching_rules:
        for action in rule['actions']:
            check_name = "Mergify — Rule: %s (%s)" % (rule['name'], action)
            prev_check = checks.get(check_name)

            if missing_conditions:
                if not prev_check:
                    continue
                method_name = "cancel"
                expected_conclusion = ["cancelled"]
            else:
                method_name = "run"
                expected_conclusion = ["success", "failure"]

            already_run = (prev_check and prev_check.conclusion in
                           expected_conclusion and
                           event_type != "refresh")
            if already_run:
                continue

            report = exec_action(
                method_name, rule, action,
                installation_id, installation_token, subscription,
                event_type, data, pull
            )

            if report:
                conclusion, title, summary = report
                status = "completed" if conclusion else "in_progress"
                check_api.set_check_run(
                    pull.g_pull, check_name, status, conclusion,
                    output={"title": title, "summary": summary})


@app.task
def handle(installation_id, installation_token, subscription,
           pull_request_rules_raw, event_type, data, pull_raw):

    pull_request_rules = rules.PullRequestRules(**pull_request_rules_raw)
    pull = mergify_pull.MergifyPull.from_raw(
        installation_id,
        installation_token,
        pull_raw)
    match = pull_request_rules.get_pull_request_rule(pull)
    checks = dict((c.name, c) for c in check_api.get_checks(pull.g_pull)
                  if c._rawData['app']['id'] == config.INTEGRATION_ID)

    post_summary(pull, match, checks)

    run_actions(installation_id, installation_token, subscription,
                event_type, data, pull, match, checks)

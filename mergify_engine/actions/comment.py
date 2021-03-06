# -*- encoding: utf-8 -*-
#
#  Copyright © 2018 Mehdi Abaakouk <sileht@sileht.net>
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

import httpx
import voluptuous

from mergify_engine import actions
from mergify_engine import config


class CommentAction(actions.Action):
    validator = {voluptuous.Required("message"): str}

    silent_report = True

    def deprecated_double_comment_protection(self, ctxt):
        # TODO(sileht): drop this in 2 months (February 2020)
        for comment in ctxt.client.items(f"issues/{ctxt.pull['number']}/comments"):
            if (
                comment["user"]["id"] == config.BOT_USER_ID
                and comment["body"] == self.config["message"]
            ):
                return True
        return False

    def run(self, ctxt, sources, missing_conditions):
        message = self.config["message"]
        try:
            ctxt.client.post(
                f"issues/{ctxt.pull['number']}/comments", json={"body": message},
            )
        except httpx.HTTPClientSideError as e:  # pragma: no cover
            return (
                None,
                "Unable to post comment",
                f"GitHub error: [{e.status_code}] `{e.message}`",
            )
        return ("success", "Comment posted", message)

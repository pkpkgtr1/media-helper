"""Custom User-Agent propagation: plain requests use it, FlareSolverr wins.

Run from the project root: python -m unittest discover -s tests -p test_user_agent.py
No network access is needed; sessions are only inspected, never sent.
"""
from __future__ import annotations

import os
import unittest

from media_helper import net as user_agent
from media_helper import net as web_fetch
from media_helper.sources import huangguo as huangguo_client


class UserAgentPropagationTests(unittest.TestCase):
    def setUp(self):
        self.keep = os.environ.get(user_agent.UA_ENV)
        os.environ.pop(user_agent.UA_ENV, None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop(user_agent.UA_ENV, None)
        if self.keep is not None:
            os.environ[user_agent.UA_ENV] = self.keep

    def test_default_agent_when_setting_is_empty(self):
        user_agent.configure({"userAgent": ""})
        self.assertEqual(web_fetch.DEFAULT_UA, web_fetch.make_session().headers["User-Agent"])
        self.assertEqual(huangguo_client.UA, huangguo_client.Client().session.headers["User-Agent"])

    def test_custom_agent_reaches_every_session(self):
        user_agent.configure({"userAgent": "MyBot/1.0 (+test)"})
        self.assertEqual("MyBot/1.0 (+test)", web_fetch.make_session().headers["User-Agent"])
        self.assertEqual("MyBot/1.0 (+test)", huangguo_client.Client().session.headers["User-Agent"])
        from media_helper.sources import yeguo as yeguo_client
        self.assertEqual("MyBot/1.0 (+test)", yeguo_client.Client().session.headers["User-Agent"])

    def test_flaresolverr_keeps_custom_agent_out(self):
        user_agent.configure({"userAgent": "MyBot/1.0", "flaresolverrEnabled": True})
        session = web_fetch.make_session()
        self.assertEqual(web_fetch.DEFAULT_UA, session.headers["User-Agent"])
        solution = type("S", (), {"cookies": [], "user_agent": "SolvedUA/2"})()
        web_fetch.apply_solution(session, solution)
        self.assertEqual("SolvedUA/2", session.headers["User-Agent"])


if __name__ == "__main__":
    unittest.main()

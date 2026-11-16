# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Follow Executor contributors
"""Answer the existing setup prompts from a submitted form, without changing them.

``gateway.py`` stays byte-identical for reviewed upgrades, so the setup console
cannot add parameters to ``gateway.configure``. Instead, while a console action
runs, ``input`` and ``getpass.getpass`` are replaced by a scripted answerer that
recognises each known prompt by its exact opening words. Validation and saving
remain in the unchanged code paths.

The answerer refuses an unknown prompt, and a prompt asked a second time (the
code's own validation rejected the answer), so a console action never loops or
guesses. Nothing is saved by those prompts until every one is answered.
"""

from __future__ import annotations

import builtins
import contextlib
import getpass
from collections.abc import Iterator, Mapping

from .config import ConfigError

# (opening words, group, field). A group of None reads the top level of the answers.
# The opening words must match the prompt text exactly; tests pin them to the
# prompts in setup.py, gateway.py and stack.py.
HOST_PROMPTS: tuple[tuple[str, str | None, str], ...] = (
    ("Install Docker from its official Ubuntu repository using sudo?", None, "docker_install"),
    ("Finish local Docker startup permissions using sudo?", None, "docker_permissions"),
    ("Enable services after logout and reboot using sudo?", None, "linger"),
    ("After login, press Enter to check readiness", None, "gateway_ready"),
    ("Type START ", None, "start_confirmation"),
    ("Account mode", "gateway", "mode"),
    ("Type LIVE to enable automatic real-account login", "gateway", "live_confirmation"),
    ("Schedule timezone (IANA name)", "gateway", "timezone"),
    ("Daily automatic restart (HH:MM", "gateway", "daily_restart"),
    ("Sunday mobile approval time (HH:MM)", "gateway", "sunday_restart"),
    ("Recovery desktop password", "gateway", "vnc_password"),
    ("Confirm recovery desktop password", "gateway", "vnc_password"),
    ("IBKR login username", "gateway", "username"),
    ("IBKR password", "gateway", "password"),
)

ACCOUNT_PROMPTS: tuple[tuple[str, str | None, str], ...] = (
    ("Account mode", None, "mode"),
    ("IBKR account ID", None, "account"),
    ("Sizing", None, "sizing"),
    ("Leverage fraction", None, "leverage_fraction"),
    ("Number of contracts", None, "quantity"),
    ("Your current IBKR NetLiquidation in USD", None, "preview_net_liquidation"),
    ("Approximate current NQ price", None, "preview_nq_price"),
    ("Type LIVE ", None, "live_confirmation"),
    ("Personal relay token", None, "token"),
)

DISCORD_PROMPTS: tuple[tuple[str, str | None, str], ...] = (
    ("Type LINK to agree and pair your Discord account", None, "agree"),
)

# Optional size-preview questions; the readiness check shows the preview anyway.
OPTIONAL = frozenset({"preview_net_liquidation", "preview_nq_price"})


class NeedInput(Exception):
    """The console has not collected this group of answers yet."""

    def __init__(self, group: str):
        super().__init__(group)
        self.group = group


class ScriptedAnswers:
    def __init__(self, prompts: tuple[tuple[str, str | None, str], ...],
                 answers: Mapping[str, object]):
        self.prompts = prompts
        self.answers = answers
        self.asked: set[str] = set()

    def answer(self, prompt: str) -> str:
        text = str(prompt)
        for opening, group, field in self.prompts:
            if text.startswith(opening):
                break
        else:
            raise ConfigError(f"The console cannot answer this prompt: {text.strip()}")
        if opening in self.asked:
            raise ConfigError(f"The value entered for '{opening.rstrip(' ?:(')}' was not accepted. "
                              "Correct it and try again.")
        self.asked.add(opening)
        values = self.answers if group is None else self.answers.get(group)
        if not isinstance(values, Mapping):
            raise NeedInput(group or field)
        if field not in values:
            if field in OPTIONAL:
                return ""
            raise NeedInput(group or field)
        value = values[field]
        if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ConfigError(f"Invalid console answer for '{field}'")
        return str(value)

    def input(self, prompt: object = "") -> str:
        return self.answer(str(prompt))

    def getpass(self, prompt: str = "Password: ", stream=None) -> str:
        return self.answer(prompt)


@contextlib.contextmanager
def scripted(prompts: tuple[tuple[str, str | None, str], ...],
             answers: Mapping[str, object]) -> Iterator[ScriptedAnswers]:
    """Replace interactive prompts for the duration of one console action."""

    answerer = ScriptedAnswers(prompts, answers)
    saved_input, saved_getpass = builtins.input, getpass.getpass
    builtins.input, getpass.getpass = answerer.input, answerer.getpass
    try:
        yield answerer
    finally:
        builtins.input, getpass.getpass = saved_input, saved_getpass

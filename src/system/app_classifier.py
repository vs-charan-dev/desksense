"""Application Categorization Engine for DeskSense.
Provides deterministic, case-insensitive classification of running processes
and window titles into productive, communication, entertainment, browser, or unclassified categories.
Supports pre-seeded default rules and persistent user-defined overrides.
Zero unsafe regex execution: uses fast exact or substring matching.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from src.storage.db import DatabaseEngine


class AppCategory(str, Enum):
    PRODUCTIVE = "productive"
    COMMUNICATION = "communication"
    ENTERTAINMENT = "entertainment"
    BROWSER = "browser"
    UNCLASSIFIED = "unclassified"


DEFAULT_PROCESS_RULES: Dict[str, AppCategory] = {
    # Productive
    "code": AppCategory.PRODUCTIVE,
    "code.exe": AppCategory.PRODUCTIVE,
    "cursor": AppCategory.PRODUCTIVE,
    "cursor.exe": AppCategory.PRODUCTIVE,
    "devenv": AppCategory.PRODUCTIVE,
    "devenv.exe": AppCategory.PRODUCTIVE,
    "idea64": AppCategory.PRODUCTIVE,
    "idea64.exe": AppCategory.PRODUCTIVE,
    "pycharm64": AppCategory.PRODUCTIVE,
    "pycharm64.exe": AppCategory.PRODUCTIVE,
    "winword": AppCategory.PRODUCTIVE,
    "winword.exe": AppCategory.PRODUCTIVE,
    "excel": AppCategory.PRODUCTIVE,
    "excel.exe": AppCategory.PRODUCTIVE,
    "powerpnt": AppCategory.PRODUCTIVE,
    "powerpnt.exe": AppCategory.PRODUCTIVE,
    "notion": AppCategory.PRODUCTIVE,
    "notion.exe": AppCategory.PRODUCTIVE,
    "figma": AppCategory.PRODUCTIVE,
    "figma.exe": AppCategory.PRODUCTIVE,
    "acad": AppCategory.PRODUCTIVE,
    "acad.exe": AppCategory.PRODUCTIVE,
    "photoshop": AppCategory.PRODUCTIVE,
    "photoshop.exe": AppCategory.PRODUCTIVE,
    "terminal": AppCategory.PRODUCTIVE,
    "windows terminal": AppCategory.PRODUCTIVE,
    "windowsterminal.exe": AppCategory.PRODUCTIVE,
    "powershell": AppCategory.PRODUCTIVE,
    "powershell.exe": AppCategory.PRODUCTIVE,
    "cmd": AppCategory.PRODUCTIVE,
    "cmd.exe": AppCategory.PRODUCTIVE,

    # Communication
    "slack": AppCategory.COMMUNICATION,
    "slack.exe": AppCategory.COMMUNICATION,
    "teams": AppCategory.COMMUNICATION,
    "ms-teams": AppCategory.COMMUNICATION,
    "ms-teams.exe": AppCategory.COMMUNICATION,
    "discord": AppCategory.COMMUNICATION,
    "discord.exe": AppCategory.COMMUNICATION,
    "whatsapp": AppCategory.COMMUNICATION,
    "whatsapp.exe": AppCategory.COMMUNICATION,
    "telegram": AppCategory.COMMUNICATION,
    "telegram.exe": AppCategory.COMMUNICATION,
    "zoom": AppCategory.COMMUNICATION,
    "zoom.exe": AppCategory.COMMUNICATION,
    "outlook": AppCategory.COMMUNICATION,
    "outlook.exe": AppCategory.COMMUNICATION,

    # Entertainment
    "netflix": AppCategory.ENTERTAINMENT,
    "netflix.exe": AppCategory.ENTERTAINMENT,
    "spotify": AppCategory.ENTERTAINMENT,
    "spotify.exe": AppCategory.ENTERTAINMENT,
    "steam": AppCategory.ENTERTAINMENT,
    "steam.exe": AppCategory.ENTERTAINMENT,
    "epicgameslauncher": AppCategory.ENTERTAINMENT,
    "epicgameslauncher.exe": AppCategory.ENTERTAINMENT,
    "vlc": AppCategory.ENTERTAINMENT,
    "vlc.exe": AppCategory.ENTERTAINMENT,

    # Browsers
    "chrome": AppCategory.BROWSER,
    "chrome.exe": AppCategory.BROWSER,
    "msedge": AppCategory.BROWSER,
    "msedge.exe": AppCategory.BROWSER,
    "firefox": AppCategory.BROWSER,
    "firefox.exe": AppCategory.BROWSER,
    "brave": AppCategory.BROWSER,
    "brave.exe": AppCategory.BROWSER,
    "opera": AppCategory.BROWSER,
    "opera.exe": AppCategory.BROWSER,
}

DEFAULT_TITLE_RULES: List[Tuple[str, AppCategory]] = [
    # Productive keywords in title
    ("visual studio code", AppCategory.PRODUCTIVE),
    ("pull request", AppCategory.PRODUCTIVE),
    ("github", AppCategory.PRODUCTIVE),
    ("gitlab", AppCategory.PRODUCTIVE),
    ("stackoverflow", AppCategory.PRODUCTIVE),
    ("stack overflow", AppCategory.PRODUCTIVE),
    ("docs.google.com", AppCategory.PRODUCTIVE),
    ("jira", AppCategory.PRODUCTIVE),
    ("confluence", AppCategory.PRODUCTIVE),
    ("overleaf", AppCategory.PRODUCTIVE),
    ("arxiv", AppCategory.PRODUCTIVE),

    # Entertainment keywords in title
    ("youtube", AppCategory.ENTERTAINMENT),
    ("netflix", AppCategory.ENTERTAINMENT),
    ("twitch", AppCategory.ENTERTAINMENT),
    ("disney+", AppCategory.ENTERTAINMENT),
    ("reddit", AppCategory.ENTERTAINMENT),
    ("twitter", AppCategory.ENTERTAINMENT),
    ("instagram", AppCategory.ENTERTAINMENT),
    ("tiktok", AppCategory.ENTERTAINMENT),
]


class AppClassifier:
    """Deterministic application classifier with user override precedence."""

    def __init__(self, db: Optional[DatabaseEngine] = None):
        self.db = db
        # In-memory user override caches: stores both name and name.exe variations
        self.user_process_rules: Dict[str, str] = {}
        self.user_title_rules: List[Tuple[str, str, int]] = []  # (keyword, category, id)
        self.load_rules_from_db()

    def _normalize_proc_key(self, pat: str) -> Tuple[str, str]:
        p = pat.strip().lower()
        if p.endswith(".exe"):
            return p, p[:-4]
        return p + ".exe", p

    def load_rules_from_db(self) -> None:
        """Loads user overrides and custom rules from database if provided."""
        if not self.db:
            return
        rules = self.db.get_category_rules()
        self.user_process_rules.clear()
        self.user_title_rules.clear()
        for r in rules:
            rtype = r.get("rule_type", "").lower()
            pattern = r.get("pattern", "").lower()
            cat = r.get("category", "").lower()
            rid = r.get("id", 0)
            if rtype == "process":
                k1, k2 = self._normalize_proc_key(pattern)
                self.user_process_rules[k1] = cat
                self.user_process_rules[k2] = cat
            elif rtype == "title":
                self.user_title_rules.append((pattern, cat, rid))

    def add_rule(self, pattern: str, rule_type: str, category: str, is_user: bool = True) -> int:
        """Adds a rule, updates in-memory cache, and persists to DB if connected."""
        pat = pattern.strip().lower()
        rtype = rule_type.strip().lower()
        cat = category.strip().lower()

        rule_id = 0
        if self.db:
            rule_id = self.db.insert_category_rule(pat, rtype, cat, is_user_override=is_user)

        if rtype == "process":
            k1, k2 = self._normalize_proc_key(pat)
            self.user_process_rules[k1] = cat
            self.user_process_rules[k2] = cat
        elif rtype == "title":
            # Remove existing pattern if present
            self.user_title_rules = [t for t in self.user_title_rules if t[0] != pat]
            self.user_title_rules.append((pat, cat, rule_id))

        return rule_id

    def delete_rule(self, pattern: str, rule_type: str, rule_id: Optional[int] = None) -> bool:
        """Deletes a rule from in-memory cache and DB."""
        pat = pattern.strip().lower()
        rtype = rule_type.strip().lower()
        success = True

        if self.db and rule_id is not None:
            success = self.db.delete_category_rule(rule_id)

        if rtype == "process":
            k1, k2 = self._normalize_proc_key(pat)
            self.user_process_rules.pop(k1, None)
            self.user_process_rules.pop(k2, None)
        elif rtype == "title":
            self.user_title_rules = [t for t in self.user_title_rules if t[0] != pat and (rule_id is None or t[2] != rule_id)]

        return success

    def classify(self, process_name: Optional[str] = None, window_title: Optional[str] = None) -> str:
        """
        Classifies an application based on deterministic precedence:
        1. User process rule (exact match, case-insensitive)
        2. User title keyword rule (substring match, case-insensitive)
        3. Default process rule
        4. Default title keyword rule (particularly useful for browser window titles)
        5. If browser process but no specific title rule, return 'browser'
        6. Otherwise 'unclassified' (neutral)
        """
        proc = (process_name or "").strip().lower()
        # Strip path if full path passed
        if "\\" in proc:
            proc = proc.split("\\")[-1]
        elif "/" in proc:
            proc = proc.split("/")[-1]

        title = (window_title or "").strip().lower()

        # 1. User process rule
        if proc in self.user_process_rules:
            return self.user_process_rules[proc]
        proc_no_ext = proc[:-4] if proc.endswith(".exe") else proc
        if proc_no_ext in self.user_process_rules:
            return self.user_process_rules[proc_no_ext]

        # 2. User title rule (first matching substring)
        if title:
            for pattern, cat, _ in self.user_title_rules:
                if pattern in title:
                    return cat

        # 3. Default process rule
        default_cat = None
        if proc in DEFAULT_PROCESS_RULES:
            default_cat = DEFAULT_PROCESS_RULES[proc].value
        elif proc_no_ext in DEFAULT_PROCESS_RULES:
            default_cat = DEFAULT_PROCESS_RULES[proc_no_ext].value

        # 4. If it's a browser, title rules can refine it to productive or entertainment!
        if title:
            for pattern, cat in DEFAULT_TITLE_RULES:
                if pattern in title:
                    return cat.value

        # If it was matched as a browser process and no specific title rule matched
        if default_cat:
            return default_cat

        # 5. Default title rule for non-browsers as fallback
        if title:
            for pattern, cat in DEFAULT_TITLE_RULES:
                if pattern in title:
                    return cat.value

        return AppCategory.UNCLASSIFIED.value

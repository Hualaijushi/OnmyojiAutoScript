"""Reusable multi-account scheduling primitives.

The package deliberately contains no gameplay task logic.  Existing account
configuration remains owned by OAS, while this layer supplies stable account
IDs, switching results, OCR request scheduling, and crash-safe daily state.
"""

from module.multi_account.account import Account
from module.multi_account.account_manager import AccountManager
from module.multi_account.account_switcher import AccountSwitcher, SwitchErrorCode, SwitchResult
from module.multi_account.daily_state import DailyStateManager

__all__ = [
    "Account",
    "AccountManager",
    "AccountSwitcher",
    "DailyStateManager",
    "SwitchErrorCode",
    "SwitchResult",
]

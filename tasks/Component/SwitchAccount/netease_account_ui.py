from __future__ import annotations

import re
import time
from dataclasses import dataclass

from lxml import etree


class AccountUiUnavailable(RuntimeError):
    """The NetEase account UI could not be read through UIAutomator."""


@dataclass(frozen=True)
class AccountEntry:
    account: str
    bounds: tuple[int, int, int, int]


class NeteaseAccountUi:
    """Read and operate the native NetEase saved-account popup."""

    ACCOUNT_ITEM_ID = "netease_mpay__login_user_item"
    ACCOUNT_LIST_ID = "netease_mpay__user_list"
    ACCOUNT_TEXT_IDS = (
        "netease_mpay__login_username_with_tag",
        "netease_mpay__login_username",
    )
    LOGIN_BUTTON_ID = "netease_mpay__login"

    def __init__(self, device, *, settle_seconds: float = 0.5, max_scrolls: int = 12):
        self.device = device
        self.settle_seconds = settle_seconds
        self.max_scrolls = max_scrolls

    @staticmethod
    def normalize_account(account: str | None) -> str:
        return "".join((account or "").split()).casefold()

    @staticmethod
    def _resource_xpath(resource_id: str) -> str:
        length = len(resource_id)
        return (
            '//*['
            f'substring(@resource-id, string-length(@resource-id) - {length - 1}) = "{resource_id}"'
            ']'
        )

    @staticmethod
    def _bounds(node) -> tuple[int, int, int, int]:
        values = [int(value) for value in re.findall(r"\d+", node.attrib.get("bounds", ""))]
        if len(values) != 4:
            raise AccountUiUnavailable("invalid account UI bounds")
        left, top, right, bottom = values
        if right <= left or bottom <= top:
            raise AccountUiUnavailable("empty account UI bounds")
        return left, top, right, bottom

    def dump(self):
        last_error = None
        for attempt in range(2):
            try:
                # OAS' regular adb hierarchy dump only returns the activity
                # root. The NetEase list is a separate PopupWindow, so force
                # the multi-window uiautomator2 hierarchy here.
                content = self.device.u2.dump_hierarchy(compressed=False, pretty=False)
                return etree.fromstring(content.encode("utf-8"))
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    try:
                        self.device.u2.uiautomator.start()
                        time.sleep(self.settle_seconds)
                        continue
                    except Exception as start_exc:
                        last_error = start_exc
                break
        raise AccountUiUnavailable(f"account UI hierarchy unavailable: {last_error}") from last_error

    def _nodes(self, root, resource_id: str):
        return root.xpath(self._resource_xpath(resource_id))

    def current_account(self, root=None) -> str | None:
        root = root if root is not None else self.dump()
        # A closed saved-account dialog contains exactly one account field. A
        # list PopupWindow contains several entries and must not be mistaken
        # for confirmation of the selected account.
        if self._nodes(root, self.ACCOUNT_LIST_ID):
            return None
        for resource_id in self.ACCOUNT_TEXT_IDS:
            for node in self._nodes(root, resource_id):
                text = node.attrib.get("text", "").strip()
                if text:
                    return text
        return None

    def account_matches(self, actual: str | None, expected: str) -> bool:
        return self.normalize_account(actual) == self.normalize_account(expected)

    def _click_bounds(self, bounds: tuple[int, int, int, int], name: str) -> None:
        left, top, right, bottom = bounds
        self.device.click(
            x=(left + right) // 2,
            y=(top + bottom) // 2,
            control_name=name,
        )

    def _click_node(self, node, name: str) -> None:
        self._click_bounds(self._bounds(node), name)

    def _account_entries(self, root) -> list[AccountEntry]:
        list_nodes = self._nodes(root, self.ACCOUNT_LIST_ID)
        if not list_nodes:
            return []
        list_node = list_nodes[0]
        entries: list[AccountEntry] = []
        for resource_id in self.ACCOUNT_TEXT_IDS:
            for text_node in list_node.xpath(self._resource_xpath(resource_id)):
                account = text_node.attrib.get("text", "").strip()
                if not account:
                    continue
                clickable = next(
                    (node for node in text_node.iterancestors() if node.attrib.get("clickable") == "true"),
                    text_node,
                )
                entries.append(AccountEntry(account=account, bounds=self._bounds(clickable)))
        return entries

    def _find_entry(self, entries: list[AccountEntry], target: str) -> AccountEntry | None:
        for entry in entries:
            if self.account_matches(entry.account, target):
                return entry
        return None

    def _open_list(self, root) -> bool:
        if self._nodes(root, self.ACCOUNT_LIST_ID):
            return True
        candidates = [
            node for node in self._nodes(root, self.ACCOUNT_ITEM_ID)
            if node.attrib.get("clickable") == "true"
        ]
        if len(candidates) != 1:
            return False
        self._click_node(candidates[0], "netease_account_list_open")
        time.sleep(self.settle_seconds)
        return True

    def _scroll(self, root, *, toward_start: bool) -> bool:
        list_nodes = self._nodes(root, self.ACCOUNT_LIST_ID)
        if not list_nodes:
            return False
        left, top, right, bottom = self._bounds(list_nodes[0])
        x = (left + right) // 2
        height = bottom - top
        if toward_start:
            start = (x, top + height // 3)
            end = (x, bottom - height // 5)
            name = "netease_account_list_to_start"
        else:
            start = (x, bottom - height // 5)
            end = (x, top + height // 3)
            name = "netease_account_list_to_end"
        self.device.swipe(start, end, duration=0.35, control_name=name)
        time.sleep(self.settle_seconds)
        return True

    def _select_visible(self, root, target: str) -> bool:
        entry = self._find_entry(self._account_entries(root), target)
        if entry is None:
            return False
        self._click_bounds(entry.bounds, "netease_account_select")
        for _ in range(4):
            time.sleep(self.settle_seconds)
            selected = self.current_account()
            if self.account_matches(selected, target):
                return True
        return False

    def select_account(self, target: str) -> bool:
        root = self.dump()
        if self.account_matches(self.current_account(root), target):
            return True
        if not self._open_list(root):
            return False

        # Check the current viewport first. If the list retained an old scroll
        # position, walk to its start, then scan toward the end. Repeated
        # account tuples mark an edge and prevent infinite swiping.
        root = self.dump()
        if self._select_visible(root, target):
            return True

        previous: tuple[str, ...] | None = None
        for _ in range(self.max_scrolls):
            root = self.dump()
            entries = self._account_entries(root)
            signature = tuple(self.normalize_account(entry.account) for entry in entries)
            if signature == previous or not entries:
                break
            previous = signature
            if self._select_visible(root, target):
                return True
            if not self._scroll(root, toward_start=True):
                break

        previous = None
        for _ in range(self.max_scrolls):
            root = self.dump()
            entries = self._account_entries(root)
            signature = tuple(self.normalize_account(entry.account) for entry in entries)
            if signature == previous or not entries:
                break
            previous = signature
            if self._select_visible(root, target):
                return True
            if not self._scroll(root, toward_start=False):
                break
        return False

    def click_login(self) -> bool:
        root = self.dump()
        buttons = [
            node for node in self._nodes(root, self.LOGIN_BUTTON_ID)
            if node.attrib.get("class") == "android.widget.Button"
            and node.attrib.get("clickable") == "true"
        ]
        if len(buttons) != 1:
            return False
        self._click_node(buttons[0], "netease_saved_account_login")
        return True

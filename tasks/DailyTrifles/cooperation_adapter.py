"""账号轮换中只检查悬赏封印协作卡槽的局部适配器。"""

from __future__ import annotations

import time
from dataclasses import dataclass

from module.base.timer import Timer
from module.logger import logger
from module.multi_account.rotation_runner import DailyTaskOutcome
from tasks.GameUi.page import page_main
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationType


CooperationResult = tuple[str, CooperationType]


@dataclass(slots=True)
class CooperationAdapter(WantedQuestsAssets):
    """复用悬赏封印协作识别，但不进入好友邀请和悬赏执行流程。"""

    owner: object
    entry_timeout: float = 12.0
    scan_timeout: float = 8.0
    stability_timeout: float = 2.0
    exit_timeout: float = 8.0

    def __getattr__(self, name: str):
        """将悬赏识别方法需要的设备操作转发给当前每日任务对象。"""
        return getattr(self.owner, name)

    def run(self) -> DailyTaskOutcome:
        self._open_wanted_quests()
        outcome: DailyTaskOutcome
        try:
            found_results = self._scan_cooperation_results()
            result = self._format_result(found_results)
            logger.info("账号轮换协作检查完成：结果=%s", result)
            outcome = DailyTaskOutcome(success=True, result=result)
        finally:
            try:
                self._return_to_main()
            except Exception as exc:
                logger.error("协作检查返回庭院失败，保留已完成结果：%s", exc)
        return outcome

    def _open_wanted_quests(self) -> None:
        if not self.owner.goto_page(page_main, timeout=int(self.entry_timeout)):
            raise TimeoutError("协作检查返回庭院超时")

        timer = Timer(self.entry_timeout).start()
        click_count = 0
        while not timer.reached():
            self.owner.screenshot()
            if self._wanted_quests_page_detected():
                return

            # 首次点击使用已确认的庭院状态，后续点击必须再次确认仍在庭院。
            current = None
            if click_count > 0:
                current = self.owner.get_current_page(skip_first_screenshot=True, fallback=False)
            if click_count < 2 and (click_count == 0 or current == page_main):
                if self.owner.appear_then_click(self.I_WQ_SEAL, interval=0.8):
                    click_count += 1
            time.sleep(0.15)
        raise TimeoutError("进入悬赏封印页面超时")

    def _wanted_quests_page_detected(self) -> bool:
        if self.owner.appear(self.I_PAGE_WANTED_QUESTS):
            return True
        if self.owner.appear(self.I_TRACE_ENABLE) or self.owner.appear(self.I_TRACE_DISABLE):
            return True
        if any(
            self.owner.appear(rule)
            for rule in (
                self.I_WQ_INVITE_1,
                self.I_WQ_INVITE_2,
                self.I_WQ_INVITE_3,
                self.I_WQ_INVITE_1_REALWORLD,
                self.I_WQ_INVITE_2_REALWORLD,
                self.I_WQ_INVITE_3_REALWORLD,
            )
        ):
            return True
        if self.owner.appear(self.I_WQ_DONE):
            return True
        return bool(self.owner.ocr_appear(self.O_WQ_LIST_CHECK, interval=0.5))

    def _scan_cooperation_types(self) -> set[CooperationType]:
        """兼容原有调用方，只返回奖励类型，不包含入口类型。"""
        return {cooperation_type for _, cooperation_type in self._scan_cooperation_results()}

    def _scan_cooperation_results(self) -> list[CooperationResult] | set[CooperationResult]:
        timer = Timer(self.scan_timeout).start()
        stable_timer = None
        previous: list[CooperationResult] | None = None
        stable_frames = 0
        while not timer.reached():
            self.owner.screenshot()
            if self._wanted_quests_page_detected():
                if stable_timer is None:
                    stable_timer = Timer(self.stability_timeout).start()
                infos = self._get_cooperation_info()
                found = []
                for item in infos:
                    cooperation_type = item.get("type")
                    source = str(item.get("source", "normal"))
                    if source == "normal":
                        if cooperation_type != CooperationType.Jade:
                            continue
                    elif source == "realworld":
                        if cooperation_type not in {CooperationType.Jade, CooperationType.Sushi}:
                            continue
                    else:
                        continue
                    result = (source, cooperation_type)
                    if result not in found:
                        found.append(result)
                if found:
                    if found == previous:
                        stable_frames += 1
                    else:
                        previous = found
                        stable_frames = 1
                        stable_timer.reset()
                    if stable_timer.reached() and stable_frames >= 2:
                        return found
                    time.sleep(0.15)
                    continue
                if found == previous:
                    stable_frames += 1
                else:
                    previous = found
                    stable_frames = 1
                    stable_timer.reset()
                # 空结果需要在短窗口内持续稳定，避免页面刚加载就过早记录无协作。
                if stable_timer.reached():
                    if stable_frames >= 2:
                        return set()
                    raise TimeoutError("悬赏封印协作卡槽结果未稳定")
            time.sleep(0.15)
        raise TimeoutError("悬赏封印页面识别超时")

    def _get_cooperation_info(self) -> list[dict]:
        """先确认卡槽存在，再通过固定标识区分协作来源并读取奖励。"""
        self.screenshot()
        results = []
        for index in range(1, 4):
            normal_button = getattr(self, f"I_WQ_INVITE_{index}")
            realworld_button = getattr(self, f"I_WQ_INVITE_{index}_REALWORLD")
            # 加号只用于确认卡槽存在，不再承担普通和现世的来源判断。
            if self.appear(normal_button):
                button = normal_button
            elif self.appear(realworld_button):
                button = realworld_button
            else:
                # 保持原有首个空卡槽即停止后续扫描的行为。
                break

            if self.appear(getattr(self, f"I_IS_REALWORLD_{index}")):
                source = "realworld"
                button = realworld_button
            elif self.appear(getattr(self, f"I_IS_NORMAL_{index}")):
                source = "normal"
                button = normal_button
            else:
                logger.warning("协作卡槽来源未识别：卡槽=%s", index)
                continue

            cooperation_type = self._detect_cooperation_type(index)
            logger.info(
                "协作卡槽识别：卡槽=%s 来源=%s 奖励=%s",
                index,
                source,
                cooperation_type.name if cooperation_type is not None else "unknown",
            )
            if cooperation_type is not None:
                results.append({"type": cooperation_type, "inviteBtn": button, "source": source})
        logger.info("get cooperation size %s", len(results))
        return results

    def _detect_cooperation_type(self, index: int) -> CooperationType | None:
        checks = (
            ("JADE", CooperationType.Jade),
            ("DOG_FOOD", CooperationType.Food),
            ("CAT_FOOD", CooperationType.Food),
            ("SUSHI", CooperationType.Sushi),
            ("GOLD", CooperationType.Gold),
        )
        for name, cooperation_type in checks:
            if self.appear(getattr(self, f"I_WQ_COOPERATION_TYPE_{name}_{index}")):
                return cooperation_type
        return None

    def _return_to_main(self) -> None:
        timer = Timer(self.exit_timeout).start()
        try:
            while not timer.reached():
                self.owner.screenshot()
                current = self.owner.get_current_page(skip_first_screenshot=True, fallback=False)
                if current == page_main:
                    return
                if self.owner.appear_then_click(self.owner.I_UI_BACK_RED, interval=0.8):
                    continue
                if self.owner.goto_page(page_main, timeout=2):
                    return
        except Exception as exc:
            logger.warning("协作检查退出悬赏页面异常：%s", exc)
        raise TimeoutError("退出悬赏封印页面超时")

    @staticmethod
    def _format_result(found_types: set[CooperationType] | list[CooperationResult] | set[CooperationResult]) -> str:
        # 兼容旧调用方只传入奖励枚举的情况。
        if not any(isinstance(item, tuple) for item in found_types):
            reward_types = set(found_types)
            if CooperationType.Jade in reward_types and CooperationType.Sushi in reward_types:
                return "jade+sushi"
            if CooperationType.Jade in reward_types:
                return "jade"
            if CooperationType.Sushi in reward_types:
                return "sushi"
            return "none"

        labels = []
        label_map = {
            ("normal", CooperationType.Jade): "普通勾协",
            ("normal", CooperationType.Sushi): "普通体协",
            ("realworld", CooperationType.Jade): "现世勾协",
            ("realworld", CooperationType.Sushi): "现世体协",
        }
        for item in found_types:
            if isinstance(item, tuple):
                source, cooperation_type = item
            else:
                source, cooperation_type = "normal", item
            label = label_map.get((str(source), cooperation_type))
            if label and label not in labels:
                labels.append(label)
        return "+".join(labels) if labels else "无"

"""账号轮换中只检查悬赏封印协作卡槽的局部适配器。"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image

from module.exception import OcrUnavailableError, ImageFrameExpiredError
from module.base.timer import Timer
from module.exception import RequestHumanTakeover
from module.logger import logger
from module.multi_account.rotation_runner import DailyTaskOutcome
from module.multi_account.daily_task_images import CooperationImage
from tasks.GameUi.page import page_main
from tasks.WantedQuests.assets import WantedQuestsAssets
from tasks.WantedQuests.config import CooperationType


CooperationResult = tuple[str, CooperationType]


class CooperationCleanupError(RequestHumanTakeover):
    """仅表示协作检查后无法确认页面已安全清理。"""


@dataclass(slots=True)
class CooperationAdapter(WantedQuestsAssets):
    """复用悬赏封印协作识别，但不进入好友邀请和悬赏执行流程。"""

    owner: object
    entry_timeout: float = 12.0
    scan_timeout: float = 8.0
    stability_timeout: float = 2.0
    exit_timeout: float = 8.0
    direct_exit_settle_timeout: float = 3
    cooperation_images: tuple[CooperationImage, ...] = field(default=(), init=False)

    def __getattr__(self, name: str):
        """将悬赏识别方法需要的设备操作转发给当前每日任务对象。"""
        return getattr(self.owner, name)

    def run(self) -> DailyTaskOutcome:
        outcome: DailyTaskOutcome
        service_failed = False
        entered = False
        try:
            self._open_wanted_quests()
            entered = True
            found_results = self._scan_cooperation_results()
            result = self._format_result(found_results)
            logger.info("账号轮换协作检查完成：结果=%s", result)
            outcome = DailyTaskOutcome(success=True, result=result, cooperation_images=self.cooperation_images)
        except (OcrUnavailableError, ImageFrameExpiredError):
            # 服务故障后交外层暂停轮换，不继续导航或覆盖成退出失败。
            service_failed = True
            raise
        finally:
            if entered and not service_failed:
                try:
                    self._return_to_main()
                except (OcrUnavailableError, ImageFrameExpiredError):
                    raise
                except RequestHumanTakeover:
                    raise
                except Exception as exc:
                    logger.error("协作检查返回庭院失败，停止账号轮换：%s", exc)
                    raise CooperationCleanupError(
                        "协作检查未能确认返回庭院，停止切换下一个账号"
                    ) from exc
        return outcome

    def _open_wanted_quests(self) -> None:
        if not self.owner.goto_page(page_main, timeout=int(self.entry_timeout)):
            raise TimeoutError("协作检查返回庭院超时")

        timer = Timer(self.entry_timeout).start()
        click_count = 0
        page_frames = 0
        while not timer.reached():
            self.owner.screenshot()
            if self._wanted_quests_page_detected():
                page_frames += 1
                if page_frames >= 2:
                    logger.info("已连续确认悬赏封印标题，开始扫描协作")
                    return
                time.sleep(0.15)
                continue
            page_frames = 0

            # 入口只点击一次；加载期间只观察，不因旧帧重复点击庭院控件。
            if click_count == 0 and self.owner.match_page_once(page_main):
                for rule in (self.I_WQ_SEAL, self.I_WQ_DONE):
                    if self.owner.appear_then_click(rule, interval=0.8):
                        click_count += 1
                        logger.info("点击悬赏入口标识：%s", rule.name)
                        break
            time.sleep(0.15)
        raise RequestHumanTakeover("未能确认进入悬赏封印页面，停止协作检查及切号")

    def _wanted_quests_page_detected(self) -> bool:
        # wq_done 是庭院入口，不是悬赏页标识；必须识别悬赏封印标题。
        return bool(self.owner.appear(self.I_PAGE_WANTED_QUESTS))

    def _scan_cooperation_types(self) -> set[CooperationType]:
        """兼容原有调用方，只返回奖励类型，不包含入口类型。"""
        return {cooperation_type for _, cooperation_type in self._scan_cooperation_results()}

    def _scan_cooperation_results(self) -> list[CooperationResult] | set[CooperationResult]:
        self.cooperation_images = ()
        timer = Timer(self.scan_timeout).start()
        stable_timer = None
        previous = None
        stable_frames = 0
        while not timer.reached():
            self.owner.screenshot()
            infos = self._get_cooperation_info() if self._wanted_quests_page_detected() else None
            if infos is not None:
                if stable_timer is None:
                    stable_timer = Timer(self.stability_timeout).start()
                found = []
                matched = []
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
                    matched.append(item)
                    result = (source, cooperation_type)
                    if result not in found:
                        found.append(result)
                if found:
                    signature = [
                        (item.get("slot"), item.get("source", "normal"), item["type"])
                        for item in matched
                    ]
                    if signature == previous:
                        stable_frames += 1
                    else:
                        previous = signature
                        stable_frames = 1
                        stable_timer.reset()
                    if stable_timer.reached() and stable_frames >= 2:
                        self.cooperation_images = self._capture_cooperation_images(matched)
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
            else:
                stable_timer = None
                previous = None
                stable_frames = 0
            time.sleep(0.15)
        raise TimeoutError("悬赏封印页面或协作卡槽未能稳定识别")

    def _get_cooperation_info(self) -> list[dict] | None:
        """卡槽可见但内容未识别时，本帧结果未确认。"""
        self.screenshot()
        if not self._wanted_quests_page_detected():
            raise RequestHumanTakeover("扫描时悬赏页面未确认，停止协作检查及切号")
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
                return None

            cooperation_type = self._detect_cooperation_type(index)
            logger.info(
                "协作卡槽识别：卡槽=%s 来源=%s 奖励=%s",
                index,
                source,
                cooperation_type.name if cooperation_type is not None else "unknown",
            )
            if cooperation_type is None:
                return None
            results.append({"type": cooperation_type, "inviteBtn": button, "source": source, "slot": index})
        logger.info("get cooperation size %s", len(results))
        return results

    def _capture_cooperation_images(self, infos: list[dict]) -> tuple[CooperationImage, ...]:
        """从识别成功的同一帧裁取卡槽，不额外截图、点击或进入详情页。"""
        pictures = []
        for info in infos:
            try:
                index = info["slot"]
                frame = self.owner.device.image
                if index not in {1, 2, 3} or frame.shape != (720, 1280, 3):
                    raise ValueError("协作截图尺寸或卡槽不符合现有坐标系")
                # 按新卡槽间距裁切，向左留出突出卡框的邀请加号。
                left = (104, 372, 640)[index - 1]
                crop = Image.fromarray(frame[110:630, left:left + 268])
                stream = BytesIO()
                crop.save(stream, format="JPEG", quality=92, subsampling=0)
                label = self._format_result([(info["source"], info["type"])])
                data_uri = "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
                pictures.append(CooperationImage(index, label, data_uri))
            except (OcrUnavailableError, ImageFrameExpiredError):
                raise
            except Exception as exc:
                # 展示图失败不能影响结果记录及 finally 中的庭院退出守卫。
                logger.warning("协作卡槽截图失败，保留文字结果：%s", exc)
        return tuple(pictures)

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
        self.owner.screenshot()
        # 协作识别结束后，只要仍在悬赏封印页面，就统一走专用退出。
        # 是否识别到卡槽/奖励只影响扫描结果，不应改变退出流程。
        if self._wanted_quests_page_detected():
            if self._return_to_main_by_dedicated_exit():
                return
            # 已尝试退出后不再导航或补点，避免落到关闭后露出的庭院控件。
            raise TimeoutError("悬赏封印专用退出未确认庭院，停止追加点击")
        # 页面已变化时只确认庭院，不在未知页尝试通用红叉或导航。
        if self._dedicated_exit_main_confirmed():
            time.sleep(0.15)
            self.owner.screenshot()
            if self._dedicated_exit_main_confirmed():
                return
        raise CooperationCleanupError("悬赏页面和庭院均未确认，停止退出及切号")

    def _return_to_main_by_dedicated_exit(self) -> bool:
        """只在悬赏页确认存在时点击专用退出，避免坐标落到庭院活动入口。"""
        timer = Timer(self.exit_timeout).start()
        while not timer.reached():
            self.owner.screenshot()
            # 退出坐标在庭院右上区域也有控件；页面已切走或未识别时绝不能盲点。
            if not self._wanted_quests_page_detected():
                return self._wait_for_main_after_dedicated_exit(timer)
            # 悬赏标题与关闭按钮均须在当前帧成立，点击命中的按钮而不是固定坐标。
            if self.owner.appear_then_click(self.I_WQ_EXIT_BUTTON, interval=3):
                logger.info("悬赏关闭按钮已识别并点击一次，仅等待庭院，不再补点")
                return self._wait_for_main_after_dedicated_exit(timer)
            time.sleep(0.1)
        return False

    def _wait_for_main_after_dedicated_exit(self, exit_timer: Timer) -> bool:
        """等待页面切换，并排除活动页后再确认回到庭院。"""
        settle_timer = Timer(self.direct_exit_settle_timeout).start()
        main_confirmations = 0
        while not exit_timer.reached():
            self.owner.screenshot()
            if self._activity_page_detected():
                logger.warning("悬赏封印专用退出后进入活动页，停止使用固定退出坐标")
                return False

            if self._dedicated_exit_main_confirmed():
                main_confirmations += 1
                # 悬赏关闭动画期间庭院底图可能已露出；必须等待切换完成，
                # 再连续确认两帧，不能因一次误匹配直接结束。
                if settle_timer.reached() and main_confirmations >= 2:
                    logger.info("悬赏封印专用退出已稳定确认庭院")
                    return True
            else:
                main_confirmations = 0

            time.sleep(0.1)
        return False

    def _dedicated_exit_main_confirmed(self) -> bool:
        """专用退出的庭院确认必须同时排除悬赏页和活动页。"""
        red_close = getattr(self.owner, "I_UI_BACK_RED", None)
        red_close_visible = bool(red_close and self.owner.appear(red_close))
        main_visible = self.owner.appear(self.owner.I_CHECK_MAIN)
        if not main_visible:
            main_visible = (
                self.owner.get_current_page(skip_first_screenshot=True, fallback=False)
                == page_main
            )
        return (
            not self._wanted_quests_page_detected()
            and not self._activity_page_detected()
            and not red_close_visible
            and main_visible
        )

    def _activity_page_detected(self) -> bool:
        activity_check = getattr(self.owner, "I_CHECK_ACTIVITY", None)
        return bool(activity_check and self.owner.appear(activity_check))

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

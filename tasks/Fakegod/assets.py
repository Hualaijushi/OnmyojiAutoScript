from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr


class FakegodAssets:
    """伪神降临独立运行所需资产。"""

    # 爬塔模式、阵容与挑战
    I_LOCK = RuleImage(roi_front=(779,648,31,30), roi_back=(685,612,330,86), threshold=0.7, method="Template matching", file="./tasks/Fakegod/fg/as_lock.png")
    I_UNLOCK = RuleImage(roi_front=(779,648,31,30), roi_back=(686,610,313,92), threshold=0.7, method="Template matching", file="./tasks/Fakegod/fg/as_unlock.png")
    I_CLIMB_MODE_PASS = RuleImage(roi_front=(1143,544,21,21), roi_back=(1118,510,119,186), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_climb_mode_pass.png")
    I_CLIMB_MODE_AP = RuleImage(roi_front=(1093,542,22,25), roi_back=(1055,495,202,219), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_climb_mode_ap.png")
    I_CLIMB_MODE_AP100 = RuleImage(roi_front=(1186,665,22,25), roi_back=(1055,495,202,219), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_climb_mode_ap100.png")
    I_AP_UNLOCK = RuleImage(roi_front=(779,648,31,30), roi_back=(686,610,313,92), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_ap_unlock.png")
    I_AP_LOCK = RuleImage(roi_front=(779,648,31,30), roi_back=(686,610,313,92), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_ap_lock.png")
    I_ACT_FIRE = RuleImage(roi_front=(1139,599,84,45), roi_back=(1080,530,192,190), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_act_fire.png")

    # 页面导航
    I_MAIN_GOTO_ACT = RuleImage(roi_front=(1188,304,35,28), roi_back=(1164,134,83,393), threshold=0.7, method="Template matching", file="./tasks/Fakegod/fg/as_main_goto_act.png")
    I_SKIP_BUTTON = RuleImage(roi_front=(1159,37,51,22), roi_back=(1141,27,86,43), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_skip_button.png")
    I_TO_BATTLE_MAIN = RuleImage(roi_front=(598,407,39,139), roi_back=(533,291,155,370), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_to_battle_main.png")
    I_TO_BATTLE_BOSS = RuleImage(roi_front=(935,250,35,123), roi_back=(876,165,234,327), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_to_battle_boss.png")
    I_CHECK_BATTLE_BOSS = RuleImage(roi_front=(151,18,129,46), roi_back=(141,0,151,85), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_check_battle_boss.png")
    I_BATTLE_MAIN_TO_RECORDS = RuleImage(roi_front=(1015,560,39,42), roi_back=(674,539,439,157), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_battle_main_to_records.png")
    I_AS_CHECK_MAIN_2 = RuleImage(roi_front=(153,19,164,39), roi_back=(116,0,256,92), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_as_check_main_2.png")
    I_AS_OPEN_EYE = RuleImage(roi_front=(1198,300,60,54), roi_back=(1146,253,134,217), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_as_open_eye.png")
    I_AS_LOCATE = RuleImage(roi_front=(1212,394,34,36), roi_back=(1146,253,134,217), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_as_locate.png")
    I_AS_CLOSE_EYE = RuleImage(roi_front=(1197,297,63,57), roi_back=(1146,253,134,217), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_as_close_eye.png")
    I_AS_TO_PASS = RuleImage(roi_front=(624,505,38,35), roi_back=(273,141,759,475), threshold=0.65, method="Template matching", file="./tasks/Fakegod/fg/as_as_to_pass.png")
    I_TO_BATTLE_AP = RuleImage(roi_front=(825,321,39,139), roi_back=(720,255,238,269), threshold=0.8, method="Template matching", file="./tasks/Fakegod/fg/as_to_battle_ap.png")

    # 资源数量与百体入口 OCR
    O_REMAIN_AP = RuleOcr(roi=(1123,24,95,34), area=(1123,24,95,34), mode="Quantity", method="Default", keyword="", name="remain_ap")
    O_REMAIN_PASS = RuleOcr(roi=(539,23,88,31), area=(539,23,88,31), mode="DigitCounter", method="Default", keyword="", name="remain_pass")
    O_REMAIN_BOSS = RuleOcr(roi=(1169,668,70,30), area=(1169,668,70,30), mode="DigitCounter", method="Default", keyword="", name="remain_boss")
    O_REMAIN_AP100 = RuleOcr(roi=(922,21,112,39), area=(913,8,131,62), mode="Digit", method="Default", keyword="", name="remain_ap100")
    O_ENTER_AP100 = RuleOcr(roi=(67,99,92,359), area=(67,99,92,359), mode="Full", method="Default", keyword="雪山修行", name="enter_ap100")

# This Python file uses the following encoding: utf-8
from enum import Enum

from pydantic import BaseModel, Field


class QuickLoadoutMode(str, Enum):
    NUMBER = 'mode_number'
    OCR = 'mode_ocr'


class QuickLoadoutConfig(BaseModel):
    """战斗界面内的一键配置。"""

    enable: bool = Field(default=False, description='quick_loadout_enable_help')
    mode: QuickLoadoutMode = Field(default=QuickLoadoutMode.NUMBER, description='quick_loadout_mode_help')
    group_number: int = Field(default=1, description='quick_loadout_group_number_help', ge=1, le=7)
    preset_number: int = Field(default=1, description='quick_loadout_preset_number_help', ge=1)
    group_name: str = Field(default='', description='quick_loadout_group_name_help')
    preset_name: str = Field(default='', description='quick_loadout_preset_name_help')

    def validate_target(self) -> None:
        if self.mode != QuickLoadoutMode.OCR:
            return
        if not self.group_name.strip():
            raise ValueError('Quick loadout group name cannot be empty in OCR mode')
        if not self.preset_name.strip():
            raise ValueError('Quick loadout preset name cannot be empty in OCR mode')


class NamedQuickLoadoutConfig(QuickLoadoutConfig):
    """支持按任务关卡名称选择不同预设的一键配置。"""

    custom_preset_enable: bool = Field(
        default=False,
        description='quick_loadout_custom_preset_enable_help',
    )
    custom_preset: str = Field(
        default='ALL:(1,1);',
        description='quick_loadout_custom_preset_help',
    )

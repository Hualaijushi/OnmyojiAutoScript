"""任务结束结果与排期分离；只在确认排期写入后报告可继续。"""
from datetime import datetime

from module.logger import logger


def report_scheduled_outcome(config, task: str, key: str, status: str) -> bool:
    """确认本次确实调用过排期，且内存与磁盘的时间一致，再报告结果。"""
    if status not in ('completed', 'retry_scheduled'):
        raise ValueError('未知任务结果')
    try:
        if key not in config.__dict__.get('last_task_delay', {}):
            return False
        model_time = getattr(config.model, key).scheduler.next_run
        disk_time = config.model.read_json(config.config_name)[key]['scheduler']['next_run']
        if isinstance(disk_time, str):
            disk_time = datetime.fromisoformat(disk_time)
        if not isinstance(model_time, datetime) or model_time != disk_time:
            return False
    except (AttributeError, KeyError, TypeError, ValueError, OSError):
        logger.warning(f'{task} 排期无法确认，轮换结果保持未知')
        return False
    config.task_runtime_outcome = {'task': task, 'status': status}
    logger.info(f'{task} 轮换任务结果: {status}')
    return True

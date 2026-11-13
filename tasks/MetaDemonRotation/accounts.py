"""按本实例的独立范围解析账号，不修改其他轮换设置。"""

from module.multi_account.account_manager import AccountManager


def accounts_for_range(instance, account_source, start: int, end: int):
    if not (type(start) is int and type(end) is int and 1 <= start <= end <= 20):
        raise ValueError('账号范围必须为 1～20 且起始序号不大于结束序号')
    raw = list(getattr(account_source, 'account_list', account_source) or [])
    # 资料不足时保留占位账号，以便明确记录跳过原因。
    raw.extend([None] * max(0, end - len(raw)))
    positions = list(range(start, end + 1))
    manager = AccountManager(instance, raw, order=positions, enabled=positions)
    return manager.get_accounts_for_instance()

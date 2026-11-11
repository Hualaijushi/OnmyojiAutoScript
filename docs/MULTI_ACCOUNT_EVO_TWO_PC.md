# 两台电脑分担组队觉醒和超鬼王门票

## 运行中修改范围的补充

已有OAS进程时，通过当前版本的配置界面或后端配置接口设置三端相同范围，并反查接口与磁盘值。只修改JSON文件可能被旧进程内存配置再次保存覆盖；先重启OAS加载新配置模型，再更新范围。三端旧任务都需要重载，不能仅让队长用新范围而队员仍持有旧内存。

2026-11-11本机曾出现group_end回到0而共享范围仍1～10的启动保护；已通过当前后端接口恢复结束组10，199场断点和人工完成记录保留。不要为消除报错删同步文件或把group_end改回全部组。

两台电脑各有完整的 oas3（队长）、oas4（队员一）、oas5（队员二）。本机跑第1～10组，另一台跑第11～20组。组号始终对应原账号槽位，不能把第11组重新填成第1组。两台电脑各自保存进度、锁和日志，不跨电脑同步；不要让同一账号同时在两台电脑登录。

## 获取代码

分支为 `zoombies-account-rotation-dailytask/synevo`。另一台已有同仓库且工作区干净时，在项目目录执行：

```powershell
git fetch origin
git switch zoombies-account-rotation-dailytask/synevo
git pull --ff-only origin zoombies-account-rotation-dailytask/synevo
```

首次获取源码：

```powershell
git clone --branch zoombies-account-rotation-dailytask/synevo --single-branch https://github.com/Hualaijushi/OnmyojiAutoScript.git yysoas
```

Git提供源码，不包含本机Python工具包、模拟器、账号配置和运行进度。另一台须已有可运行的OAS环境；新安装按照仓库安装说明准备依赖与工具包。不要用远程仓库传账号配置。

## 三端配置

通过私下文件传输将 `config/oas3.json`、`oas4.json`、`oas5.json` 的账号设置复制到另一台，先备份另一台原配置；分别调整设备连接地址、模拟器路径等机器相关设置。保留全部20组账号及原iOS/安卓分界，`group_count=20`。

两台各自的三个配置中，`multi_account_evo.multi_account_evo_config` 设置如下：

| 字段 | 本机 | 另一台 |
| --- | --- | --- |
| group_start | 1 | 11 |
| group_end | 10 | 20 |
| event_progress_enable | true | true |
| event_ocr_start | 200 | 200 |
| event_ocr_interval | 10 | 10 |
| battle_count | 250 | 250 |

三端角色保持leader/member_1/member_2各一个，关联账号仍对应同一原组号，启用组队觉醒且关闭同配置普通觉醒调度。范围默认1～全部组（group_end=0），因此另一台必须在第一次启动前设置11～20。三端范围不同、内存配置未重载或同日已有另一范围的进度都会拒绝启动，避免静默借用错误断点。

更改配置后停止并重新加载三个任务/OAS，再由用户运行。本机第一次分配范围采用备份、原锁内显式迁移，保留第一组人工完成、其他组逐场计数、票数和每日状态；不自动清空进度。已有其他范围的机器不要删除状态强行重跑，应先核对是否有需要保留的当天记录。

## 进度与日志

不要把正在使用的 `.multi_account_evo_event_50_sync.json`、普通觉醒同步文件、`.multi_account_daily_state.json`、锁、备份和运行日志复制到另一台覆盖。另一台首次运行会从第11组建立自己的活动状态。

门票模式第1～199把不读门票，第200把起每10把采样；首次50/50需新截图复核。已达标账号继续陪跑，仅三端均达标且安全收尾才完成；250把仍未齐全则停止并保留未完成。普通次数模式保持原完成规则。

每台查看自己 `log/dailytask/index.html?open=latest`，进入“超鬼王门票情况”；另一台可为自己的index创建“每日任务日志”快捷方式。本机日报只显示本机负责范围，两个HTML不自动合并。真实OCR准确率、活动弹窗和长时间三端运行速度仍需自然运行验证，离线测试不能证明现场表现。

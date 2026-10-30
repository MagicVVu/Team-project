# 库存归类确认与详情调整

2026-10-30，Asia/Shanghai。

登录后的库存新增确认流程（手动、语音审核、照片审核）恢复匹配询问：服务端名称匹配为完全相同，或共享连续至少两个字符时，先展示候选类别，允许“归为一类”“单独归类”或取消；没有匹配时直接保存。相同product的逐件候选在弹窗中去重，多个类别可选择具体目标。匹配读取失败不会静默入库，超时仍按原请求恢复，切换家庭后旧选择失效。

后端现在真实执行显式选择：separate新建独立商品，existing使用指定候选，并验证家庭归属、物品版本与商品版本。批量新增仍一件一条，原名称保留。没有选择字段的AI草稿和旧请求维持原有自动归类兼容。没有改动游客模式的本地自动分组。

库存详情不再展示生命周期“状态”字段；“购入日期”改为“入库日期”，“开封日期”改为“开封状态”，根据既有开封记录展示已开封/未开封。日期数据沿用原有记录，没有改写历史日期。

验证：74项JVM测试、22项独立PostgreSQL测试、8项离线设备界面测试通过。正式部署后另用设备已有账号通过3项真实服务器只读测试，验证库存读取、详情展示及匹配弹窗；未创建生产测试库存或采购项。参见 [verification.json](verification.json)、[设备测试](device-tests.log) 和 [发布后真实读取](live-after-deploy.log)。

通过ssh magicvvu发布后端单文件覆盖镜像 `magicvvu/backend:grouping-confirmation-20261030`，保持当前P8.6的AI服务、数据库、环境变量、端口和挂载。无需数据库迁移。第一次发布因候选文件权限检查失败自动恢复旧镜像，修正权限后再次发布成功，源码摘要与本地一致，服务healthy。备份位于服务器 `/srv/magicvvu/releases/grouping-confirmation-20261030`。参见 [部署检查](deployment.json)。

连接的模拟器已保留登录和数据覆盖升级至6 / 1.2.2-inventory。新版 [APK](../../frontend/app/build/outputs/apk/debug/mewstow-1.2.2-inventory.apk)，真实服务器的 [归类弹窗](grouping-dialog.png) 与 [库存详情](inventory-detail.png)。未提交或推送Git，保留本轮开始前已有未提交修改。

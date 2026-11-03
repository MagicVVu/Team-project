# MuMu最新版更新记录

日期：2026-10-28。更新归属：Garin测试工作。结果：覆盖安装与启动检查完成。

|项目|实际结果|
|---|---|
|源码基线|aea6411d868ff30e64ab440239de8bbba7059f09|
|目标设备|MuMu Android12，emulator-5556，V2362A|
|安装版本|1.0 → 1.2.0-test，versionCode 4|
|包名|com.example.teamapp|
|覆盖方式|同签名 adb install -r --no-streaming；未卸载、未清数据|
|安装包|Mewstow-aea6411-debug.apk，64,633,421字节|
|APK SHA256|3b65cdbedfc9391857b80316e998bc3baeb6203653bd312d259a8fd3334bcab4|
|设备实际APK|与本次构建产物哈希一致|
|数据|原15条库存完整，ID与原有字段不变；采购仍0条；照片引用仍0条|
|启动|登录页和游客首页可用，观察期间未发现启动崩溃|
|默认服务器地址|https://8.134.172.165:8000；本轮未登录或请求业务服务|

## 备份与文件保护

原应用的shared_prefs与files已打包保存在仓库外，另留旧APK与更新前后状态用于核对。私密备份位置：`C:\Users\ASUS\AppData\Local\GarinBackups\MuMu_20261028_aea6411`。不要把私密备份上传Git。

本轮核对了2016个原跟踪文件及200个隔离副本输入，内容未变化；只在自己的交接目录追加链接。未修改队友源码、构建配置、数据库或Jev配置，未提交或推送Git。APK本机保留，默认被本目录.gitignore排除，避免将大型构建文件混入提交。

## 构建与检查范围

从最新源码的隔离副本构建，使用本机SDK、JDK21、Gradle9.3.1及原调试签名。首次离线因相机/OCR依赖缺失停止；随后只下载已声明依赖，assembleDebug通过。没有更改依赖版本或屏蔽构建规则。

原仓库附带的10月25日APK与当前安装签名不同，且未包含之后的前端提交，因此没有使用该旧包。最终新包沿用已安装App的签名，覆盖后保留原firstInstallTime，lastUpdateTime更新。

本轮只做版本、签名、数据保留和启动检查，没有重跑全量单测/Lint，也没有测云端登录、业务事务、后端接入或模型质量。更新App不代表Jev已接入，付费模型调用为0。

## 证据

- [安装与版本核验](evidence/apk-verification.json)、[安装日志](evidence/install.log)、[设备包信息](evidence/package-after.txt)。
- [安装后数据检查](evidence/data-after-install.json)、[启动后数据检查](evidence/data-after-startup.json)。
- [登录页截图](evidence/login.png)、[游客首页截图](evidence/guest.png)、[启动结果](evidence/startup-result.json)。
- [离线构建日志](evidence/build-offline.log)、[联网构建日志](evidence/build-online.log)、[文件完整性](evidence/source-integrity.json)。
- [适配记录](evidence/adapter-notes.json)：安装记录脚本自复制与登录按钮文字定位问题均已修正，不计为App功能缺陷，也未因此重复安装。

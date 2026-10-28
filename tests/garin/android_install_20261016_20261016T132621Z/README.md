# 当前 App 构建安装记录

日期：2026-10-16。源码提交：`a251aa033586e915cb49e35bbd242efccb358de6`。

已在独立源码副本构建调试APK并安装到MuMu安卓设备-1，确认登录页及游客首页可打开。检查期间未观察到启动崩溃；这不是完整功能或前后端验收。

## 成果

- APK：`MagicVVu-a251aa0-debug.apk`。
- SHA256：`5d12b4821d01382b3da22bd5c049cc8e6ef824849f8f8ff3c04849fe5fdf5bd7`。
- 设备：MuMu安卓设备-1，Android 12，ADB `127.0.0.1:16416`。
- 软件：拾物，包名 `com.example.teamapp`，版本 1.0。
- 当前停留在游客首页；15种物品为调试构建自动生成的本机示例。

## 证据

- `build-offline.log`：第一次离线尝试，因缺缓存的Kotlin编译依赖而失败。
- `build-online.log`：补齐项目依赖后构建成功。
- `install.log`、`launch.log`：安装和启动结果。
- `screenshots/login.png`、`screenshots/guest.png`：设备实际截图，旁边XML保存当时界面文字。
- `installation-result.json`：版本、APK哈希、设备和核验结论。

## 边界

原工程110个被复制文件的哈希保持不变，构建副本内这110个文件也未变化。没有修改业务源码、卸载旧App、清空设备、登录正式服务或操作云端库存。构建副本被本目录.gitignore忽略，APK与证据留作交付。

今后队友更新源码后，需要重新构建和安装，当前APK不会自动跟随Git更新。
# P1 正式 HTTPS 与 Android

状态：PARTIAL；正式手机验收 NOT_VERIFIED。

沿用 Release 的 mewstowReleaseApiUrl、TargetPolicy 的 HTTPS/0.9.0/isolated_test=false 校验；Debug继续只允许隔离服务。未关闭证书校验、未改环境标志，APK无内部凭据。

命令（frontend目录）：

```powershell
$env:JAVA_HOME='D:\Android Studio\jbr'
.\gradlew.bat :app:testDebugUnitTest :app:assembleRelease -PmewstowReleaseApiUrl=https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net --console=plain
```

构建/单测最终证据见 P6、evidence/P6-android-final.log。产物 frontend/app/build/outputs/apk/release/app-release-unsigned.apk；使用团队受保护签名流程后才能安装，不在仓库新建/提交签名密钥。

首次正式HTTPS系统TLS校验成功、health200、未认证用户/内部路径401；最新复查网络失败，见evidence/P1-public-checks.json，不能确认当前连通。没有使用真实账号登录或改动真实家庭库存。

人工验收：核对APK SHA256与Release配置→团队签名→移动网络登录本人账号→选择家庭→进入云端助手→发送只读库存查询→核对实际数据→关闭/重建应用→恢复原task_id。另验证Debug被正式环境拒绝。保存脱敏时间、task_id、后端版本和手机结果。构建成功不等于这些步骤通过。

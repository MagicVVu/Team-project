# Mew当前素材使用规范

更新：2026-10-21。

普通页面角色以V14无脚奶白盒子猫为形象基准，V16仅补充姿态。当前实现统一从 `frontend/app/src/main/java/com/example/teamapp/ui/MewMascot.kt` 的MewPose选择状态；对应资源为 `frontend/app/src/main/res/drawable-nodpi/mew_*.png`。浅深色共用同一PNG和原色，按场景使用明确语义，不再用十二宫格数字或dark_前缀区分角色身份。

拉绳属于用户确认的V04特殊动作，用AssistantPullMascot.kt和六张maoyou_pull_*.png合成；保留600×768同坐标画布、实际57.6dp宽度和已验证动作。品牌V1字标、无脸猫盒图标另属品牌用途，不当成普通表情猫替换。

当次交付：
- [浅深色实测对照](E:/TM_code/Team-project/ui/Mew统一-20261021/Mew统一实测对照.html)
- [完成清单及边界](E:/TM_code/Team-project/ui/Mew统一-20261021/完成清单.md)
- [状态、源图和哈希](E:/TM_code/Team-project/ui/Mew统一-20261021/Mew状态与源文件.json)

历史范围：ui根目录、light_ui、dark_ui中的早期设计图，以及Mew风格核对-20261021中的审计快照，记录当时的版本，不代表当前Android页面。旧的7张运行角色资源已保存在 `ui/Mew统一-20261021/历史角色资源-不再打包`；应从当前语义资源表选择素材。

V14原图：E:/1-大三上/团队项目/UI设计稿/猫又IP概念稿/猫又-情绪炸毛双尾-十二场景V14-20261012.png。

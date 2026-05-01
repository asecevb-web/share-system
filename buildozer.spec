[app]
title = 文件共享
package.name = fileshare
package.domain = org.fileshare
source.dir = .
source.include_exts = py
version = 0.3
requirements = python3,kivy,requests
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 28
android.minapi = 21
android.accept_sdk_license = True
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 0

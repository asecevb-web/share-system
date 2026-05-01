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
android.api = 35
android.minapi = 24
android.accept_sdk_license = True
android.archs = arm64-v8a
android.ndk = 27
android.ndk_api = 24

# 16KB page alignment flags for all native builds
android.extra_cflags = -DANDROID_PAGE_SIZE=16384
android.extra_ldflags = -Wl,-z,max-page-size=16384

[buildozer]
log_level = 2
warn_on_root = 0

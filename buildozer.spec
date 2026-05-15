[app]
title = FileShare
package.name = fileshare
package.domain = org.fileshare
source.dir = .
source.include_exts = py,ttf
version = 0.7
requirements = python3,kivy,requests
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 28
android.minapi = 21
android.accept_sdk_license = True
android.archs = arm64-v8a
android.keystore = keystore/fileshare.keystore
android.keystore_pass = android
android.key_alias = fileshare
android.key_pass = android

[buildozer]
log_level = 2
warn_on_root = 0

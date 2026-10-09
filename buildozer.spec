[app]
title = Pebolim Arcade
package.name = pebolimarcade
package.domain = org.pebolim
source.dir = .
source.include_exts = py
version = 0.1
requirements = python3==3.10.12,hostpython3==3.10.12,pygame
orientation = landscape
fullscreen = 1
android.permissions = INTERNET
android.archs = arm64-v8a
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1

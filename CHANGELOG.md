# Changelog

## [0.5.0](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.4.0...jazzy-v0.5.0) (2026-07-17)


### Neue Features

* **navigation:** drive Position tile from map-frame robot_pose ([29c6b48](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/29c6b48931ff03caafc78ac451877104b97e9c3c))
* **navigation:** drive Position tile from map-frame robot_pose ([ed34d9e](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/ed34d9eda79e70ce24cd39593bc5425537d64871))
* **navigation:** live SLAM map via rosbridge WebSocket ([063a777](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/063a77737456f1804bb5430271baca5f9c7d9ba7))
* **navigation:** live SLAM map via rosbridge WebSocket ([933752d](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/933752dbae16c46d753f62648d2477f4d3326050))
* **navigation:** save current pose with auto-name, map_id and timestamp ([42e00d0](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/42e00d04dd35e2d3dc00bbe0049b45c9ecf7e736))
* **navigation:** save current pose with auto-name, map_id and timestamp ([b5a31b8](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/b5a31b8684c468d0e3aaf3055285b4d1da5e8a66))
* **navigation:** show live nav feedback (distance/ETA/recoveries) ([3441a9c](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/3441a9c4a57dfde42f0b4d995b4befe93f911b19))
* **navigation:** show live nav feedback (distance/ETA/recoveries) ([e244774](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/e244774a35a45430ca6f3c8a77ac4b7f0c22dffd))
* **teleop:** add live odometry mini-tile ([8759fd0](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/8759fd0e953bd269e094472a892c1eb1a2acb4fa))
* **teleop:** add live odometry mini-tile ([6e2a56e](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/6e2a56eec9181d300bdd086db0296ac26ffca55b))


### Bug Fixes

* **navigation:** stay on navigation page after saving/navigating a pose ([20aa3d5](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/20aa3d57fdd5484d936d5c51c0c129cfd8cfe163))
* **navigation:** stay on navigation page after saving/navigating a pose ([1204e36](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/1204e367ace08b50aa55c8874e2aa515be60eb9c))
* **sse:** coalesce odometry backlog so velocity/pose panels stay live ([737901e](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/737901ea73d9e8bec2a7d144c3c3c5cb8d1bd436))
* **sse:** coalesce odometry backlog so velocity/pose stay live ([749a6fd](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/749a6fd3b2ae19b74deaa46303e2b8b8f76e7c6b))
* **sse:** give each connection its own queue so tabs stop stealing messages ([228e52f](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/228e52f510e72cda14f4530b8d272ed2dc30bc92))
* **sse:** per-connection queues so browser tabs stop stealing each other's messages ([bfd7e31](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/bfd7e31218dd354400961a0b8ab4a2b508e16e74))
* **teleop:** convert motor input_voltage from mV to V in voltage tile ([5a65b28](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/5a65b286e1e9413c8f0ef7efcac846b784b0746d))
* **teleop:** lower server-side linear_x clamp to 0.31 m/s ([59a0d25](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/59a0d25229ada8a06c935b7bc795a08d6697c8ab))
* **teleop:** lower server-side linear_x clamp to 0.31 m/s ([aa7e2b9](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/aa7e2b923b0a4b1a6f8307b8049b2c024dcd191d))
* **teleop:** show motor voltage in volts (mV-&gt;V) in voltage tile ([9434c94](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/9434c9432dd40db9afd0ab4672ff8d55ee2b8dd2))
* **webapp:** throttle odometry velocity so the display stays real-time ([a0d06d4](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/a0d06d433021feb81c36c09dd58ac306fa74dd5c))
* **webapp:** throttle odometry velocity so the display stays real-time ([72177de](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/72177de2cdd4a2ec628217a5305c61a9c7bd676c))

## [0.4.0](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.3.1...jazzy-v0.4.0) (2026-06-23)


### Neue Features

* **versions:** show deployed service versions in navbar ([6f900a6](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/6f900a61af573e33233d4a9b4f2626936f8292a0))
* **versions:** show deployed service versions in navbar ([0b1a9fe](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/0b1a9fe75d4c03401615ca38bc2032db6dfcb259))

## [0.3.1](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.3.0...jazzy-v0.3.1) (2026-06-19)


### Bug Fixes

* **ui:** read motor velocity under the actual dict key ([f8f303c](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/f8f303c2c80fb5dd042ebe033c5962559793fc9f))
* **ui:** read motor velocity under the actual dict key ([398d670](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/398d6709c593b8099f0ce8bd1272d099a87869ee))
* **ui:** show actual system-pi values instead of bucket summaries ([015a21e](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/015a21efcdcd905bcd05f64d958946cdf06ab932))

## [0.3.0](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.2.0...jazzy-v0.3.0) (2026-06-12)


### Neue Features

* **webapp:** touch-joystick teleop + 4-page mobile-first dashboard ([#21](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/21)) ([#22](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/22)) ([8a47778](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/8a4777831094e862699f3cab2d5ab684771859a4))

## [0.2.0](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.1.3...jazzy-v0.2.0) (2026-06-05)


### Neue Features

* **ui:** professional-restraint style overhaul ([#18](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/18)) ([6650803](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/6650803668151167ef17c35e0c66aebb6dfc6abe))
* **ui:** show System Status as text + fix topic-config passthrough ([#17](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/17)) ([64c1fbc](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/64c1fbc198ddfea9adebacec91eced8f02a6728e))

## [0.1.3](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.1.2...jazzy-v0.1.3) (2026-05-31)


### Bug Fixes

* **entrypoint:** drop redundant in-container mosquitto broker ([#13](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/13)) ([2a3e284](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/2a3e284f60ce667405eb451a8f9ea8b1000624e2))
* **webapp:** subscribe to base/odometry; display host/disk/throttle ([#14](https://github.com/cme-research/cmeresearch_amr_webcontrol/issues/14)) ([f95c149](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/f95c149845b2f60ac079e761202594616734b8a8))

## [0.1.2](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.1.1...jazzy-v0.1.2) (2026-05-29)


### Bug Fixes

* **config:** correct cmexa-001 -&gt; cmexaiii-001 namespace in three topic paths ([e62b781](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/e62b7815269973beaf2c2c791681717a3d58f32a))
* **config:** correct cmexa-001 → cmexaiii-001 namespace in app_config.json ([1b34113](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/1b341135db06a8a6e3ec9d568e1c6aec704690f7))

## [0.1.1](https://github.com/cme-research/cmeresearch_amr_webcontrol/compare/jazzy-v0.1.0...jazzy-v0.1.1) (2026-05-24)


### Dokumentation

* add release and CI badges ([b28437e](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/b28437e0219312a93e39204bb8361c87df879380))
* add release and CI badges to README ([805036c](https://github.com/cme-research/cmeresearch_amr_webcontrol/commit/805036c40e43f49cf0b8b466660e6d92f6767a12))

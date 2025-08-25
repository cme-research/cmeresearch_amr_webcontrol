# cmeresearch_amr_webcontrol Dockerfile

docker run -it --rm --name cmexa-webcontrol --privileged --tmpfs /run --tmpfs /run/lock -v /sys/fs/cgroup:/sys/fs/cgroup:ro --network="host" cmexa/webcontrol:1.0
# cmeresearch_amr_webcontrol Dockerfile

docker run -it --rm --name cmexa-webcontrol --network="host" -v /var/run/docker.sock:/var/run/docker.sock cmexa/webcontrol:1.0
# cmeresearch_amr_webcontrol Dockerfile

docker run -it --name cmexa-webcontrol --network="host" -p 1883:1883 --restart=always cmexa/webcontrol:1.0
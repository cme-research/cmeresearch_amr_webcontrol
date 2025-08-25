curl --silent --unix-socket /var/run/docker.sock \
  -H "Content-Type: application/json" \
  -d '{"Image":"alpine","Cmd":["reboot"],"HostConfig":{"Privileged":true,"PidMode":"host"}}' \
  -X POST http://localhost/containers/create \
| jq -r '.Id' \
| xargs -I {} curl --silent --unix-socket /var/run/docker.sock \
    -X POST http://localhost/containers/{}/start
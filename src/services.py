import secrets
import base64
import json
import random
import subprocess
import tempfile
import yaml
import shutil
import socket
import os

from pathlib import Path

def generate_random_password():
    return base64.b64encode(secrets.token_bytes(32)).decode()

def generate_random_port(tmpdir):
    if Path(f"{tmpdir}/used_ports.txt").exists():
        used_ports = set(int(line.split(":")[0]) for line in Path(f"{tmpdir}/used_ports.txt").read_text(encoding="utf-8").splitlines() if line.strip())
    else:
        used_ports = set()

    if Path("src/configuration/allowed_ports.txt").stat().st_size > 0:
        allowed_ports = set(int(line) for line in Path("src/configuration/allowed_ports.txt").read_text(encoding="utf-8").splitlines() if line.strip())
        return random.choice(list(allowed_ports))
    else:
        excluded_ports = set(int(line) for line in Path("src/configuration/excluded_ports.txt").read_text().splitlines() if line.strip())
        available_ports = set(range(2000, 26000 + 1)) - excluded_ports - used_ports
        return random.choice(list(available_ports))

def parse_config():
    if Path("src/configuration/settings.json").stat().st_size == 0:
        return None
    with open("src/configuration/settings.json") as f: 
        return json.load(f)

def generate_tmpdir():
    return tempfile.mkdtemp(prefix="xray-cAD-")

def generate_xray_config(config, tmpdir):
    
    def generate_shadowsocks_inbound(config):
        
        shadowsocks_instances_count = config["xray_inbound_separated_instances"]["shadowsocks_instances_count"]
        shadowsocks_inbound_objects = {}

        for instance_num in range(shadowsocks_instances_count):

            shadowsocks_port = generate_random_port(tmpdir=tmpdir)
            shadowsocks_password = generate_random_password()

            shadowsocks_inbound_object = {
                "tag": f"shadowsocks-{instance_num + 1}", # because it's starts from zero
                "protocol": "shadowsocks",
                "port": shadowsocks_port,
                "listen": "0.0.0.0",
                "settings": {
                    "method": config["xray_shadowsocks_inbound_method"],
                    "network": config["xray_shadowsocks_inbound_network"],
                    "password": shadowsocks_password
                }
            }

            shadowsocks_inbound_objects[instance_num] = shadowsocks_inbound_object

            if config is not None and config["xray_shadowsocks_inbound_network"] in ["tcp,udp", "udp,tcp"]:
                paste_to_used_ports(tmpdir, shadowsocks_port, "tcp")
                paste_to_used_ports(tmpdir, shadowsocks_port, "udp")
            elif config is not None and config["xray_shadowsocks_inbound_network"] == "tcp":
                paste_to_used_ports(tmpdir, shadowsocks_port, "tcp")
            elif config is not None and config["xray_shadowsocks_inbound_network"] == "udp":
                paste_to_used_ports(tmpdir, shadowsocks_port, "udp")

        return shadowsocks_inbound_objects

    def generate_wireguard_outbound(config):

        wireguard_outbound_object = {
            "protocol": "wireguard",
            "listen": "0.0.0.0",
            "settings": {
                "secretKey": config["xray_wireguard_outbound_privatekey"],
                "address": [config["xray_wireguard_outbound_peeraddress"]],
                "mtu": config["xray_wireguard_outbound_mtu"],
                "peers": [{
                        "publicKey": config["xray_wireguard_outbound_publickey"],
                        "endpoint": config["xray_wireguard_outbound_endpoint"]
                }]
            }
        }

        return wireguard_outbound_object

    def generate_freedom_outbound():
        
        freedom_outbound_object = {
            "protocol": "freedom",
        }

        return freedom_outbound_object

    def generate_blackhole_outbound():

        blackhole_outbound_object = {
            "protocol": "blackhole",
            "tag": "black"
        }

        return blackhole_outbound_object

    def check_if_all_values_is_not_empty(dictionary):
        if isinstance(dictionary, dict):
            return all(check_if_all_values_is_not_empty(value) for value in dictionary.values())
        elif isinstance(dictionary, list):
            return all(check_if_all_values_is_not_empty(value) for value in dictionary)
        else:
            return bool(dictionary)

    shadowsocks_inbound_objects = generate_shadowsocks_inbound(config=config)
    
    wireguard_outbound_object = generate_wireguard_outbound(config=config)
    freedom_outbound_object = generate_freedom_outbound()
    blackhole_outbound_object = generate_blackhole_outbound()

    xray_config = {
        "log": {"loglevel":  "debug"},
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "ip": ["geoip:private"],
                    "outboundTag": "block"
                }
            ]
        },
        "inbounds": [],
        "outbounds": []
    }

    if check_if_all_values_is_not_empty(shadowsocks_inbound_objects):
        xray_config["inbounds"].extend(shadowsocks_inbound_objects.values())

    if check_if_all_values_is_not_empty(wireguard_outbound_object):
        xray_config["outbounds"].append(wireguard_outbound_object)
        xray_config["outbounds"].append(freedom_outbound_object)
        xray_config["outbounds"].append(blackhole_outbound_object)
    else:
        xray_config["outbounds"].append(freedom_outbound_object)
        xray_config["outbounds"].append(blackhole_outbound_object)

    if not xray_config["inbounds"]:
        raise ValueError("[-] xray-core: Inbounds can't be empty!")

    with open(f"{tmpdir}/config.json", "w", encoding="utf-8") as f:
        json.dump(xray_config, f, indent=4)

def generate_docker_compose(config, tmpdir):
    
    docker_compose = {
        "services": {
            "xray-core": {
                "image": "ghcr.io/xtls/xray-core:latest",
                "volumes": [f"{tmpdir}/config.json:/usr/local/etc/xray/config.json:ro"],
                "ports": [],
                "restart": "no",
                "dns": ["1.1.1.1","1.0.0.1"]
            }
        }
    }

    with open(f"{tmpdir}/used_ports.txt") as f:
        for line in f:
            port, protocol = line.strip().split(":")
            docker_compose["services"]["xray-core"]["ports"].append(f"{port}:{port}/{protocol}")

    with open(f"{tmpdir}/docker-compose.yml", "w", encoding="utf-8") as f:
        yaml.dump(docker_compose, f, allow_unicode=True, sort_keys=False)

def run_docker_compose(tmpdir):
    subprocess.run(["docker", "compose", "up", "-d"], check=True, cwd=tmpdir)

def stop_docker_compose(tmpdir):
    subprocess.run(["docker", "compose", "down"], check=True, cwd=tmpdir)

def remove_tmpdir(tmpdir):
    shutil.rmtree(tmpdir); print(f"{tmpdir} : removed")

def clean_all():
    if list(Path(tempfile.gettempdir()).glob("xray-cAD-*")):
        for item in list(Path(tempfile.gettempdir()).glob("xray-cAD-*")):
            shutil.rmtree(item); #print(f"{item} : removed")

def paste_to_used_ports(tmpdir, port, protocol):
    with open(f"{tmpdir}/used_ports.txt", "a", encoding="utf-8") as f:
        f.write(f"{port}:{protocol}\n")

def parse_xray_config(tmpdir):
    if Path(f"{tmpdir}/config.json").stat().st_size == 0:
        return None
    with open(f"{tmpdir}/config.json") as f: 
        return json.load(f)

def list_xray_inbound_instances(config, tmpdir):

    xray_config = parse_xray_config(tmpdir=tmpdir)
    
    if xray_config is not None:     
        
        xray_inbound_instances = {
            num: instance["tag"]
            for num, instance in enumerate(xray_config["inbounds"])
        }

    return xray_inbound_instances

def refurbish_xray_inbound_intance(config, tmpdir, instance_num):

    def refurbish_shadowsocks_inbound_instance():

        shadowsocks_port = generate_random_port(tmpdir=tmpdir)
        shadowsocks_password = generate_random_password()

        shadowsocks_inbound_object = {
            "tag": f"shadowsocks-{instance_num + 1}", # because it's starts from zero
            "protocol": "shadowsocks",
            "port": shadowsocks_port,
            "listen": "0.0.0.0",
            "settings": {
                "method": config["xray_shadowsocks_inbound_method"],
                "network": config["xray_shadowsocks_inbound_network"],
                "password": shadowsocks_password
            }
        }

        if config is not None and config["xray_shadowsocks_inbound_network"] in ["tcp,udp", "udp,tcp"]:
            paste_to_used_ports(tmpdir, shadowsocks_port, "tcp")
            paste_to_used_ports(tmpdir, shadowsocks_port, "udp")
        elif config is not None and config["xray_shadowsocks_inbound_network"] == "tcp":
            paste_to_used_ports(tmpdir, shadowsocks_port, "tcp")
        elif config is not None and config["xray_shadowsocks_inbound_network"] == "udp":
            paste_to_used_ports(tmpdir, shadowsocks_port, "udp")

        return shadowsocks_inbound_object

    xray_config = parse_xray_config(tmpdir=tmpdir)

    if xray_config is not None:        

        if xray_config["inbounds"][instance_num]["protocol"] == "shadowsocks":
            inbound_object = refurbish_shadowsocks_inbound_instance()
        else:
            raise ValueError("[-] ... something went wrong. Honestly, I don't really know what exactly.")
        
        xray_config["inbounds"][instance_num] = inbound_object

        with open(f"{tmpdir}/config.json", "w", encoding="utf-8") as f:
            json.dump(xray_config, f, indent=4)

def request_config_for_xray_inbound_instance(config, tmpdir, instance_num):
    
    def get_server_public_ip():
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            sock.connect(("1.1.1.1", 80))
            ip = sock.getsockname()[0]
        except Exception as e:
            raise ValueError("[-] Cannot get server public ip address!")
        finally:
            sock.close()

        return ip
    
    server_public_ip = get_server_public_ip()
    xray_config = parse_xray_config(tmpdir=tmpdir)

    if xray_config is None or server_public_ip is None:
        return

    def get_shadowsocks_inbound_instance_config():
        
        def refactor_mode_parameter(xray_shadowsocks_inbound_method):
        
            if xray_shadowsocks_inbound_method in ("tcp,udp", "udp,tcp"):
                shadowsocks_mode_parameter = "tcp_and_udp"
        
            if xray_shadowsocks_inbound_method == "tcp":
                shadowsocks_mode_parameter = "tcp_only"
        
            if xray_shadowsocks_inbound_method == "udp":
                shadowsocks_mode_parameter = "udp_only"

            return shadowsocks_mode_parameter

        shadowsocks_config = {
            "server": server_public_ip,
            "server_port": xray_config["inbounds"][instance_num]["port"],
            "method": xray_config["inbounds"][instance_num]["settings"]["method"],
            "password": xray_config["inbounds"][instance_num]["settings"]["password"],
            "mode": refactor_mode_parameter(xray_config["inbounds"][instance_num]["settings"]["network"]),
            "local_address": "127.0.0.1",
            "local_port": "1080"
        }

        return shadowsocks_config

    if xray_config["inbounds"][instance_num]["protocol"] == "shadowsocks":
        inbound_instance_config = get_shadowsocks_inbound_instance_config()
    else:
        raise ValueError("[-] ... something went wrong. Honestly, I don't really know what exactly.")

    return inbound_instance_config

def request_instance_protocol(config, tmpdir, instance_num):

    xray_config = parse_xray_config(tmpdir=tmpdir)

    if xray_config is not None:
        return xray_config["inbounds"][instance_num]["protocol"]
    else:
        return None

def request_instance_tag(config, tmpdir, instance_num):

    xray_config = parse_xray_config(tmpdir=tmpdir)

    if xray_config is not None:
        return xray_config["inbounds"][instance_num]["tag"]
    else:
        return None

def remove_content_of_tmpdir(tmpdir):

    for item in Path(tmpdir).iterdir():
        if item.is_file() or item.is_symlink():
            item.unlink()

        if item.is_dir():
            shutil.rmtree(item)
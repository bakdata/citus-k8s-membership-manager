import typing
import yaml
import psycopg2
import time
import os
import signal
import subprocess
import logging

from config import PG_CONF
from contextlib import contextmanager

log = logging.getLogger(__file__)


def run_local_query(query: str, port: int) -> typing.List[typing.Tuple]:
    with db_connector(port) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()


@contextmanager
def db_connector(port: int) -> typing.Iterator[psycopg2._psycopg.connection]:
    try:
        conn = psycopg2.connect(
            dbname=PG_CONF["db"], host="localhost", user=PG_CONF["user"], port=port
        )
        yield conn
    finally:
        conn.close()


class PortForwarder:
    def __init__(
        self, pod_name: str, port_mapping: typing.Tuple[int, int], namespace: str
    ) -> None:
        cmd = "kubectl port-forward {} {}:{} -n {}"
        status_cmd_template = "kubectl get pods --all-namespaces | grep {}"
        if "/" not in pod_name:
            self.status_cmd = status_cmd_template.format(pod_name)
        else:
            self.status_cmd = status_cmd_template.format(pod_name.split("/")[1])

        self.cmd = cmd.format(pod_name, port_mapping[0], port_mapping[1], namespace)

    def __enter__(self) -> None:
        log.info(
            "Pod status: %s",
            subprocess.run(
                [self.status_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            ).stdout,
        )
        self.pid = subprocess.Popen(self.cmd.split(" ")).pid
        time.sleep(1)  # Wait until port forwarding is established
        log.info("Port forwarding created with %s in process %s", self.cmd, self.pid)

    def __exit__(self, *args) -> None:
        os.kill(self.pid, signal.SIGTERM)


def run_kubectl_command(command: str) -> typing.Tuple[int, str, str]:
    result = subprocess.run(
        [command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True
    )

    def parse_output(output) -> str:
        if not output:
            return ""
        return output.decode("utf-8").strip()

    stdout = parse_output(result.stdout)
    stderr = parse_output(result.stderr)
    log.info("Command: %s, Stdout: %s, Stderr: %s", command, stdout, stderr)
    return result.returncode, stdout, stderr


def parse_single_kubernetes_yaml(file_path: str) -> dict:
    with open(file_path, "r") as f:
        return yaml.load(f)

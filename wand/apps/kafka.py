#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

import os
import shutil
import subprocess
import logging
import yaml

from wand.contrib.java import JavaCharmBase

from ops.model import BlockedStatus

from charmhelpers.fetch.ubuntu import apt_update
from charmhelpers.fetch.ubuntu import add_source
from charmhelpers.fetch.ubuntu import apt_install
from charmhelpers.core.host import mount
from charmhelpers.core.templating import render

logger = logging.getLogger(__name__)

__all__ = [
    'KafkaJavaCharmBase'
]

OVERRIDE_CONF = """{% if service_unit_overrides %}
[Unit]
{% for key, value in service_unit_overrides.items() %}
{% if value %}
{{key}}={{value}}
{% endif %}
{% endfor %}

{% endif %}
[Service]
{% for key, value in service_overrides.items() %}
{% if value %}
{% if key =='ExecStart' %}
# If there is an ExecStart override then we need to clear the ExecStart list first
ExecStart=
{% endif %}
{{key}}={{value}}
{% endif %}
{% endfor %}
{% for key, value in service_environment_overrides.items() %}
{% if value %}
Environment="{{key}}={{value}}"
{% endif %}
{% endfor %}""" # noqa


class KafkaJavaCharmBase(JavaCharmBase):

    LATEST_VERSION_CONFLUENT = "6.1"

    @property
    def distro(self):
        return self.config.get("distro", "confluent").lower()

    def __init__(self, *args):
        super().__init__(*args)

    def install_packages(self, java_version, packages):
        version = self.config.get("version", self.LATEST_VERSION_CONFLUENT)
        if self.distro == "confluent":
            url_key = 'https://packages.confluent.io/deb/{}/archive.key'
            key = subprocess.check_output(['wget', '-qO', '-',
                                           url_key.format(version)])
            url_apt = \
                'deb [arch=amd64] https://packages.confluent.io/deb/{}' + \
                ' stable main'
            add_source(
                url_apt.format(version),
                key=key)
            apt_update()
        elif self.distro == "apache":
            raise Exception("Not Implemented Yet")

        apt_install(packages)

    def is_client_ssl_enabled(self):
        # TODO(pguimaraes): add support for certificate endpoint
        # if ssl_* config is set, this takes precedence otherwise
        # vault relation should be used to provide certificates.
        if len(self.config.get("ssl_cert", "")) > 0 and \
           len(self.config.get("ssl_key", "")) > 0:
            return True
        if len(self.config.get("ssl_cert", "")) > 0 or \
           len(self.config.get("ssl_key", "")) > 0:
            logger.warning("Only some of the ssl configurations have been set")
        return False

    def is_ssl_enabled(self):
        return False

    def is_sasl_enabled(self):
        # This method must be implemented per final charm.
        # E.g. zookeeper supports digest and kerberos
        # while broker does not support digest but does support LDAP
        pass

    def is_sasl_oauthbearer_enabled(self):
        return False

    def is_sasl_scram_enabled(self):
        return False

    def is_sasl_plain_enabled(self):
        return False

    def is_sasl_delegate_token_enabled(self):
        return False

    def is_sasl_ldap_enabled(self):
        return False

    def is_sasl_kerberos_enabled(self):
        # TODO(pguimaraes): implement this logic
        return False

    def is_sasl_digest_enabled(self):
        # TODO(pguimaraes): implement this logic
        return False

    def is_jolokia_enabled(self):
        # TODO(pguimaraes): implement this logic
        return False

    def is_jmxexporter_enabled(self):
        # TODO(pguimaraes): implement this logic
        return False

    def create_log_dir(self, data_log_dev,
                       data_log_dir,
                       data_log_fs,
                       user="cp-kafka",
                       group="confluent",
                       fs_options=None):

        if len(data_log_dir or "") == 0:
            logger.warning("Data log dir config empty")
            BlockedStatus("data-log-dir missing, please define it")
            return
        os.makedirs(data_log_dir, 0o750, exist_ok=True)
        shutil.chown(data_log_dir,
                     user=self.config["user"],
                     group=self.config["group"])
        dev, fs = None, None
        if len(data_log_dev or "") == 0:
            logger.warning("Data log device not found, using rootfs instead")
        else:
            for k, v in data_log_dev:
                fs = k
                dev = v
            logger.info("Data log device: mkfs -t {}".format(fs))
            cmd = ["mkfs", "-t", fs, dev]
            subprocess.check_call(cmd)
            mount(dev, data_log_dir,
                  options=self.config.get("fs-options", None),
                  persist=True, filesystem=fs)

    def create_data_and_log_dirs(self, data_log_dev,
                                 data_dev,
                                 data_log_dir,
                                 data_dir,
                                 data_log_fs,
                                 data_fs,
                                 user="cp-kafka",
                                 group="confluent",
                                 fs_options=None):

        if len(data_log_dir or "") == 0:
            logger.warning("Data log dir config empty")
            BlockedStatus("data-log-dir missing, please define it")
            return
        if len(data_dir or "") == 0:
            logger.warning("Data dir config empty")
            BlockedStatus("data-dir missing, please define it")
            return
        os.makedirs(data_log_dir, 0o750, exist_ok=True)
        shutil.chown(data_log_dir,
                     user=self.config["user"],
                     group=self.config["group"])
        os.makedirs(data_dir, 0o750, exist_ok=True)
        shutil.chown(data_dir,
                     user=self.config["user"],
                     group=self.config["group"])
        dev, fs = None, None
        if len(data_log_dev or "") == 0:
            logger.warning("Data log device not found, using rootfs instead")
        else:
            for k, v in data_log_dev.items():
                fs = k
                dev = v
            logger.info("Data log device: mkfs -t {}".format(fs))
            cmd = ["mkfs", "-t", fs, dev]
            subprocess.check_call(cmd)
            mount(dev, data_log_dir,
                  options=self.config.get("fs-options", None),
                  persist=True, filesystem=fs)

        if len(data_dev or "") == 0:
            logger.warning("Data device not found, using rootfs instead")
        else:
            for k, v in data_dev.items():
                fs = k
                dev = v
            logger.info("Data log device: mkfs -t {}".format(fs))
            cmd = ["mkfs", "-t", fs, dev]
            subprocess.check_call(cmd)
            mount(dev, data_dir,
                  options=self.config.get("fs-options", None),
                  persist=True, filesystem=fs)

    def render_service_override_file(self,
                                     target,
                                     jmx_file_name="kafka"):
        service_unit_overrides = yaml.safe_load(
            self.config.get('service-unit-overrides', ""))
        service_overrides = yaml.safe_load(
            self.config.get('service-overrides', ""))
        service_environment_overrides = yaml.safe_load(
            self.config.get('service-environment-overrides', ""))

        if "KAFKA_OPTS" not in service_environment_overrides:
            # Assume it will be needed, so adding it
            service_environment_overrides["KAFKA_OPTS"] = ""

        if self.is_ssl_enabled():
            if len(service_environment_overrides["KAFKA_OPTS"]) > 0:
                service_environment_overrides["KAFKA_OPTS"] += " "
            service_environment_overrides["KAFKA_OPTS"] = \
                service_environment_overrides["KAFKA_OPTS"] + \
                "-Djdk.tls.ephemeralDHKeySize=2048"
        if self.is_sasl_kerberos_enabled() or self.is_sasl_digest_enabled():
            if len(service_environment_overrides["KAFKA_OPTS"]) > 0:
                service_environment_overrides["KAFKA_OPTS"] += " "
            service_environment_overrides["KAFKA_OPTS"] = \
                service_environment_overrides["KAFKA_OPTS"] + \
                "-Djava.security.auth.login.config=" + \
                "/etc/kafka/jaas.conf"
        if self.is_jolokia_enabled():
            if len(service_environment_overrides["KAFKA_OPTS"]) > 0:
                service_environment_overrides["KAFKA_OPTS"] += " "
            service_environment_overrides["KAFKA_OPTS"] = \
                service_environment_overrides["KAFKA_OPTS"] + \
                "-javaagent:/opt/jolokia/jolokia.jar=" + \
                "config=/etc/kafka/jolokia.properties"
        if self.is_jmxexporter_enabled():
            if len(service_environment_overrides["KAFKA_OPTS"]) > 0:
                service_environment_overrides["KAFKA_OPTS"] += " "
            service_environment_overrides["KAFKA_OPTS"] = \
                service_environment_overrides["KAFKA_OPTS"] + \
                "-javaagent:/opt/prometheus/jmx_prometheus_javaagent.jar=" + \
                "{}:/opt/prometheus/{}.yml" \
                .format(self.config.get("jmx-exporter-port", 8079),
                        jmx_file_name)
        if len(service_environment_overrides.get("KAFKA_OPTS", "")) == 0:
            # Assumed KAFKA_OPTS would be set at some point
            # however, it was not, so removing it
            service_environment_overrides.pop("KAFKA_OPTS", None)

        if service_overrides:
            if self.config.get('user', "") in service_overrides and \
               self.config.get('group', "") in service_overrides:
                service_overrides["User"] = \
                    self.config.get('user')
                service_overrides["Group"] = \
                    self.config.get('group')
        render(source="kafka_override.conf.j2",
               target=target,
               owner=self.config.get('user'),
               group=self.config.get("group"),
               perms=0o644,
               context={
                   "service_unit_overrides": service_unit_overrides or {},
                   "service_overrides": service_overrides or {},
                   "service_environment_overrides": service_environment_overrides or {} # noqa
               })
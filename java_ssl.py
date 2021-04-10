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
import string
import subprocess

CHARS_PASSWORD = string.ascii_letters + string.digits
PASSWORD_LEN = 48


def _break_crt_chain(buffer):
    return [ i+"-----END CERTIFICATE-----\n" \
           for i in crts.split("-----END CERTIFICATE-----\n") \
           if i.startswith("-----BEGIN CERTIFICATE-----\n") ]


def saveCrtChainToFile(buffer,
                       cert_path,
                       ca_chain_path,
                       user="root",
                       group="root",
                       force=False):
    crts = _break_crt_chain(buffer)
    if _check_file_exists(cert_path) and not force:
        raise Exception("{} already exists, aborting".format(cert_path))
    if _check_file_exists(ca_chain_path) and not force:
       raise Exception("{} already exists, aborting".format(ca_chain_path))
    # cert_path can be set to None, and all the files will the
    # certificates will be saved to ca_chain_path
    if cert_path:
        with open(cert_path, "w") as f:
            f.write(crts[0])
            f.close()
        with open(ca_chain_path, "w") as f:
            f.write(crts[1:])
            f.close()
    else:
        with open(cert_path, "w") as f:
            f.write(crts[0:])
            f.close()
    setFilePermissions(path, user, group, mode=0o640)
    setFilePermissions(path, user, group, mode=0o640)


def _check_file_exists(path):
    try:
        os.stat(path)
    except FileNotFoundError:
        return False
    return True


def genRandomPassword():
    return "".join(CHARS_PASSWORD[c % len(CHARS_PASSWORD)]
                   for c in os.urandom(PASSWORD_LEN))


def RegisterIfKeystoreExists(path):
    return _check_file_exists(path)


def RegisterIfTruststoreExists(path):
    return _check_file_exists(path)


def setFilePermissions(path, user, group, mode=None):
    shutil.chown(path, user=user, group=group)
    if mode:
        os.chmod(path, mode)


def SetTrustAndKeystoreFilePermissions(user, group, 
                                       keystore_path,
                                       truststore_path):
    shutil.chown(keystore_path, user=user, group=group)
    os.chmod(keystore_path, 0o640)
    shutil.chown(truststore_path, user=user, group=group)
    os.chmod(truststore_path, 0o640)


def SetCertAndKeyFilePermissions(user, group,
                                 ca_cert_path,
                                 cert_path,
                                 key_path):
    shutil.chown(ca_cert_path, user=user, group=group)
    os.chmod(ca_cert_path, 0o640)
    shutil.chown(cert_path, user=user, group=group)
    os.chmod(cert_path, 0o640)
    shutil.chown(key_path, user=user, group=group)
    os.chmod(key_path, 0o640)


def PKCS12CreateKeystore(keystore_path, keystore_pwd, ssl_chain, ssl_key):
    try:
        with open("/tmp/kafka-broker-charm-cert.chain", "w") as f:
            f.write(ssl_chain)
            f.close()
        with open("/tmp/kafka-broker-charm.key", "w") as f:
            f.write(ssl_key)
            f.close()
        pk12_cmd = ['openssl', 'pkcs12', '-export', '-in',
                    "/tmp/kafka-broker-charm-cert.chain",
                    "-inkey", "/tmp/kafka-broker-charm.key",
                    "-out", "/tmp/kafka-broker-charm.p12",
                    "-name", "localhost", "-passout", "pass:mykeypassword"]
        subprocess.check_call(pk12_cmd)
        ks_cmd = ["keytool", "-importkeystore", "-srckeystore",
                  "/tmp/kafka-broker-charm.p12", "-srcstoretype",
                  "pkcs12", "-srcstorepass", "mykeypassword",
                  "-destkeystore", keystore_path, "-deststoretype", "pkcs12",
                  "-deststorepass", keystore_pwd, "-destkeypass", keystore_pwd]
        subprocess.check_call(ks_cmd)
    except Exception as e:
        # We've saved the key and cert to /tmp, we cannot leave it there
        # clean it up:
        os.remove("/tmp/kafka-broker-charm.key")
        os.remove("/tmp/kafka-broker-charm.p12")
        os.remove("/tmp/kafka-broker-charm-cert.chain")
        raise e

    # We've saved the key and cert to /tmp, we cannot leave it there
    # clean it up:
    os.remove("/tmp/kafka-broker-charm.key")
    os.remove("/tmp/kafka-broker-charm.p12")
    os.remove("/tmp/kafka-broker-charm-cert.chain")


def CreateTruststoreWithCertificates(truststore_path, truststore_pwd, ssl_ca):
    crtpath = "/tmp/juju_ca_cert"
    for c in ssl_ca:
        with open(crtpath, "w") as f:
            f.write(c)
            f.close()
        ts_cmd =["keytool", "-noprompt", "-keystore", truststore_path,
                 "-storetype", "pkcs12", "-alias", "jujuCAChain",
                 "-trustcacerts", "-import", "-file", crtpath, "-deststorepass",
                 truststore_pwd]
    os.remove(crtpath)


def CreateKeystoreAndTrustore(keystore_path,
                              truststore_path,
                              regenerate_stores,
                              keystore_pwd,
                              truststore_pwd,
                              ssl_cert_chain,
                              ssl_key,
                              user="root",
                              group="root",
                              mode=None):
    if RegisterIfKeystoreExists(keystore_path) and \
       RegisterIfTruststoreExists(truststore_path) and \
       not regenerate_stores:
        # return None as this option is not needed
        return None
    cert_chain = _break_crt_chain(ssl_cert_chain)
    PKCS12CreateKeystore(keystore_path, keystore_pwd, cert_chain[0], ssl_key)
    CreateTruststoreWithCertificates(truststore_path, truststore_pwd, cert_chain[1:])
    setFilePermissions(keystore_path, user, group, mode)
    setFilePermissions(truststore_path, user, group, mode)

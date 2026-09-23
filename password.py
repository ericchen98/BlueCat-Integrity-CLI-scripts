#!/usr/bin/python3
# coding:utf-8
# Copyright 2019 BlueCat Networks (USA) Inc. and its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# v5.2 20251226 change "is not" to "!="
# v5.1 20230827 rename process_password.py to password.py (rename fun name to password())
# v5.0 20210915-1500
# v2.0 : 2021/2/25 
#   found process_password.decrypt_password() will through exception "Incorrect padding"
#   if the encoded pw is not base64. Modify decrypt_password() to return "empty string" if it happens.
# v1.0 by Eric
#    copy from gw_nfv_plugin script, add print note for pyghon2 (need quote for input)
#


import base64


def encrypt_password(password):
    """
    Encrypt password with base64
    """
    
    
    
    password_bytes = str.encode(password.strip(), encoding='utf-8')
    return base64.b64encode(password_bytes).decode()

def decrypt_password(encoded):
    """
    Decrypt password with base64    
    """

    try:
        password_decypt_bytes = base64.b64decode(encoded)
        return password_decypt_bytes.decode('utf-8')
    except Exception as e:
        
        # Note by Eric --- don't print error message in this prog ---
        # ther error "e" will be "Incorrect padding" if the encoded string is wrong
        #   cannot be decoded by base64
        
        # logMsg = 'module "process_password" password decode error: ' + str(e)
        # print str(logMsg)
        
        # just return empty string - means pw decode error. calling prog will handle this
        return ''


def password():
    while True:
        # --- remove note, assume user use py3 now ---
        # print("Note: if you use Python2, please addd quote symoble (') for your input e.g. 'example' )")
        # print("   note: the quote symble will not be considered as part of the password")
        password = input("\nPlease input the password to be encrypted: ")
        if password.strip() != "":
            break
    pwd_encrypt = encrypt_password(password)
    print("{0} {1}".format("\nPassword is encrypted as:", pwd_encrypt))
    print("\nPlease update your encrypted api user password in bamconfig.json file\n")


if __name__ == '__main__':
    password()



# Integrity CLI script setup procedure

## 1. In BAM, create an API user and setup its password

In BAM, create a API user with correct access right.
	
## 2. create a file "bamconfig.json" 
   
   Copy or rename "bamconfig.json.example" to "bamconfig.json" and edit it.<br>
   All scripts will read this file and use the api user/password in this file to access BAM.

{ <br>
"sshuser"              : "bluecat",<br>
  "hostname"             : "bam.example.corp",<br>
  "user"                 : "api",<br>
  "password"             : "REPLACE_WITH_ENCRYPTED_PASSWORD",<br>
  "password_encrypt"     : "true",<br>
  "https"                : "false",<br>
  "bdds-name"            : "dds1",<br>
  "config-name"          : "config1",<br>
  "view-name"            : ["view1"],<br>
  "rpz-block-zone"       : "block.rpz.corp",<br>
  "rpz-redirect-zone"    : "redirect.rpz.corp",<br>
  "rpz-blackhole-zone"    : "blackhole.rpz.corp",<br>
  "rpz-whitelist-zone"    : "whitelist.rpz.corp",<br>
  "external-host-record" : "to.rpz.corp",<br>
  "add-flag" : [ "add", "new"],<br>
  "delete-flag" : [ "delete", "del"]<br>
}

**Most critical items are:**<br>
  **"user"**                 : this is the api user name you created in BAM<br>
  **"password"**            : put your encrypted password here<br>
  **"password_encrypt"**     : ["true" or "false"] - "true" means the "password" is encrypted.<br>
  **"https"**               : ["true" or "false"] - whether the scipt should use https to connect to BAM<br><br>
   Rest of the fileds are used for some special scripts (for example RPZ update scripts).<br>

# How to encrypt the password in "bamconfig.json"

  use password.py to generate your encrypted password. This is an example:

	$python password.py

	Please input the password to be encrypted: my_password
	Password is encrypted as: bXlfcGFzc3dvcmQ=
	
	Please update your encrypted api user password in bamconfig.json file

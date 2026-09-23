

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

# API version
   These script was orignially developed by BAM v1 API<br>
   All scripts has been converted to BAM v2 API in BAM.py.<br>


# BlueCat CLI Command Reference

All scripts share the same global flags for connecting to BAM: `-c config_name` (configuration), `-v view_name` (DNS view), `-z zone_name` (zone), plus `-d`/`--debug` on most scripts to print raw API request/response detail. Credentials and server host come from `bamconfig.json` (see `bamconfig.json.example`), not from a command-line flag.

`-k` ("same as zone") appears throughout the record scripts: it targets the zone's own apex record (e.g. `test.corp` itself) instead of a named child record, and when given, `-r`/record-name is ignored.

---

## Configuration / View / Zone management

### config_add.py
```
config_add.py -c config1
```
Add a configuration to BAM.

### config_query.py
```
config_query.py -a                 # list all configs
config_query.py -c config1         # query one config
```

### view_add.py
```
view_add.py -c config1 -v view1
```

### view_query.py
```
view_query.py -c config1 -a
view_query.py -c config1 -v view1
```
- `-a` lists all views under the config; `-v` queries one view.

### view_update.py
```
view_update.py -c config1 -v view1 --nv=viewNew1
```
- `--nv` new view name (rename).

### zone_add.py
```
zone_add.py -c config1 -v view1 -z zone1        # without deployable flag
zone_add.py -c config1 -v view1 -z zone1 -y     # with deployable flag set
```

### zone_query.py
```
zone_query.py -c config1 -v view1                # list all sub-zones
zone_query.py -c config1 -v view1 -z zone1       # query one zone
zone_query.py -c config1 -v view1 -z zone1 -a    # list sub-zones of that zone
```

### zone_query_all.py
```
zone_query_all.py -c config1 -v view1 -a   # list all zones
zone_query_all.py -c config1 -v view1 -y   # list only zones with deploy flag set
```

### zone_update.py
```
zone_update.py -c config1 -v view1 -z zone1 -y   # set deployable = True
zone_update.py -c config1 -v view1 -z zone1 -n   # set deployable = False
```

---

## DNS records - A records (`a_*.py`)

### a_add.py
```
a_add.py -c config1 -v view1 -z test.corp -r pc1 -i 10.10.10.3
a_add.py -c config1 -v view1 -z test.corp -i 10.10.10.3 -k

-k same as zome record (when -k is used, -r is ignored)
```
- `-r` record name, `-i` IP address.

### a_query.py
```
a_query.py -c config1 -v view1 -z test.corp -r pc1
a_query.py -c config1 -v view1 -z test.corp -k
```

### a_update.py
```
a_update.py -c config1 -v view1 -z test.corp -r pc1 -i 20.1.1.3 --ni 10.1.1.4
```
- `-i` old IP, `--ni` new IP.

### a_delete.py
```
a_delete.py -c config1 -v view1 -z test.corp -r pc1 -i 10.10.10.3
a_delete.py -c config1 -v view1 -z test.corp -i 10.10.10.3 -k
```

---

## DNS records - CNAME (`cname_*.py`)

### cname_add.py
```
cname_add.py -c config1 -v view1 -z test.corp -r www -i host.test.corp
```
- `-r` CNAME record name, `-i` linked (target) host record name. No `-k` — a zone apex can't be a CNAME.

### cname_query.py
```
cname_query.py -c config1 -v view1 -z test.corp -r www
```

### cname_update.py
```
cname_update.py -c config1 -v view1 -z test.corp -r c3 --ni h2.test.corp
```
- `--ni` new target host record. No old-value `-i` flag — found by name, target replaced directly.

### cname_delete.py
```
cname_delete.py -c config1 -v view1 -z test.corp -r www -i host.test.corp
cname_delete.py -c config1 -v view1 -z test.corp -i host.test.corp -k
```

---

## DNS records - Host records (`host_*.py`)

Host records support multiple IPs per name and an optional PTR (reverse) record.

### host_add.py
```
host_add.py -c config1 -v view1 -z test.corp -r host1 -i 10.1.1.3,10.1.1.4 -p   # with PTR
host_add.py -c config1 -v view1 -z test.corp -r host1 -i 10.1.1.3,10.1.1.4      # without PTR
host_add.py -c config1 -v view1 -z test.corp -i 10.1.1.3,10.1.1.4 -p -k         # same-as-zone
```
- `-i` comma-separated IP list (no spaces), `-p` also add PTR.

### host_add_one.py
```
host_add_one.py -c config1 -v view1 -z test.corp -r host1 -i 10.1.1.3
```
Appends one IP to an existing host record's IP list.

### host_query.py
```
host_query.py -c config1 -v view1 -z test.corp -r host1
host_query.py -c config1 -v view1 -z test.corp -k
```

### host_update.py
```
host_update.py -c config1 -v view1 -z test.corp -r host1 -i 10.10.10.3
host_update.py -c config1 -v view1 -z test.corp -r host1 -i 10.10.10.3,10.10.10.4 -p yes
```
- `-i` replaces the full IP list, `-p [yes|no]` add/remove PTR (omit to keep current setting).

### host_update_one.py
```
host_update_one.py -c config1 -v view1 -z test.corp -r host1 -i 10.10.10.3 --ni 10.10.10.4
host_update_one.py -c config1 -v view1 -z test1.corp -r h1 -i 10.1.1.2 --ni 10.1.1.2 -p yes   # PTR only
```
- `-i` existing IP to replace, `--ni` its new value.

### host_delete_one.py
```
host_delete_one.py -c config1 -v view1 -z test.corp -r host1 -i 10.10.10.3
```
Removes one IP from a host record's list.

### host_delete.py
```
host_delete.py -c config1 -v view1 -z test.corp -r host1
host_delete.py -c config1 -v view1 -z test.corp -k
```
Deletes the whole host record.

---

## DNS records - NS (`ns_*.py`)

### ns_add.py
```
ns_add.py -c config1 -v view1 -z test.corp -r ns1 -i a1.test.corp
```
- `-i` rdata (the nameserver target name).

### ns_query.py
```
ns_query.py -c config1 -v view1 -z test.corp -r pc1
```

### ns_update.py
```
ns_update.py -c config1 -v view1 -z test.corp -r ns1 -i pc1.test.corp --ni pc2.test.corp
```

### ns_delete.py
```
ns_delete.py -c config1 -v view1 -z test.corp -r pc1 -i rdata
```

---

## DNS records - SRV (`srv_*.py`)

### srv_add.py
```
srv_add.py -c config1 -v view1 -z test.corp -r srv1 -i host1.test.corp -o 10 -p 5060 -w 100
```
- `-i` linked record name, `-o` priority, `-p` port, `-w` weight.
- `-i` target must be an existing HostRecord or ExternalHostRecord.

### srv_query.py
```
srv_query.py -c config1 -v view1 -z test.corp -r srv1
```

### srv_update.py
```
srv_update.py -c config1 -v view1 -z test1.corp -r srv1 -i host1.test.corp -o 10 -p 5060 -w 100 --ni=host2.test.corp --no=20 --np=2020 --nw=200
```
- Every current value (`-i -o -p -w`) must be paired with its `--n*` counterpart (`--ni --no --np --nw`) even if only one field is changing — any `--n*` left out is written as blank.

### srv_delete.py
```
srv_delete.py -c config1 -v view1 -z test1.corp -r srv1 -i host1.test.corp -o 10 -p 5060 -w 100
```

---

## DNS records - NAPTR (`naptr_*.py`)

### naptr_add.py
```
naptr_add.py -c config1 -v view1 -z test.corp -r naptr1 -g S -o 100 -p 10 -e '!^.*$!sip:user@sip.rfc1035.com!' -t test1.MNC001.MCC700.gprs. -s x-3gpp-pgw:x-gp:x-gn
```
- `-g` flags, `-o` order, `-p` preference, `-e` regexp, `-t` replacement, `-s` service. Quote `-e` with single quotes in bash.

### naptr_query.py
```
naptr_query.py -c config1 -v view1 -z test.corp -r naptr1
```

### naptr_update.py
```
naptr_update.py -c config1 -v view1 -z test.corp -r naptr1 -g S -o 100 -p 10 -e '!^.*$!sip:user@sip.rfc1035.com!' -t test1.MNC001.MCC700.gprs. -s x-3gpp-pgw:x-gp:x-gn --ng S --no 999 --np 10 --ne '!^.*$!sip:user@sip.rfc1035.com!' --nt test1.MNC001.MCC700.gprs. --ns x-3gpp-pgw:x-gp:x-gn
```

### naptr_delete.py
```
naptr_delete.py -c config1 -v view1 -z test.corp -r naptr1 -g S -o 100 -p 0 -e '!^.*$!sip:eric@sip.rfc1035.com!' -t test1.MNC001.MCC700.gprs. -s x-3gpp-pgw:x-gp:x-gn
```
- Must match the record's **current** values exactly (i.e. post-update values, if it was updated since).

---

## DNS records - Generic (`generic_*.py`) — TXT, MX, HINFO, and other simple types

### generic_add.py
```
generic_add.py -c config1 -v view1 -z test.corp -r pc1 -i 10.10.10.3 -t A
generic_add.py -c config1 -v view1 -z test.corp -r pc1 -i a1.test.corp -t NS
generic_add.py -c config1 -v view1 -z test.corp -i 10.10.10.3 -k -t A
```
- `-t` rrtype (A, AAAA, NS, TXT, MX, HINFO, ...), `-i` rdata.

### generic_query.py
```
generic_query.py -c config1 -v view1 -z test.corp -r pc1              # all types named pc1
generic_query.py -c config1 -v view1 -z test.corp -r pc1 -t NS         # only NS
```

### generic_update.py
```
generic_update.py -c config1 -v view1 -z test.corp -t A -r a1 -i 10.10.10.3 --ni=20.20.20.3
```

### generic_delete.py
```
generic_delete.py -c config1 -v view1 -z test.corp -t a -r pc1 -i 10.10.10.3
```

---

## Zone-wide record listing / export

### zone_rr_query.py
```
zone_rr_query.py -c config1 -v view1 -z test.corp -a                       # all records
zone_rr_query.py -c config1 -v view1 -z test.corp -t naptr -n naptr1       # by name
zone_rr_query.py -c config1 -v view1 -z test.corp -t ns -r pc1.test.corp   # by rdata (NS/NAPTR only)
```
- `-t [host|cname|mx|txt|srv|naptr|generic|hinfo]`, `-a` dumps every type.

### dump_rr.py
```
dump_rr.py -c config1 -v view1 -a                              # all record types in one view
dump_rr.py -c config1 -v view1 -t ns -r a1.corp -o out.csv -u   # filter + save to CSV
dump_rr.py -c config1 -t ns -r a1.corp                          # ALL views under the config (no -v)
dump_rr.py -c config1 -y                                        # just list zones
```
- `-t [host|cname|mx|txt|srv|hinfo|A|AAAA|naptr]`, `-n` name filter, `-r` rdata filter, `-u [d|u]` set XML on-exist flag, `-o file.csv` save output, `-m` human-readable instead of CSV, `-y` zones only.

---

## DNS deployment roles (which server serves which zone/view)

### dnsRole_add.py
```
dnsRole_add.py -c config1 -v view1 -r master -s dds1                       # role on the view
dnsRole_add.py -c config1 -v view1 -z test.corp -r master -s dds1          # role on a zone
dnsRole_add.py -c config1 -v view1 -z test.corp -r master -s dds1 -p dds1.test.com   # via published interface
```
- `-r [primary|secondary|primary_hidden|recursion|forwarder|stub|secondary_stealth|none]` (older `master`/`slave` spellings also accepted), `-s` server name, `-p` published-interface hostname.

### dnsRole_query.py
```
dnsRole_query.py -c config1 -v view1 -z test.corp -s dds1   # one server's role
dnsRole_query.py -c config1 -v view1 -z test.corp -a        # every role on this view/zone
```

### dnsRole_update.py
```
dnsRole_update.py -c config1 -v view1 -z test.corp -s dds1 --nr secondary
dnsRole_update.py -c config1 -v view1 -z red.corp -s dds1 -p pub1.xyz.corp --nr master
```
- `--nr` new role, `-p` existing published interface (needed to locate the role if the server has one), `--np` also move the role to a new published interface — if given and unresolvable, the whole update aborts before anything changes.

### dnsRole_delete.py
```
dnsRole_delete.py -c config1 -v view1 -r master -s dds1
dnsRole_delete.py -c config1 -v view1 -z test.corp -r master -s dds1
```

### server_role.py *(legacy — superseded by `dnsRole_add.py`/`dnsRole_delete.py`)*
```
server_role.py -c config1 -v view1 -z test.corp -a -r master -s dds1   # add
server_role.py -c config1 -v view1 -z test.corp -x -s dds1             # delete
```

---

## DNS deployment options (forwarding, forwarding policy, ACLs)

All of these scale to config, view, server, or server-group scope via `-s`/`-g`/`-y` (see each script's own flags).

### dns_forwarding_add.py
```
dns_forwarding_add.py -c config1 -v view1 -i 8.8.8.8,1.1.1.1 -z yes
dns_forwarding_add.py -c config1 -s dds1 -y -i 8.8.8.8 -z yes   # directly on a server
```
- `-i` forwarder IP list, `-z [yes|no]` disable forwarding for child zone, `-s`/`-g` server/serverGroup, `-y` apply directly to that server/group instead of the config/view.

### dns_forwarding_query.py
```
dns_forwarding_query.py -c config1 -v view1
```

### dns_forwarding_delete.py
```
dns_forwarding_delete.py -c config1 -v view1 -s dds1
```

### dns_forwardingPolicy_add.py
```
dns_forwardingPolicy_add.py -c config1 -o             # "only"
dns_forwardingPolicy_add.py -c config1 -v view1 -f     # "first"
dns_forwardingPolicy_add.py -c config1 -g sg1 -y -o    # directly on a server group
```
- `-o` policy = only, `-f` policy = first, `-s`/`-g`/`-y` same scoping as above.

### dns_forwardingPolicy_delete.py
```
dns_forwardingPolicy_delete.py -c config1 -v view1 -s dds1
```
(No dedicated query script for forwarding policy.)

### matchClient_add.py
```
matchClient_add.py -c config1 -v view1 -m 10.1.1.0/24,10.1.2.0/24
```
- `-m` comma-separated CIDR/IP list (the view's `match-clients` ACL).

### matchClient_query.py
```
matchClient_query.py -c config1 -v view1
```

### matchClient_update.py
```
matchClient_update.py -c config1 -v view1 -m 10.1.1.0/24,20.0.0.0/8
```
Replaces the whole ACL with the new value.

### matchClient_delete.py
```
matchClient_delete.py -c config1 -v view1
```
Deletes the whole match-clients option (all ACL entries at once).

---

## Deployment (push config to a server)

### deploy_server.py
```
deploy_server.py -c config1 -s dds1 -t DNS
deploy_server.py -c config1 -s dds1 -t DNS -f 30 -w 1
```
- `-t [DNS|DHCP|DHCPv4|DHCPv6|TFTP]` (omit for a full deploy), `-f` status-check frequency (default 20), `-w` wait seconds between checks (default 1).

### deploy_status.py
```
deploy_status.py -c config1 -s dds1
```
- Returns one of: EXECUTING, INITIALIZING, QUEUED, CANCELLED, FAILED, NOT_DEPLOYED, WARNING, INVALID, DONE, NO_RECENT_DEPLOYMENT.

---

## IPv4 address space (networks, addresses, DHCP ranges)

### ip4network_query.py
```
ip4network_query.py -c config1 -i 10.1.1.0/24
```

### ip4network_update.py
```
ip4network_update.py -c config1 -i 10.1.1.0/24 -n new_name
ip4network_update.py -c config1 -i 10.1.1.0/24 -u UDF1 -v UDF_value
```
- `-n` new network name (mutually exclusive with `-u`/`-v` UDF update), `-o` overwrite if UDF isn't empty, `--dry` dry-run.

### ip4addr_add.py
```
ip4addr_add.py -c config1 -i 10.1.1.10 -m 112233445566 -n "Joe Chen" -p
```
- `-m` MAC address, `-n` name, `-k [y|n]` ping check, one of `-s`/`-p`/`-r` (static / DHCP-reserved / reserved).

### ip4addr_query.py
```
ip4addr_query.py -c config1 -i 10.1.1.10
```

### ip4addr_update.py
```
ip4addr_update.py -c config1 -i 10.1.1.10 -m 112233445566 -n "Joe Chen" -p
```

### ip4addr_udf_update.py
```
ip4addr_udf_update.py -c config1 -i 10.1.1.10 -u UDF_name -a 'New_UDF_value'
ip4addr_udf_update.py -c config1 -i 10.1.1.10 -u UDF_name -x   # delete existing UDF data
```

### ip4addr_delete.py
```
ip4addr_delete.py -c config1 -i 10.1.1.10
```

### dhcp4range_add.py
```
dhcp4range_add.py -c config1 -i 10.1.1.0/24 -s 10.1.1.11 -e 10.1.1.20 -n range1
```

### dhcp4range_query.py
```
dhcp4range_query.py -c config1 -i 10.1.1.0/24 -s 10.1.1.11 -e 10.1.1.20
```

### dhcp4range_update.py
```
dhcp4range_update.py -c config1 -i 10.1.1.0/24 -s 10.1.1.11 -e 10.1.1.20 --ns 10.1.1.15 --ne 10.1.1.25
dhcp4range_update.py -c config1 -i 10.1.1.0/24 -s 10.1.1.15 -e 10.1.1.25 -n new_name
```
- Provide `-n`, or both `--ns`/`--ne`, or both at once.

### dhcp4range_delete.py
```
dhcp4range_delete.py -c config1 -i 10.1.1.0/24 -s 10.1.1.11 -e 10.1.1.20
```

---

## MAC pools and MAC addresses

### macPool_add.py
```
macPool_add.py -c config1 -p macPool1 -i
```
- `-i` enable instant deployment for changes to this pool.

### macPool_query.py
```
macPool_query.py -c config1 -p macPool1
```

### macPool_delete.py
```
macPool_delete.py -c config1 -p macPool1
```

### macPoolItem_add.py
```
macPoolItem_add.py -c config1 -p macPool1 -m 1122334455
```
- `-p macPool` (use `deny` to target the Deny MAC Pool instead). **Note (confirmed live):** the MAC address must already exist as a known entity in the configuration before it can be associated — this script does not register a brand-new MAC on the fly.

### macPoolItem_delete.py
```
macPoolItem_delete.py -c config1 -p macPool1 -m 1122334455
```

### mac_query.py
```
mac_query.py -c config1 -m 112233445566
```

---

## Response Policy Zones (RPZ)

### rpz_add.py
```
rpz_add.py -c config1 -r ResponsePolicy-1 -i a1.test.corp
```
Adds one RPZ policy item to a built-in BAM RPZ Response Policy.

### rpz_delete.py
```
rpz_delete.py -c config1 -r ResponsePolicy-1 -i a1.test.corp
```

### rpz_upload.py
```
rpz_upload.py -c config1 -r ResponsePolicy-1 -f rpz-list.txt
```
Uploads a whole text file of RPZ items, **replacing all existing items** in that policy.

### rpz_update.py
```
rpz_update.py -i input.csv -z block -o add -t domain
```
- Different tool from the other three: reads a CSV and bulk add/deletes items in a **customized** RPZ zone (not the built-in BAM RPZ). `-z [block|blackhole|redirect|whitelist]`, `-o [add|delete]`, `-t [domain|ip]`, `-n` dry-run, `-e` encode a password.

---

## Server info and access control

### server_query.py
```
server_query.py -c config1 -a          # all servers
server_query.py -c config1 -s dds1     # one server
```

### access_rights.py
```
access_rights.py -a FULL -c config1 -v view1 -u user1
access_rights.py -a FULL -c config1 -v view1 -z test.corp -g userGroup1
access_rights.py -r -c config1 -v view1 -z test.corp -u user1              # remove
access_rights.py -a FULL -c config1 --b4 10.0.0.0/8 -u user1               # on an IP4 block
access_rights.py -a FULL -c config1 --n4 10.1.1.0/24 -u user1              # on an IP4 network
```
- `-a [HIDE|VIEW|ADD|CHANGE|FULL]` add/update ACL, `-r` remove ACL, `--b4`/`--b6` IP block, `--n4`/`--n6` IP network, `-u` user, `-g` user group.

---

## Not a BAM command

### run_all_tests.py
The self-cleaning test harness for this whole toolkit — runs the full add/query/update/delete lifecycle against a live BAM server. See its own header docstring for usage (`--list`, `--yes`, `--dry-run`, `--only`, `--keep`, `--timeout`).

### BAM.py / cli.py / log.py / password.py
Shared library modules imported by every script above (the v2 API shim, shared CLI helpers, logging, and password encode/decode). Not invoked directly.


   

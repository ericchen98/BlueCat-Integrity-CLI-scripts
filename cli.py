#!/usr/bin/python
# coding:utf-8
#
# Copyright 2021 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
# https://opensource.org/licenses/Python-2.0
#
# Bluecat only provides this Script for reference as a Proof of Concept
#
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
#
#
# v1.0 20230826 
# --- not included in this cli.py ---
#   generate_add.py
#   generate_delete.py
#   print_file.py
#	dns_resolver.py
# ----------------------------------------------------------

import getopt
import sys
import json
import os

# for linux up/down key function

if os.name == 'nt':
    #  same dir in Windows
    pass
else:
    # Linux platform
    import readline

import BAM

from	access_rights            import *

from	a_add                    import *
from	a_delete                 import *
from	a_query                  import *
from	a_update	             import *
from	cname_add                import *
from	cname_delete             import *
from	config_add               import *
from	config_query             import *
from	deploy_server             import *
from	deploy_status             import *
from	dnsRole_add              import *
from	dnsRole_delete           import *
from	dns_forwarding_add       import *
from	dns_forwarding_delete	 import *
from	dns_forwarding_query     import *
from	dump_rr                  import *
from	generic_add              import *
from	generic_delete           import *
from	generic_query            import *
from	generic_update           import *
from	host_add                 import *
from    host_add_one             import *
from	host_delete              import *
from    host_delete_one          import *
from	host_query               import *
from	host_update	             import *
from	host_update_one          import *
from	log                      import *
from	matchClient_add          import *
from	matchClient_delete       import *
from	matchClient_query        import *
from	matchClient_update       import *
from	naptr_add                import *
from	naptr_delete             import *
from	naptr_query              import *
from	naptr_update             import *
from	ns_add                   import *
from	ns_delete                import *
from	ns_query                 import *
from	ns_update                import *
from	server_role              import *
from    server_query             import *
from	srv_add                  import *
from	srv_delete               import *
from	srv_query                import *
from	srv_update               import *
from	view_add                 import *
from	view_query               import *
from	view_update              import *
from	zone_add                 import *
from	zone_query               import *
from	zone_query_all           import *
from	zone_rr_query            import *
from	zone_update              import *
from	rpz_update               import *
from	rpz_add                  import *
from	rpz_delete               import *
from	rpz_upload               import *

from	macPool_add              import *
from	macPool_delete           import *
from	macPool_query            import *
from	macPoolItem_add          import *
from	macPoolItem_delete       import *
from    mac_query                import *

from	password                 import *

# ---------------------------------------------------------------------
develop_mode = False

# ---------------------------------------------------------------------
# New module to replace BAM (zeep, SOAP)
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
#if develop_mode:
#    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "1.1"

help_text = '''
[---User management---]
   access-rights    : add/remove user access right 
[---Server management---]   
   deploy-server 
   server-query             server-role
[---Configuration/View/Zone management ---]
         config-add         config-query   
           view-add           view-query          view-update
           zone-add           zone-query          zone-update     zone-query-all
    matchClient-add   matchClient-delete    matchClient-query  matchClient-update
        dnsRole-add       dnsRole-delete      
[---DNS record management---] 
        a-add           a-update         a-query         a-delete
       ns-add          ns-update        ns-query        ns-delete
      srv-add         srv-update       srv-query       srv-delete
     host-add        host-update      host-query      host-delete
 host-add-one    host-update-one                  host-delete-one  
    cname-add       cname-delete
    naptr-add       naptr-update     naptr-query     naptr-delete
  generic-add     generic-update   generic-query   generic-delete
[---DNS record dump---]
   zone-rr-query: dump or query DNS records from view/zone
[---DNS forward configuration[---] 
   dns-forwarding-add   dns-forwarding-query   dns-forwarding-delete
[---RPZ configuration--] 
    rpz-add   rpz-delete  rpz-upload  rpz-update
[---MAC address/Pool ---]
    macPool-add         macPool-delete     macPool-query
    macPoolItem-add     macPoolItem_delete
    mac-query
[---configuration file bamconfig.json example--] 
    bamconfig-show
    
TIp: command is case insensitive.

Enter "exit" to exit cli shell
Enter "help", "h" or "?" to print this help 
Enter individual command to get help:

      password (encrypt api password), version
      config, view, zone, a, host, cname, ns, srv, naptr, generic
      matchClient, server, deploy, dns, rpz, access-rights, mac, bamconfig-show
'''

bamconfig_json='''
{ "sshuser"              : "bluecat", 
  "hostname"             : "10.1.1.113", 
  "user"                 : "api", 
  "password"             : "YXBp", 
  "password_encrypt"     : "true", 
  "https"                : "false",
  "bdds-name"            : "dds1",
  "config-name"          : "config1",
  "view-name"            : ["view1","view2","view3"],
  "rpz-block-zone"       : "block.rpz.corp",
  "rpz-redirect-zone"    : "redirect.rpz.corp",
  "rpz-blackhole-zone"    : "blackhole.rpz.corp",
  "rpz-whitelist-zone"    : "whitelist.rpz.corp",
  "external-host-record" : "to.rpz.corp",
  "add-flag" : [ "add", "new"],
  "delete-flag" : [ "delete", "del"]
}
'''

help_config = '''
config-add      : add a configuration
config-query    : query a configuration
'''

help_view = '''
view-add    : add a view to a configuration 
view-query  : query a view to a configuration.
view-update : update name of a view 
'''
help_zone = '''
zone-add        : add a zone in a view
zone-query      : query a zone
zone-update     : set or clear the "deployable flag" of a zone 
zone-query-all  : list all zones under a view
zone-rr-query   : dump or query DNS records from view/zone
'''

help_cname = '''
cname-add       : add a CNAME record to a zone
cname-delete    : delete a CNAME record from a zone
'''

help_ns = '''
ns-add       : add    a NS record to a zone 
ns-delete    : delete a NS record from a zone
ns-query     : query  a NS record from a zone
ns-update    : update a NS record in a zone
'''

help_srv = '''
srv-add       : add    a SRV record to a zone 
srv-delete    : delete a SRV record from a zone
srv-query     : query  a SRV record from a zone
srv-update    : update a SRV record in a zone
'''

help_naptr = '''
naptr-add       : add    a NAPTR record to a zone 
naptr-delete    : delete a NAPTR record from a zone
naptr-query     : query  a NAPTR record from a zone
naptr-update    : update a NAPTR record in a zone
'''

help_generic = '''
generic-add    : add    a generic record to a zone 
generic-delete : delete a generic record from a zone
generic-query  : query  a generic record from a zone
generic-update : update a generic record in a zone
'''
  
help_a = '''
a-add     : add an A record to a zone 
a-delete  : delete an A record from a zone
a-query   : query an A record from a zone
a-update  : update an A record in a zone
'''

help_host = '''
host-add    : add a host record to a zone (with one or multiple IP)
host-delete : delete a host record from a zone
host-query  : query a host record from a zone
host-update : update a host record in a zone (update ALL IP by at once)

host-add-one    : add an IP to a host record
host-update-one : Update an IP of a host record
host-delete-one : delete an IP from a host record
'''

help_dns = '''
dnsRole-add           : add DNS deploy role to a view or a zone
dnsRole-delete        : delete DNS deploy role from a view or a zone
dns-forwarding-add    : add DNS forwarding role to a view 
dns-forwarding-query  : query DNS forwarding role of a view 
dns-forwarding-delete : delete DNS forwarding role from a view 
'''

help_matchClient = '''
matchClient-add    : add    a matchClient to a view
matchClient-delete : delete a matchClient to a view
matchClient-query  : query  a matchClient to a view
matchClient-update : Update a matchClient to a view
'''

help_server = '''
server-query  : query one or all BDDS servers setting of a config
server-role   : add/delete server deploy roles(master,slave) to a view/zone
deploy-server : deploy a BDDS server
deploy-status : get the deploy status of a BDDS server
'''

help_deploy = '''
deploy-server : deploy a BDDS server
deploy-status : get the deploy status of a BDDS server
'''
help_mac = '''
mac-query          : MAC address query

macPool-add        : add    a MACPool 
macPool-delete     : delete a MACPool
macPool-query      : query  a MACPool
macPoolItem-add    : add    a MAC address to a MACPool
macPoolItem_delete : delete a MAC address from a MACPool
'''

help_rpz = '''
rpz-add     : add a RPZ policy item to a BAM RPZ ReponsePolicy
rpz-delete  : delete a RPZ policy item from a BAM RPZ ReponsePolicy
rpz-upload  : Upload RPZ Policy items in a text file to RPZ ReponsePolicy
              Note: will replace all existing RPZ policy items
rpz-update  : Read rpz items from a csv file and add them to a user customized RPZ zone
              Note: "user customized RPZ zone" is NOT the built-in BAM RPZ function
'''

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
if not develop_mode:
    sys.tracebacklimit = 0


def do_help():
    print(help_text)

def cli(*args): 

    shell_mode = True
    doLoop = True
    
    arg_list = list( args )
    
    if len(arg_list) > 1:  # only has exe name
        shell_mode = False
    
    
    input_cmd = ''

    print("cli> ", end='')
    
    #------------------------------------------------------
    # main while loop
    #------------------------------------------------------

    cmd_found = False
    while doLoop:
        input_cmd = ''
        cmd_found = False
        
        if shell_mode:    # exe file name only, accept user input()
            line = input()        #re-accpet user input 
            arg_list1 = line.split( ' ')
            arg_list = list(filter(None, arg_list1))
            
            if len(arg_list) >= 1:
                input_cmd = arg_list[0].lower()     #get the input cmd
            
            # in cli.py interactive shell, if user enter more than one space, 
            #     getop() will get wrong result.
            # user input data will go to args(wrong) instead of opts(right).
            # need to use "with filter: arg_list = list(filter(None, arg_list1))" 
            #    to delete all empty element in a list
            
            
        else: # passed from exe
        
            arg_list.pop(0) #remove exe file name
            input_cmd = arg_list[0].lower()     #get the input cmd
            doLoop = False  #stop loop (one cmd only)
        
        #remove first element (function name) from arg_list 
        if len(arg_list) != 0:
            arg_list.pop(0)

        #----------------------------------------     
        # help  
        #----------------------------------------       
        if (input_cmd.lower() == 'help') or (input_cmd == '?') or (input_cmd.lower() == 'dir') \
            or input_cmd.lower() == 'h':
            do_help()
            cmd_found = True

        #----------------------------------------       
        # help_view
        #----------------------------------------       
        if input_cmd == 'version'.lower():
            print( 'version: %s' % version )
            cmd_found = True
        #----------------------------------------       
        # help_config
        #----------------------------------------       
        if input_cmd == 'config'.lower():
            print( help_config )
            cmd_found = True

        #----------------------------------------       
        # help_view
        #----------------------------------------       
        if input_cmd == 'view'.lower():
            print( help_view )
            cmd_found = True
        #----------------------------------------       
        # help_zone
        #----------------------------------------       
        if input_cmd == 'zone'.lower():
            print( help_zone )
            cmd_found = True
        #----------------------------------------       
        # help_cname
        #----------------------------------------       
        if input_cmd == 'cname'.lower():
            print( help_cname )
            cmd_found = True

        #----------------------------------------       
        # help_ns
        #----------------------------------------       
        if input_cmd == 'ns'.lower():
            print( help_ns )
            cmd_found = True
        #----------------------------------------       
        # help_srv
        #----------------------------------------       
        if input_cmd == 'srv'.lower():
            print( help_srv )
            cmd_found = True
        #----------------------------------------       
        # help_naptr
        #----------------------------------------       
        if input_cmd == 'naptr'.lower():
            print( help_naptr )
            cmd_found = True
        #----------------------------------------       
        # help_generic
        #----------------------------------------       
        if input_cmd == 'generic'.lower():
            print( help_generic )
            cmd_found = True
        #----------------------------------------       
        # help_a
        #----------------------------------------       
        if input_cmd == 'a'.lower():
            print( help_a )
            cmd_found = True

        #----------------------------------------       
        # help_host
        #----------------------------------------       
        if input_cmd == 'host'.lower():
            print( help_host )
            cmd_found = True

        #----------------------------------------       
        # help_dns
        #----------------------------------------       
        if input_cmd == 'dns'.lower():
            print( help_dns )
            cmd_found = True

        #----------------------------------------       
        # help_matchClient
        #----------------------------------------       
        if input_cmd == 'matchClient'.lower():
            print( help_matchClient )
            cmd_found = True

        #----------------------------------------       
        # help_server
        #----------------------------------------       
        if input_cmd == 'server'.lower():
            print( help_server )
            cmd_found = True
        #----------------------------------------       
        # help_deploy
        #----------------------------------------       
        if input_cmd == 'deploy'.lower():
            print( help_deploy )
            cmd_found = True
        #----------------------------------------       
        # help_mac
        #----------------------------------------       
        if input_cmd == 'mac'.lower():
            print( help_mac )
            cmd_found = True
            
        #----------------------------------------       
        # help_rpz
        #----------------------------------------       
        if input_cmd == 'rpz'.lower():
            print( help_rpz )
            cmd_found = True
            
        #=========================================       
        # main function
        #=========================================       
        if input_cmd == 'exit'.lower():
            doLoop = False
            cmd_found = True
            
        #----------------------------------------       
        if input_cmd == 'bamconfig-show'.lower():
            print('CLI configuration file "bamconfig.json" format example:')
            print(bamconfig_json)
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'access-rights'.lower():
            rtn = access_rights( *arg_list )
            
        #----------------------------------------       
        if input_cmd == 'a-add'.lower():
            rtn = a_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'a-delete'.lower():
            rtn = a_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'a-query'.lower():
            rtn = a_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'a-update'.lower():
            rtn = a_update( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'cname-add'.lower():
            rtn = cname_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'cname-delete'.lower():
            rtn = cname_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'config-add'.lower():
            rtn = config_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'config-query'.lower():
            rtn = config_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'deploy-server'.lower():
            rtn = deploy_server( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'deploy-status'.lower():
            rtn = deploy_status( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'dnsRole-add'.lower():
            rtn = dnsRole_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'dnsrole-delete'.lower():
            rtn = dnsRole_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'dns-forwarding-add'.lower():
            rtn = dns_forwarding_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'dns-forwarding-delete'.lower():
            rtn = dns_forwarding_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'dns-forwarding-query'.lower():
            rtn = dns_forwarding_query( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'dump-rr'.lower():
            rtn = dump_rr( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'generic-add'.lower():
            rtn = generic_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'generic-delete'.lower():
            rtn = generic_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'generic-query'.lower():
            rtn = generic_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'generic-update'.lower():
            rtn = generic_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'host-add'.lower():
            rtn = host_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-add-one'.lower():
            rtn = host_add_one( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-delete'.lower():
            rtn = host_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-delete-one'.lower():
            rtn = host_delete_one( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-query'.lower():
            rtn = host_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-update'.lower():
            rtn = host_update( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'host-update-one'.lower():
            rtn = host_update_one( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'matchclient-add'.lower():
            rtn = matchClient_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'matchclient-delete'.lower():
            rtn = matchClient_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'matchclient-query'.lower():
            rtn = matchClient_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'matchclient-update'.lower():
            rtn = matchClient_update( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'naptr-add'.lower():
            rtn = naptr_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'naptr-delete'.lower():
            rtn = naptr_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'naptr-query'.lower():
            rtn = naptr_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'naptr-update'.lower():
            rtn = naptr_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'ns-add'.lower():
            rtn = ns_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'ns-delete'.lower():
            rtn = ns_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'ns-query'.lower():
            rtn = ns_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'ns-update'.lower():
            rtn = ns_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'password-encrypt'.lower():
            rtn = process_password( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'password'.lower():
            rtn = password( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'server-query'.lower():
            rtn = server_query( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'server-role'.lower():
            rtn = server_role( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'srv-add'.lower():
            rtn = srv_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'srv-delete'.lower():
            rtn = srv_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'srv-query'.lower():
            rtn = srv_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'srv-update'.lower():
            rtn = srv_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'view-add'.lower():
            rtn = view_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'view-query'.lower():
            rtn = view_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'view-update'.lower():
            rtn = view_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'zone-add'.lower():
            rtn = zone_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'zone-query'.lower():
            rtn = zone_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'zone-query-all'.lower():
            rtn = zone_query_all( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'zone-rr-query'.lower():
            rtn = zone_rr_query( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'zone-update'.lower():
            rtn = zone_update( *arg_list )
            cmd_found = True

        #----------------------------------------       
        if input_cmd == 'rpz-update'.lower():
            rtn = rpz_update( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'rpz-add'.lower():
            rtn = rpz_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'rpz-delete'.lower():
            rtn = rpz_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'rpz-upload'.lower():
            rtn = rpz_upload( *arg_list )
            cmd_found = True
            
        #----------------------------------------       
        if input_cmd == 'macpool-add'.lower():
            rtn = macPool_add( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'macpool-delete'.lower():
            rtn = macPool_delete( *arg_list )
            cmd_found = True
        #----------------------------------------       
        if input_cmd == 'macpool-query'.lower():
            rtn = macPool_query( *arg_list )
            cmd_found = True

        #---------------------------------------- nput_cmd will be all lower case 
        if input_cmd == 'macpooLItem-add'.lower():
            rtn = macPoolItem_add( *arg_list )
            cmd_found = True
        #---------------------------------------- nput_cmd will be all lower case       
        if input_cmd == 'macpooLItem-delete'.lower():
            rtn = macPoolItem_delete( *arg_list )
            cmd_found = True

        #---------------------------------------- nput_cmd will be all lower case 
        if input_cmd == 'mac-query'.lower():
            rtn = mac_query( *arg_list )
            cmd_found = True

        #----------------------------------------       
        # print prompt before loop    
        #----------------------------------------       
        #print("\nEnter cli commands. enter help for available commands")
        
        if input_cmd == '':
            cmd_found = True

        if cmd_found != True:
            print( ' Command not found')
            
        if doLoop:
            print("cli> ", end='')


# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    
    #print (sys.argv)
    cli(*sys.argv)
    













#!/usr/bin/python3
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

# https://opensource.org/licenses/Python-2.0#
#
# v5.9-20251228 fixed help message 
# v5.8-20240923 fixed if a server does not have fullHostName, program will show key error
#      if 'fullHostName' in properties: <---------------------- new added
# v5.7-20230828 fixed log does not show in cli.py issue 
# v5.6-20230827 rename query_server to server_query()
# v5.5-20221226 change log dir to "./"
# v5.4-20220221 update BAM.bam_logout(bam) before all return()
# v5.3 20211206  update help error
# v5.1 20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# ver: 3.0 2021/8/1 use new BAM.get_confid(), BAM.get_viewid(), BAM.get_zoneid()
#
# ---------------------------------------------------------------
# output example
# python3 query-server.py  -c config1 -a
# 
# BDDS Name: dds1
#   profile: DNS_DHCP_GEN4_2000
#   Service IPv4 InterfCace: 10.1.1.106
#   defaultInterfaceAddress: 10.1.1.106
# 
# BDDS Name: dds2
#   profile: DNS_DHCP_GEN4_2000
#   Service IPv4 InterfCace: 10.1.1.107
#   Service IPv6 InterfCace: 2001:DB9::107
#   defaultInterfaceAddress: 10.1.1.107
# 
#     published Interface Address: 192.168.2.4
#     published Interface IPv6Address: 2001:DB8::4
#     published interface host name: dds12.xyz.corp
# 
#     published Interface Address: 117.56.25.1
#     published Interface IPv6Address: 2001:4420:6707:FE::1
#     published interface host name: dds12.xyz1.corp
# 
# BDDS Name: oth-dds136
#   profile: OTHER_DNS_SERVER
#   defaultInterfaceAddress: 10.1.1.136
# 
# INFO:Success: server found
# ---------------------------------------------------------------

"""
server_query -c config1 -a
server_query -c config1 -s dds1
    -c config_name 
    -a get all server information in config_name
    -s BDDS_server_name
       
    Note: server name is case sensitive!   
"""
import getopt
import sys
import json
import os

import BAM

# ---------------------------------------------------------------------
# New module to replace BAM
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "5.9"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def server_query(*args):    

    # ---------------------------------------------------------------------
    # local #def
    # ---------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_view

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var setup
    # ---------------------------------------------------------------------

    logMsg = ''
    logMsg2 = ''        # for query script to build multiple result
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''
   
    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False

    configuration = None
    server = ""
    
    # not used
    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    show_version = False

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    
    record_changed = False

    get_all = False
    bdds = ""

    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False

    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
    else:
        # Linux platform
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"

    # BAM.get_input_cmd() is a function. 
    #----------------------------------------------------------------
    #fixed log input issue when called by cli.py or python3 xxx.py
    #----------------------------------------------------------------
    #get program name. If prog is called by cli.py, then __name__ will be "a_query"
    prog_name = __name__
    
    #convert "_" to "-" in prog_name
    prog_name = prog_name.replace('_','-')
    
    if __name__ == '__main__': #this program is run by python directly (e.g. python3 a_query.py)
         #will get user full input commands and remove ".py"
        input_cmd_log = BAM.get_input_cmd()
    else: #this program is called by cli.py (use args as log output file)
        input_cmd_log_from_args = ' '.join(args)
        input_cmd_log = " Input: %s %s" % (prog_name,input_cmd_log_from_args)
    
    # will create a logger, store input_cmd_log and setup logpath logFileName to logger
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)

    # --- load config by BAM.load_config()  return json format "config"
    configFile = workingDir + "bamconfig.json"
    config = BAM.load_config(print_log, configFile)

    if config['https'].upper() == 'TRUE':
        https = True
    else:
        https = False

    # --- get api & apiPw ---
    api = config['user']
    apiPw = config['password'] 
    
    # decode api verify encrypted password to see if it is valid.
    apiPw_decode = BAM.decrypt_password(apiPw) 
        
    if apiPw_decode == '':
        logMsg = "API user password decode error"
        print_log.go(log_error, logMsg)
        return (1)  
    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:s:ah", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:s:ah", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True   
        elif o == "-c": configuration = v 
        elif o == "-s": bdds = v 
        elif o == "-a": get_all = True
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h": 
            print (__doc__)
            return(1)

    if not opts:
        print (__doc__)
        return (0)

    if show_version == True:
        print("Version %s" % version)
        return(0)

    # ---------------------------------------------------------
    # debug setup
    # ---------------------------------------------------------
    if debug:
        debug_user = True    # value 1
        debug_api = False 
        debug_bam = False 
    if debug_input == 'api':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = False 
    elif debug_input == 'bam':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = True 

    # ----------------------------------------------------------------
    # test required parameters
    # ----------------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return (1)

    if not get_all:
        if (not bdds):
            logMsg = "Failure: -s server option is required"
            print_log.go(log_error, logMsg)
            return (1)

    # use server for the following prog (to consistent with outher program)
    server = bdds

    # ----------------------------------------------------------------
    # login to BAM
    # ----------------------------------------------------------------
    if https:
        BAM_URL = "https://" + config['hostname'] + "/Services/REST/v1/"
    else:
        BAM_URL = "http://" + config['hostname'] + "/Services/REST/v1/"       
    try:                   
        bam=BAM.BAM( BAM_URL, req_timeout)       
        response = bam.login( api, apiPw_decode )   #response.ok is checked in bam.login()
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) )   # mask username and pw in e when login fail
        print_log.go(log_error, logMsg)
        return(1)    

    # ----------------------------------------------------------------
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

        if get_all:
            try:
                result_list = bam.getEntities(confid, "Server", 0, max_obj_count)
            except ValueError as e:
                logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            for ent in result_list:
            
                if debug_api:
                    print (ent)

                properties = bam.splitProp(ent)
                
                fullhostname = ''
                
                if 'fullHostName' in properties:
                    fullhostname = properties['fullHostName']
                
                server_id = ent['id']
                # print (fullhostname)

                print ("BDDS Name: %s" % (ent['name']) )
                #print ("  Object Id: %s" % (server_id) )
                print ("  profile: %s " % (properties['profile']) )
                
                # print service ipv4/ipv6 interface info
                if "servicesIPv4Address" in properties:
                    print ("  Service IPv4 Interface: %s " % (properties['servicesIPv4Address']) )
                if "servicesIPv6Address" in properties:
                    print ("  Service IPv6 Interface: %s " % (properties['servicesIPv6Address']) )
                if "defaultInterfaceAddress" in properties:
                    print ("  defaultInterfaceAddress: %s " % (properties['defaultInterfaceAddress']) )
                
                #get all publish interfaces

                try:
                    ent2_list = bam.getEntities(server_id, "PublishedServerInterface", 0, max_obj_count)
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get server's publish interfce: %s" % (str(e), ent['name'])
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)


                # space line for publish interface
                print()
                for ent2 in ent2_list:
                    if ent2['id'] == '0':
                        pass
                        # no publish interface found
                        
                    else:
                        ent2_Properties = bam.splitProp(ent2)
                
                        #print (ent2_Properties)
                
                        publish_interface = False
                        if "publishedInterfaceAddress" in ent2_Properties:
                            print ("    published Interface Address: %s " %  (ent2_Properties['publishedInterfaceAddress']) )
                            publish_interface = True

                        if "publishedInterfaceIPv6Address" in ent2_Properties:
                            print ("    published Interface IPv6Address: %s " %  ( \
                                ent2_Properties['publishedInterfaceIPv6Address']) )
                            publish_interface = True

                        if publish_interface == True:
                            print ("    published interface host name: %s" % (ent2['name']) )
                        print()
                        
                #endof for result2_json in result2_list_json:
            #endof for result_json in result_list:
            logMsg = "Success: server found %s " % (server)
            print_log.go(log_info, logMsg)
            BAM.bam_logout(bam)
            return(0)
        
        else:   # of if get_all:  (print only one bdds)
            try:
                ent = bam.getEntityByName(confid, server, "Server")
            except ValueError as e:
                logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            serverid = ent['id']
            
            if serverid == 0:
                logMsg = "Failure: Failed to get server: %s" % server
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
                
            else: #of if serverid == 0:  (found server)
            
                properties = bam.splitProp(ent)
                fullhostname = properties['fullHostName']
                
                # print (fullhostname)

                print ("BDDS Name: %s" % (server) )
                print ("  profile: %s " % (properties['profile']) )
                
                
                # print service ipv4/ipv6 interface info
                if "servicesIPv4Address" in properties:
                    print ("  Service IPv4 Interface: %s " % (properties['servicesIPv4Address']) )
                if "servicesIPv6Address" in properties:
                    print ("  Service IPv6 Interface: %s " % (properties['servicesIPv6Address']) )
                if "defaultInterfaceAddress" in properties:
                    print ("  defaultInterfaceAddress: %s " % (properties['defaultInterfaceAddress']) )
                

                #get all publish interfaces

                try:
                    result_list2 = bam.getEntities(serverid, "PublishedServerInterface", 0, max_obj_count)
                        
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get server's publish interfce: %s" % (str(e), server)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                # print (result2_list_json)
                #
                # result2_list_json is a list
                # [ 
                #   {'id': 172155, 'name': 'dds12.xyz.corp', 'type': 'PublishedServerInterface', 
                #        'properties': 'publishedInterfaceAddress=192.168.2.4|publishedInterfaceIPv6Address=2001:DB8::4|'
                #   },
                # 
                #   {'id': 172156, 'name': 'dds12.xyz1.corp', 'type': 'PublishedServerInterface', 
                #    'properties': 'publishedInterfaceAddress=117.56.25.1|
                #        publishedInterfaceIPv6Address=2001:4420:6707:FE::1|'
                #   }
                # ]
                
                # space line for publish interface
                print()
                
                for ent2 in result_list2:
                    if ent2['id'] == '0':
                        pass
                        # no publish interface found
                    else:
                        ent2_Properties = bam.splitProp(ent2)
                
                        #print (ent2_Properties)
                
                        publish_interface = False
                        if "publishedInterfaceAddress" in ent2_Properties:
                            print ("    published Interface Address: %s " %  (ent2_Properties['publishedInterfaceAddress']) )
                            publish_interface = True

                        if "publishedInterfaceIPv6Address" in ent2_Properties:
                            print ("    published Interface IPv6Address: %s " %  ( \
                                ent2_Properties['publishedInterfaceIPv6Address']) )
                            publish_interface = True

                        if publish_interface == True:
                            print ("    published interface host name: %s" % (ent2['name']) )
                        print()

                #endof for result2_json in result2_list_json:
                logMsg = "Success: server found %s " % (server)
                print_log.go(log_info, logMsg)
                BAM.bam_logout(bam)
                return(0)

        #endof if get_all:
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)

# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    server_query()
    


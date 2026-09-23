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
# program name: ip_update.py
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 9.6
#
# v2.0-20260518
#   1. fixed IP state = static, there is no macAddress in prop issue.
#   2. add -m "" (clear MAC function)
#
# v1.0-20250126
#    Return value:
#       0 - both update success. 
#       1 - error (any one of the update is failed)
#

'''
ip_update -c config1 -i 10.1.1.10 -m 112233445566 -n "Joe Chen" -p
    -c config_name
    -i ip_address
    -n ip_name      (use quot if there's space in name. E.g. "Joe Chen")
    -m MAC_address  (-m "" : clear MAC address)
    [-s|-p|-r]
        -s Make_static
        -p Make_dhcp_reserved
        -r Make_reserved
'''


import getopt
import sys
import json
import os

import BAM

# ---------------------------------------------------------------------
# New module to replace BAM (zeep, SOAP)
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "1.0"

# to disable exception trackback info (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

#-------------------------------------------
# working & log path setup (Win & Linux)
#-------------------------------------------
win_workingDir = "./"
win_logPath = "./"
win_logFileName = "cli"
Linux_workingDir =  "./"
Linux_logPath =  "./"
Linux_logFileName = "cli"

#-------------------------------------------
# convertRR = False | False //whether to convert RR to lower cases when add/delete/query
#   A record: convert RR_Name
#-------------------------------------------
convertRR = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def ip4addr_update(*args): 

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
    # var setup
    # ---------------------------------------------------------------------
    logMsg = ''
    logMsg2 = ''        # for query script to build multiple result
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False
    
    configuration = None
    show_version = False
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    
    debug_user = False
    debug_api  = False
    debug_bam  = False
    
    confid = 0
    ipaddr = ''
    action = ''
    ip_name = ''
    
    #mac = ''
    mac_not_enter_string = 'thisIsAemptyHolder20260519'
    mac = mac_not_enter_string
    mac_not_enter = False
    mac_enter_empty = False
    
    mac_need_update = False
    
    hostInfo = ''
    overwrite = False
    
    rtn_value = 1
    ip_found = False
    
    
    no_action = False    
    action_make_static = 'MAKE_STATIC'
    action_make_reserved = 'MAKE_RESERVED'
    action_make_dhcp_reserved = 'MAKE_DHCP_RESERVED'

    
    mac_default = '00-00-00-00-00-00'
    
    
    
    user_input = ''
    ip_name_old = ''
    ip_mac_old = ''
    ip_mac_old_tmp = ''
    ip_state_old = ''

    update_ip_data = False
    update_ip_state = False

    mac_print = ''
    ip_name_print = ''
    user_input_print = ''

    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    logPath = ''
    logFileName = ''
    
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = win_workingDir
        logPath = win_logPath
        logFileName = win_logFileName
    else:
        # Linux platform
        workingDir = Linux_workingDir
        logPath = Linux_logPath
        logFileName = Linux_logFileName

    # BAM.get_input_cmd() is a function. 
    # will get user full input commands and remove ".py"-it will be used to append to log file
    
    #----------------------------------------------------------------
    #fixed log input issue when called by cli.py or python3 xxx.py
    #----------------------------------------------------------------
    #get program name. If prog is called by cli.py, then __name__ will be "a_query"
    prog_name = __name__
    
    #convert "_" to "-" in prog_name
    prog_name = prog_name.replace('_','-')
    
    if __name__ == '__main__': #this program is run by python directly (e.g. python3 a_query.py)
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
        return(1)  

    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:i:n:m:sprh", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:i:n:m:sprh", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True   
        elif o == "-c": configuration = v
        elif o == "-i": ipaddr = v
        elif o == "-n": ip_name = v
        elif o == "-m": mac = v
        elif o == "-s": action = action_make_static
        elif o == "-p": action = action_make_dhcp_reserved
        elif o == "-r": action = action_make_reserved
        elif o == "-o": overwrite = True
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-h":
            print (__doc__)
            return(0)

    if not opts:
        print (__doc__)
        return(0)

    if show_version == True:
        print("Version %s" % version)
        return(0)

    # ---------------------------------------------------------
    # debug setup
    # ---------------------------------------------------------
    if debug:
        debug_user = True    # for -d
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

    if debug_api:
        print ("--------------[debug: input parameter] ---------------")
        print(opts)
        print("")
    # ---------------------------------------------------------
    # test cli required parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)
    if (not ipaddr) or (ipaddr[0:1] == "-"):
        logMsg = "Failure: -i ip_address option is required"
        print_log.go(log_error, logMsg)
        return(1)
        
    if (not action):
        no_action = True
        pass

    if (action[0:1] == "-"):
        logMsg = "Failure: action cannot be '-' parameter entered error"
        print_log.go(log_error, logMsg)
        return(1)

    if (ip_name[0:1] == "-"):
        logMsg = "Failure: IP_Name cannot be '-' parameter entered error"
        print_log.go(log_error, logMsg)
        return(1)

    if (not action) and (not ip_name):
        logMsg = "Failure: [-p|-r|-s] cannot be all empty"
        print_log.go(log_error, logMsg)
        return(1)


    if (mac[0:1] == "-"):
        logMsg = "Failure: MAC cannot be '-' parameter entered error"
        print_log.go(log_error, logMsg)
        return(1)

    if mac == mac_not_enter_string:
        mac_not_enter = True
    else:
        if mac == '':
            mac_enter_empty = True


    if action == action_make_dhcp_reserved:
        if mac_enter_empty:
            logMsg = "Failure: -p need to have MAC address"
            print_log.go(log_error, logMsg)
            return(1)

    if debug_api:
        print ("--------------[debug:mac_not_enter,mac_enter_empty ] ---------------")
        print (mac_not_enter)
        print (mac_enter_empty)

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
    
    try:    #for general api exception
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
                
            # note: config != 0
            
            # ------------------------------------------------ 
            # Search for target IP
            # ------------------------------------------------ 
            try:
                network_ent = bam.getIPRangedByIP(confid, "IP4Network", ipaddr)
                if debug_api:
                    print('---[debug: network_ent -----------------')
                    print(network_ent)
            
            except ValueError as e:
                logMsg = "Failure: %s fail to get IP address" % str(e)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(2)

            if network_ent['id'] == 0: # no entity found
                logMsg = "Failure: Network not found for IP:%s" % ipaddr
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)                
                
            else: # found network_ent

                network_id = network_ent['id']
                try:
                    ipaddr_ent = bam.getIP4Address(network_id, ipaddr)
                   
                    '''
                    #--- ent got from a dhcp ip ---
                    {'id': 100904, 'name': 'win2008-1', 'type': 'IP4Address', 
                        'properties': 
                        'macAddress=00-0C-29-F7-AA-9A
                        |address=10.2.2.16
                        |state=DHCP_FREE
                        |leaseTime=2024-11-01 19:14:37.0
                        |expiryTime=2024-11-02 19:14:37.0
                        |parameterRequestList=1,15,3,6,44,46,47,31,33,121,249,43
                        |vendorClassIdentifier=MSFT 5.0|'
                    }
                    '''                   
                except ValueError as e:
                    logMsg = "Failure: %s fail to get IP information" % str(e)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(2)
                
                if debug_api:
                    print('---[debug: ipaddr_ent -----------------')
                    print(ipaddr_ent)
               
                if ipaddr_ent['id'] == 0:
                    logMsg = "Failure: IP address %s not found" % ipaddr
                    print_log.go(log_error, logMsg)
                    ip_found = False
                
                else: # found ipaddr_ent. Update it
                
                    ip_name_old = ipaddr_ent['name']
                    prop = bam.splitProp(ipaddr_ent)
                    ip_state_old = prop['state']
                    
                    if 'macAddress' in prop:    # mac exists in existing IP
                    
                        prop_macAddress_exist = True
                        
                        ip_mac_old_tmp = prop['macAddress']
                        ip_mac_old = ip_mac_old_tmp.translate({ord('-'): None})
                        
                        
                        if mac_enter_empty:  # to delete mac
                            # remove key 'macAddress'
                            prop.pop('macAddress', None)
                            mac_need_update = True
                            
                        else:
                            if not mac_not_enter:
                                prop['macAddress'] = mac  #update mac if user's input is not empty
                                                          # if key 'macAddress' does not exist, 
                                                          # this command will add new key & value to dict
                                mac_need_update = True
                                                          
                    else: # mac does not exist in IP
                        
                       
                        # if no mac exist and user does not input mac - exit
                        if action == action_make_dhcp_reserved:
                            if mac_not_enter:
                                logMsg = "Failure: -p need to have MAC address"
                                print_log.go(log_error, logMsg)
                                return(1)
                        
                        
                        
                        
                        prop_macAddress_exist = False

                        if not mac_not_enter:
                            prop['macAddress'] = mac  #update mac if user's input is not empty
                            mac_need_update = True
                    
                    
                    #mac_not_enter
                    #mac_enter_empty
                    
                    if ip_name != '':
                        ipaddr_ent['name'] = ip_name    #update ip name if user's input is not empty

                        
                    user_input = ''

                    # action will be used in changeStateIP4Address()
                    # action is one of 'MAKE_STATIC' or 'MAKE_RESERVED' or 'MAKE_DHCP_RESERVED'
                    #     to call API
                    if action == action_make_static:
                        user_input = 'STATIC'
                    
                    elif action == action_make_dhcp_reserved:
                        user_input = 'DHCP_RESERVED'

                    elif action == action_make_reserved:
                        user_input = 'RESERVED'

                    if prop['state'] == 'GATEWAY':
                        pass #do nothing for Gateway
                    else:
                        # if current data and user input is same, don't do update
                        update_ip_state = False
                        update_ip_data = False
                        mac_print = ''
                        ip_name_print = ''
                        user_input_print = ''

                        if (prop['state'] != user_input) and (user_input != ''):
                            update_ip_state = True

                        if (ip_name_old != ip_name) and (ip_name != ''):
                            update_ip_data = True
                            ip_name_print = ip_name
                        else:
                            ip_name_print = '(no changes)'

                        # if (ip_mac_old != mac) and (mac != ''):
                        # xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                        
                        if mac_need_update:
                            update_ip_data = True
                            mac_print = mac
                        else:
                            mac_print = '(no changes)'

                        if user_input == '':
                            user_input_print = '(no changes)'
                        else:
                            user_input_print = user_input
                            
                        try:
                            ipaddr_ent['properties'] = bam.joinProp(prop)
                            
                            if update_ip_data:  # update only when existing data and user input are diff
                                
                                # --- update here (use update() to write "MAC, Name"---
                                bam.update(ipaddr_ent)

                                logMsg = ("Success: (updated IP data) update IP address:%s MAC_Old:%s " + \
                                         "MAC_New:%s Name_Old:%s Name_New:%s state_Old:%s state_New:%s") % (
                                              ipaddr, ip_mac_old, mac_print, ip_name_old, 
                                              ip_name_print, ip_state_old, user_input_print)
                                print_log.go(log_info, logMsg)
                                
                            if update_ip_state and not no_action:  #update only when data & user input are diff
                                
                                # --- update here ---
                                # action is one of 'MAKE_STATIC' or 'MAKE_RESERVED' or 'MAKE_DHCP_RESERVED'
                                
                                
                                if 'macAddress' in prop: 
                                    bam.changeStateIP4Address( ipaddr_ent['id'], action, prop['macAddress'] )
                                else:
                                    bam.changeStateIP4Address( ipaddr_ent['id'], action, '')
                                
                                
                                logMsg = ("Success: (updated IP state) update IP address:%s MAC_Old:%s "+ \
                                          "MAC_New:%s State_Old:%s State_New:%s ") % ( 
                                          ipaddr , ip_mac_old, mac_print, ip_state_old, user_input_print)
                                print_log.go(log_info, logMsg)
                            
                        except ValueError as e:     # except fosr any api error
                            logMsg = "%s" % ( str(e) )
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam) 
                            # if any one of the update fails, retunr (1)
                            return(1)

                        if (not update_ip_data) and (not update_ip_state):
                            logMsg = ("Success: (No update:Data are same) Current IP address:%s MAC:%s " + \
                                      "name:%s state:%s ") % (ipaddr , ip_mac_old, ip_name_old, ip_state_old)
                            print_log.go(log_info, logMsg)
            
        # endof if configuration:
        BAM.bam_logout(bam)
        return(0)   
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
        
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    ip4addr_update()

    

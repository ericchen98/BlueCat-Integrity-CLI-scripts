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
# v1.1-20260519
#       1. add -k to allow ping before assign IP
#       2. allow -s -r without entering MAC address
#       Note: "ping before assign" does not work with update(). It only work when adding a new IP.
#
# v1.0-20241117 
# vt1 this is completed with -k option
#

'''
ip4_add -c config1 -i 10.1.1.10 -m 112233445566 -n "Joe Chen" -p

    -c config_name
    -i IP_address
    -n IP_name (use quot if there's space in name. E.g. "Joe Chen")
    -m MAC_address
    -k [y|n] ("-k y" enable ping ckeck when assign IP. "-k n" disable ping check when assign IP)
    [-s | -p | -r]
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

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
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
def ip4addr_add(*args): 

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
    mac = ''
    hostInfo = ''
        
    action_make_static = 'MAKE_STATIC'
    action_make_reserved = 'MAKE_RESERVED'
    action_make_dhcp_reserved = 'MAKE_DHCP_RESERVED'

    ping_check_enable = ''
    ping_check = False
    ping_check_not_set = False
    
    mac_default = '00-00-00-00-00-00'


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
    #     will get user full input commands and remove ".py" - it will be used to append to log file
    
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
            opts, args = getopt.getopt(  input_args, "dc:i:n:m:sprk:h", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:i:n:m:sprk:h", ["debug=","version"])
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
        elif o == "-k": ping_check_enable = v
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
        
    if (not action) or (action[0:1] == "-"):
        logMsg = "Failure: [-s | -p | -r] one of the option is required"
        print_log.go(log_error, logMsg)
        return(1)



    #if (not mac) or (mac[0:1] == "-"):
    #    mac = mac_default

    if action == action_make_dhcp_reserved:
        if mac=='':
            logMsg = "Failure: for dhcp reserve (-p), -m with MAC is required"
            print_log.go(log_error, logMsg)
            return(1)


    if mac[0:1] == "-":
        logMsg = "Failure: -m with MAC is required"
        print_log.go(log_error, logMsg)
        return(1)


    if ping_check_enable[0:1] == "-":
        logMsg = "Failure: -k [y|n] option is required"
        print_log.go(log_error, logMsg)
        return(1)
    else:
        if ping_check_enable != '':
            if ping_check_enable.upper() == 'Y':
                ping_check = True
            elif ping_check_enable.upper() == 'N':
                ping_check = False
            else:
                logMsg = "Failure: -k [y|n] option input error"
                print_log.go(log_error, logMsg)
                return(1)
        else:
            #ping check not set
            ping_check_not_set = True
            
        
        
        
    #if (ip_name[0:1] == "-"):
    #    ip_name = ''


    #print(action)
    #print(ip_name)
    #print(mac)

    #return    
        
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

                # ------------------------------------------------ 
                # End of read config/view/zone 
                # ------------------------------------------------ 
                
            # config != 0
            try:
                
                # build empty prop first
                prop = {}
                
                # set ip name 
                prop['name'] = ip_name
                
                if ping_check:
                    prop['pingBeforeAssign'] = 'enable'
                    
                 #pingBeforeAssign=enable 
                
                prop_to_go = bam.joinProp(prop)
                
                if debug_api:
                    print ("--------------[debug: properity of IP address to assign] ---------------")
                    print(prop_to_go)
                    print("")
                
                
                rtn = bam.assignIP4Address( confid, ipaddr, mac, hostInfo, action, prop_to_go)
                obj_id = rtn
                #rtn is obj id
               
                #example of calling assignIP4Address()
                #rtn = bam.assignIP4Address( '100882', '10.1.1.21', '11-22-33-44-55-66', '', 'MAKE_STATIC', '')
                
                
                logMsg = "Success: set IP address:%s Mac:%s Type:%s Name:%s id:%s" % (ipaddr , mac, action, 
                                                                                        ip_name, obj_id)
                print_log.go(log_info, logMsg)
                
            except ValueError as e:
                logMsg = "Failure: %s fail to add IP address" % str(e)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

                
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
    ip4addr_add()
    

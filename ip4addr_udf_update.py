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
#
# v1.1-20260524     rename ip4_udf_update.py to ip4addr_udf_update.py
# v1.0-20260521     create ip4_udf_update.py
#
#

'''
ip4addr_udf_update -c config1 -i 10.1.1.10 -u UDF_name -a 'New_UDF_value'

    -c config       configuration_name
    -i IP4Address   IP4 address
    -u UDF_name     UDF field name (not the UDF display name)
    -a UDF_value    UDF data
    -x              delete existing UDF data
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
def ip4_udf_update(*args): 

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
    udf = ''
    udfNew = ''
    udfOld = ''
    clearUdf = False


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
            opts, args = getopt.getopt(  input_args, "dc:i:u:a:xh", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:i:u:a:xh", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True   
        elif o == "-c": configuration = v
        elif o == "-i": ipaddr = v
        elif o == "-u": udf = v
        elif o == "-a": udfNew = v  
        elif o == "-x": clearUdf = True 
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
        
    if (not udf) or (udf[0:1] == "-"):
        logMsg = "Failure: -u UDF_name is required"
        print_log.go(log_error, logMsg)
        return(1)
        
    if clearUdf:
        pass # if -d, no need to have "-a udfNew"
    else: 
        # "-a udfNew" is required
        if (not udfNew) or (udfNew[0:1] == "-"):
            logMsg = "Failure: -a udfNew is required"
            print_log.go(log_error, logMsg)
            return(1)
        
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
                    if ipaddr_ent['id'] == 0:
                        logMsg = "Failure: Fail to get IP address: %s" % ipaddr
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

                except ValueError as e:
                    logMsg = "Failure: %s fail to get IP address" % str(e)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                
                if debug_api:
                    print('---[debug: ipaddr_ent -----------------')
                    print(ipaddr_ent)
               
                if ipaddr_ent['id'] == 0:
                    logMsg = "Failure: IP address %s not found" % ipaddr
                    print_log.go(log_error, logMsg)
                    ip_found = False
                
                else: # found ipaddr_ent. Update it
                
                    prop = bam.splitProp(ipaddr_ent)
                    
                    # print(prop)
                    # {'udf_state': 'ip-in-used', 'address': '10.1.3.11', 'state': 'STATIC'}
                    
                
                    if debug_api:
                        print('---[debug: prop -----------------')
                        print(prop)
                    
                    
                    
                    if udf in prop:    # udf exists in IP (use has set UDF)
                        
                        
                        # if delete it
                        if clearUdf:
                            try:
                                udfOld = prop[udf]
                                
                                # note: use prop.pop(udf,None) does not work for BAM API!! Need to set udf = '' to clear it
                                
                                # set udf to '' to clear it
                                prop[udf] = ''
                                
                                ipaddr_ent['properties'] = bam.joinProp(prop)
                                
                                
                                if debug_api:
                                    print('---[debug: ipaddr_ent befre update() -----------------')
                                    print(ipaddr_ent)
                                
                                # --- update here (use update() to write "MAC, Name"---
                                bam.update(ipaddr_ent)

                                logMsg = ('Success: clear IP address:%s UDF_field: "%s" Value(old): "%s" ') % (
                                              ipaddr, udf, udfOld )
                                print_log.go(log_info, logMsg)
                            
                            except ValueError as e:     # except fosr any api error
                                logMsg = "%s" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam) 
                                return(1)
                          
                        
                        else: # not clear UDF
                        
                            # ---- change UDF ----
                            try:
                                udfOld = prop[udf]
                                prop[udf] = udfNew
                                
                                ipaddr_ent['properties'] = bam.joinProp(prop)
                                
                                    
                                # --- update here (use update() to write "MAC, Name"---
                                bam.update(ipaddr_ent)

                                logMsg = ('Success: update IP address:%s UDF_field: "%s" Value(old): "%s" to Value(new): "%s" ') % (
                                              ipaddr, udf, udfOld, udfNew )
                                print_log.go(log_info, logMsg)
                                    
                                
                            except ValueError as e:     # except fosr any api error
                                logMsg = "%s" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam) 
                                # if any one of the update fails, retunr (1)
                                return(1)
                        
                        
                    else: #of  if udf in prop:
                    
                        # udf value does not exist, add it
                        
                        if clearUdf:
                            logMsg = ('Success: clear IP address:%s UDF_field: "%s" does not exist (no need to clear)') % (
                                          ipaddr, udf )
                            print_log.go(log_info, logMsg)
                        
                        
                        else:
                            try:
                                prop[udf] = udfNew
                                ipaddr_ent['properties'] = bam.joinProp(prop)
                                    
                                # --- update here (use update() to write "MAC, Name"---
                                bam.update(ipaddr_ent)

                                logMsg = ('Success: update IP address:%s UDF_field: "%s" Value(old): %s to Value(new): "%s"') % (
                                              ipaddr, udf, udfOld, udfNew )
                                print_log.go(log_info, logMsg)
                                    
                                
                            except ValueError as e:     # except fosr any api error
                                logMsg = "%s" % ( str(e) )
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam) 
                                # if any one of the update fails, retunr (1)
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
    ip4_udf_update()
    

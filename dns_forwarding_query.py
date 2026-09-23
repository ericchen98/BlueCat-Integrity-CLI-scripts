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
#
# This program only work with match client from "view" only.
# if matchclients is set on BDDS, this script won't work yet.(to be added -s bdds) function 
#
# v2.1-20230828 fixed log does not show in cli.py issue 
# v2.0-20221226 change log dir to "./"
# v1.0: initial version
#

"""
dns-forwarding-query  -c config1 -v view1 

    -c config_name
    -v view_name  
"""

import getopt
import sys
import json
import ipaddress
import os

# ------------- module by BlueCat ---------
import BAM

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "2.1"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def dns_forwarding_query(*args):    

    # -------------------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    # -------------------------------------------------------------------------------
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_view

    # ---------------------------------------------------------------------
    # var setup
    # ---------------------------------------------------------------------
    # default = 3 sec. If change any  other number, it will overwrite REST requests timeout value
    req_timeout = 5

    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''
    
    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # ------ Other var (2021/2/25) ------
    api=''
    apiPw=''
    https=False

    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    forwardingIP = None
    user = None
    show_version = False

    confid = 0
    viewid = 0
    zoneid = 0

    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

    sameAsZone = None
    sameAsZone_Message = ""

    addrList = []
    ip_match = False
    index = 0
    addptr= False
    propertiesString = ''

    foo1=None
    addrList_sort =''

    do_config = False
    do_view = False
    
    disable_forward_child_zones = ''

    # read max obj count in API
    max_obj_count = "1000"

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

    # --------------------------------------------------------------
    # load config by BAM.load_config()  return json format "config"
    # --------------------------------------------------------------
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
            opts, args = getopt.getopt(  input_args, "dc:v:h", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-i": forwardingIP = v
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
    # ---------------------------------------------------------
    # test cli parameters 
    # ---------------------------------------------------------
    
    do_config = False
    do_view = False
    
    if (configuration) and (configuration[0:1] != "-"):
        if (view) and (configuration[0:1] != "-"):
            do_view = True
        else:
            do_config = True
    else:
        logMsg = "Failure: -c config option is required"
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
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
        
        value = ''
        if do_config:
            
            ent = bam.getDNSDeploymentOption(confid, "forwarding", "0")
            
            # 100900 is dds id
            #ent = bam.getDNSDeploymentOption(confid, "forwarding", "100900")

      
            # {'id': 433442, 'name': 'forwarding', 'type': 'DNS', 
            #    'value': 'true,8.8.8.8,1.1.1.1', 
            #   'properties': 'inherited=false|'}
            
            
            if debug_api: 
                print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                print(ent)
            
            if ent['id']== 0:
                logMsg = "Failure: Failed to query DNS forwarding option of config: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
            
            else:
                value = ent['value']
                split_value = value.split(",")
                
                ip_join = ''
                for i in range(1,len(split_value)) :
                    if i==1:
                        ip_join = split_value[i]
                    else:
                        ip_join = ip_join + ','+ split_value[i]
                disable_forward_child_zones = split_value[0]
                    
                logMsg =  "Success: query existing DNS forwarding option: %s Disable forwarding for Child zone: %s" % ( 
                                                    ip_join, disable_forward_child_zones )
                print_log.go(log_info, logMsg)
                BAM.bam_logout(bam)
                return(0)
            
        elif do_view:         
                
            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                    
                try:
                    ent = bam.getDNSDeploymentOption(viewid, "forwarding", "0")
                    
                    if debug_api: 
                        print('[debug: ------- search result of getDNSDeploymentOption() -------]')
                        print(ent)
                        print()
                
                    if ent['id']== 0:
                        logMsg = "Failure: Failed to query DNS forwarding option of config: %s view: %s" % (configuration,view)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                    
                    else:
                        value = ent['value']
                        split_value = value.split(",")
                        
                        ip_join = ''
                        for i in range(1,len(split_value)) :
                            if i==1:
                                ip_join = split_value[i]
                            else:
                                ip_join = ip_join + ','+ split_value[i]
                        disable_forward_child_zones = split_value[0]
                            
                        logMsg =  "Success: query existing DNS forwarding option: %s Disable forwarding for Child zone: %s" % ( 
                                                            ip_join, disable_forward_child_zones )
                        print_log.go(log_info, logMsg)
                        BAM.bam_logout(bam)
                        return(0)
                    
                except ValueError as e:
                        logMsg = "Failure: %s Failed to query DNS forwarding option" % ( str(e) )
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
            #endof if view:
            
        #endof if do_config:
            
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    dns_forwarding_query()
    

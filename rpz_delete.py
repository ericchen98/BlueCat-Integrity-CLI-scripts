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
# v1.3-20240706 add "-c config" to help
# v1.2-20230828 fixed log does not show in cli.py issue 
# v1.1 update help
# v1.0 use BAM.py v20230809
#
# log path and file name is defined by:
#   logPath = "/var/log/bluecat/"
#   logFileName = "cli"
#
#   rpz_add()               : add rpz policy item
#   rpz_delete()            : delete rpz policy item
#   rpzPolicy_add()         : add rpz policy
#   rpzPolicy_delete()      : delete rpz policy
#
#
# --- example of how to call rpz_add() ---
#from rpz_add import rpz_add
#
#rtn=1
#
#confg_flag = '-c'
#config_name = 'config1'
#rpz_flag = '-r'
#rpz = 'local-block-policy'
#item_flag = '-i'
#item = "a11.test.corp"
#
#arg_list =  [confg_flag, config_name, rpz_flag, rpz, item_flag, item ]
#
#rtn = rpz_add( *arg_list )
# ---------------------------------------
#
#


'''
rpz-delete.py -c config -r ReponsePolicy-1  -i a1.test.corp 

    -c config                   # config name
    -r ReponsePolicy_name       # RPZ policy name
    -i a1.test.corp             # RPZ policy item to be added

    # Delete a RPZ policy item from a BAM RPZ ReponsePolicy
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

version = "1.3"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0


# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def rpz_delete(*args): 

    # rpz_add(

    # convert args to string (for logging)
    passed_args = ''
    for tmp in args:
        passed_args = passed_args + ' '+ tmp 
    
    passed_args = " [arguments]: rpz_delete" + passed_args
    #print(passed_args)

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
    log_prog_type_index = prog_type_update

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # decide to enlarge it to 120sec (2min) in case there is a big upload list file
    req_timeout = 3

    # read max obj count in API
    max_obj_count = "10000"

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
    
    rpz = None
    fileName = None
    
    view = None
    zone = None
    rrName = None
    rdata = None
    
    matchclient = None
    user = None
    sameAsZone = False
    show_version = False
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    
    debug_user = False
    debug_api  = False
    debug_bam  = False
    
    confid = 0
    viewid = 0
    zoneid = 0


    rpz_ent_id = ''
    rpz_item = ''
    options = ''  #form api guide addResponsePolicyItem(): typee: array /Reserved for future use


    RecordPrintCount = 0
    query_ok_flag = False

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
        logPath = "/var/log/bluecat/"
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
        print_log.go(log_error, logMsg )
        return(1)  

    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:r:i:h", ["debug=","version"])           
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:r:i:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg )
        return(0) 
    
    for o,v in opts:
        if o == "-d": debug = True
        elif o == "-c": configuration = v
        elif o == "-r": rpz = v
        elif o == "-i": rpz_item = v
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
        sys.tracebacklimit = 1000   # turn on tracking. default value is 1000
        debug_user = True
        debug_api = True 
        debug_bam = False 
    elif debug_input == 'bam':
        sys.tracebacklimit = 1000   # turn on tracking. default value is 1000
        debug_user = True
        debug_api = True 
        debug_bam = True 

    # note: sys.tracebacklimit = 0 
    #       This is to disable exception trackback information (if not set, 
    #       urllib3 excpetion will be printed to screen)
    # the # default value = 1000
    
    # ---------------------------------------------------------
    # test cli required parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg )
        return(1)

    if (not rpz) or (rpz[0:1] == "-"):
        logMsg = "Failure: -r rpz option is required"
        print_log.go(log_error, logMsg )
        return(1)
    
    if (not rpz) or (rpz[0:1] == "-"):
        logMsg = "Failure: -r rpz_policy_Name is required"
        print_log.go(log_error, logMsg )
        return(1)

    if (not rpz_item) or (rpz_item[0:1] == "-"):
        logMsg = "Failure: -i rpz_item is required"
        print_log.go(log_error, logMsg )
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

        # login. token will be saved inside bam()   
        response = bam.login( api, apiPw_decode )
        
        if not response.ok:     # response.ok == True (status_code less than 200)
            logMsg = response.text
            print_log.go(log_error, logMsg )
            return(1)                    
        
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) ) # mask username and pw in e when login fail
        print_log.go(log_error, logMsg )
        return(1)
        
    # ----------------------------------------------------------------
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    
    
    
    try:    #for general api exception
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration", debug_bam)
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg )
                return (1)
            
            try:
                rpz_ent = bam.getEntityByName(confid, rpz, "ResponsePolicy")
                rpz_ent_id = rpz_ent['id']
                
                if debug_api: 
                    print(rpz_ent)
                    
                # {'id': 171813, 'name': 'ReponsePolicy-1', 'type': 'ResponsePolicy', 
                #   'properties': 'ttl=3600|responsePolicyType=BLACKLIST|'}
                
                if rpz_ent_id == 0:
                    logMsg = "Failure: fail to get Response Policy %s" % rpz
                    print_log.go(log_error, logMsg )
                    BAM.bam_logout(bam)
                    return(1)
                    
            except ValueError as e:
                logMsg = "Failure: %s fail to get Response Policy" % str(e)
                print_log.go(log_error, logMsg )
                BAM.bam_logout(bam)
                return(1)
    
            rtn = bam.deleteResponsePolicyItem(rpz_ent_id, rpz_item, options)

            #return '1' if add success
            #return '0' if item does not exist
            
            return_code = 1
            
            if rtn == "1":
                # add success
                logMsg = "Success: delete Response Policy item %s"  % ( rpz_item )
                print_log.go(log_info, logMsg )
                return_code = 0
            else:
                # return false: item exists already
                logMsg = "False: item does not exist: %s"  % ( rpz_item )
                print_log.go(log_error, logMsg )
                return_code = 1

            BAM.bam_logout(bam)
            return(return_code) 


    except ValueError as e:     # except fosr any api error
        logMsg = "%s [API error]" % ( str(e) )
        print_log.go(log_error, logMsg )
        BAM.bam_logout(bam)
        exit(1)
        
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    rpz_delete()
    

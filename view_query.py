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
# v5.6-20230828 fixed log does not show in cli.py issue 
# v5.5-20230827 change "-l" to "-a" to match other scripts
# v5.4-20221226 change log dir to "./"
# v5.3-20220221 update BAM.bam_logout(bam) before all return()
# v5.1-20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# v4.2 2021/7/17 use pw in BAM, change parameter
# v4.0 2021/7/9 use new BAM that work with 9.3 & REST
#       - modify to work with python 3
#       - use bam.find_zone()
#       - use print_log class in BAM.py
#

'''
view-query -c config1 -a              
view-query -c config1 -v view1 

    -c config_name
    -a list all views under config_name
    -v view_name
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
version = "5.6"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def view_query(*args):    

    # -------------------------------------------------------------------------------
    # First step, define log_prog_type_index : to be called in BAM.print_log()
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

    # ------ Other var ------
    api=''
    apiPw=''
    https=False

    # read max obj count in API
    max_obj_count = "1000"

    debug = False
    
    # ------------------------------------------
    configuration = None

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

    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

    allView = False
    
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
            opts, args = getopt.getopt(  input_args, "dc:v:ah", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:ah", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-a": allView = True
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
    # test cli required parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)
    
    if (not view):
        if not allView:
            logMsg = "Failure: -a option is required"
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
    # Start to get data from BAM
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
            if allView:
                try:
                    rtn_list = bam.getEntities(confid, "View", 0, max_obj_count)
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get view: %s" % (str(e), view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                RecordPrintCount=0
                show_list = ""

                for viewEnt in rtn_list:
                    print ("View name: %s" % viewEnt['name'])
                    RecordPrintCount=RecordPrintCount+1
                    if RecordPrintCount == 1:
                        show_list = show_list + viewEnt['name'] 
                    else:
                        show_list =  show_list + ',' + viewEnt['name']

                if RecordPrintCount==0:
                    logMsg = "Failure: No data found!" 
                    print_log.go(log_error, logMsg)
                else:
                    logMsg = "Success: success to get view: %s" % (show_list)
                    print_log.log_only(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(0)
            else:   # of if allView: (do: query single view name)
                try:
                    ent = bam.getEntityByName(confid, view, "View")
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get configuration: %s" % (str(e), configuration)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else:
                    viewid = ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % view
                    print_log.go(log_error, logMsg)
                else:
                    logMsg = "Success: found view: %s" % view
                    print_log.go(log_info, logMsg)
                BAM.bam_logout(bam)
                return(0) 
            #endof if allView:
        #endof if configuration:
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
        
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    view_query()
                     
                    

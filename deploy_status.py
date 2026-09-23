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
# program name: a-delete.py
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
# https://opensource.org/licenses/Python-2.0#
#
#   Deploy status return code:
#       EXECUTING = -1
#       INITIALIZING = 0
#       QUEUED = 1
#       CANCELLED = 2
#       FAILED = 3
#       NOT_DEPLOYED = 4
#       WARNING = 5
#       INVALID = 6
#       DONE = 7
#       NO_RECENT_DEPLOYMENT = 8
#
# v2.4-20231106 modify -f -w default value
# v2.3-20230828 fixed log does not show in cli.py issue 
# v2.2-20230827 rename getDeployStatus() to deploy-status()
# v2.1-20230824 change -t (wait_time) to -w as -t is conflit in deployServer (-t type)
# v1.2-20230701
# v1.0-20230316 created
#

"""
getDeployStatus -c config1 -s ServerName [-f requence -w wait_time]

    -c config_name
    -s BDDS_server_name
    -f frequency  # default 20 times 
    -w wait_time  # default 1 seconds (By defaut, max check time will be 1*20=20sec)
    Possible return value: 
       EXECUTING, INITIALIZING, QUEUED, CANCELLED, FAILED, 
       NOT_DEPLOYED, WARNING, INVALID, DONE, NO_RECENT_DEPLOYMENT

    Note: Server name is case sensitive!
"""
import getopt
import sys
import json
import os
import time

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

version = "2.4"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def deploy_status(*args):    

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
    log_prog_type_index = prog_type_other

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"

    deploy_rtn_code = { "-1":"EXECUTING", "0":"INITIALIZING", "1":"QUEUED","2":"CANCELLED",
                     "3":"FAILED","4":"NOT_DEPLOYED","5":"WARNING","6":"INVALID","7":"Done",
                     "8":"NO_RECENT_DEPLOYMENT" }

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
    server = None
    
    # not used
    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    show_version = False
    
    # default value
    frequency = 20
    wait_time = 1
    
    input_frequency = ""     #str for getop input
    input_wait_time = ""   #str for getop input

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    
    record_changed = False

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
            opts, args = getopt.getopt(  input_args, "dc:s:t:f:w:h", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:s:t:f:w:h", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-c": configuration = v 
        elif o == "-d": debug = True
        elif o == "-s": server = v
        elif o == "-f": input_frequency = v
        elif o == "-w": input_wait_time = v
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
    

    # test required parameters
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return (1)

    if (not server) or (server[0:1] == "-"):
        logMsg = "Failure: -s server option is required"
        print_log.go(log_error, logMsg)
        return (1)

    if (input_frequency[0:1] == "-"):
        logMsg = "Failure: -f frequency error"
        print_log.go(log_error, logMsg)
        return (1)
    else:
        try:
            if input_frequency == '':
                #do nothing. because frequency is the correct initial value
                pass 
            else:
                #convert str to int
                frequency = int(input_frequency)
        except:
            logMsg = "Failure: -f frequency error"
            print_log.go(log_error, logMsg)
            return (1)


    if (input_wait_time[0:1] == "-"):
        logMsg = "Failure: -w wait_time"
        print_log.go(log_error, logMsg)
        return (1)
    else:
        try:
            if input_wait_time == '':
                pass
            else:
                wait_time = int(input_wait_time)
        except:
            logMsg = "Failure: -w wait_time"
            print_log.go(log_error, logMsg)
            return (1)
    
    
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
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    try: #for api error
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
        
            if server:
                try:
                    ent = bam.getEntityByName(confid, server, "Server")
                    serverid = ent['id']
                    
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                
                # print(ent)
                # output
                # {'id': 100895, 'name': 'dds1', 'type': 'Server', 
                #   'properties': 
                #     'defaultInterfaceAddress=10.1.1.106|
                #      fullHostName=dds1.test.corp|
                #      servicesIPv4Address=10.1.1.106|
                #      profile=DNS_DHCP_GEN4_2000|'
                #  }

                if serverid == 0: 
                    logMsg = "Failure: Failed to get server: %s" % server
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else: #of if serverid == 0:
                    properties = bam.splitProp(ent)
                    fullhostname = properties['fullHostName']
                    
                try:
                    rtn_sif = bam.getEntityByName(serverid, fullhostname,  "NetworkServerInterface")
                    sifid = rtn_sif['id']
                    
                except ValueError as e:
                    logMsg = "Failure: %s Failed to get server: %s" % (str(e), server)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                    
                # ------- debug only (for sifid ) --------
                # print (f'{sifid}........')
                # print (rtn_sif)
                # output
                # {'id': 100896, 'name': 'dds1.test.corp', 'type': 'NetworkServerInterface', 
                # 'properties': 'defaultInterfaceAddress=10.1.1.106|servicesIPv4Address=10.1.1.106|'}
                
                if sifid == 0:
                    # this is to check whether there's network interface (do we need it?)
                    # but sifid is not used in deployServer()
                    logMsg = "Failure: Failed to get server interface id: %s" % server
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else:
                
                
                    for i in range(frequency):
                        try:
                            rtn = bam.getServerDeploymentStatus(serverid, '')
                            #---debug only ---
                            #print(rtn)    
                            #print (deploy_rtn_code[rtn] )
                            
                        except ValueError as e:
                            logMsg = "Failure: %s Failed to get server deployment status: %s" % (str(e), server)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            return(1)

                        logMsg = "Success: get server deployment status: %s" % deploy_rtn_code[rtn]
                        print_log.go(log_info, logMsg)
                    
                        # deploy_rtn_code = { "-1":"EXECUTING", "0":"INITIALIZING", "1":"QUEUED","2":"CANCELLED",
                        # "3":"FAILED","4":"NOT_DEPLOYED","5":"WARNING","6":"INVALID","7":"Done",
                        # "8":"NO_RECENT_DEPLOYMENT" }

                        if debug:
                            print( "wait %s sec for %s/%s times. Return code=%s" % (wait_time, i+1, 
                                frequency, rtn) )

                        if rtn == "7":  # deploy_rtn_code == "7":Done
                            #found "done", exit for loop
                            break
                        else:
                            time.sleep(wait_time)
                        
                        if i == frequency-1:
                            logMsg = "Success: get server deployment status: %s" % "Check Finished."
                            print_log.go(log_info, logMsg)

                    #endof for i in range(frequency):
                    
                    BAM.bam_logout(bam)
                    return(0)
                    
                #endof if sifid == 0:
            #endof if server:
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
    deploy_status()
    


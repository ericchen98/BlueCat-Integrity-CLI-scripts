#!/usr/bin/python3
# coding:utf-8
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# Copyright 2017 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
#
# https://opensource.org/licenses/Python-2.0
#
# zone-query-all.py
#
# v5.5-20230828 fixed log does not show in cli.py issue 
# v5.4-20221220
#       1) modified: logPath = "./"
#       2) add flag convertRR=True to convert RR Name and rdata to "lower case".
# v5.3 20220402 fix parent zone not print ('*") problem
# v5.2-20220221 update BAM.bam_logout(bam) before all return()
# v5.1-20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# v4.1 2021/7/17 use pw in BAM
# v4.0 2021/7/9 use new BAM that work with 9.3 & REST
#       - modify to work with python 3
#       - use bam.find_zone()
#       - use print_log class in BAM.py
#

'''
zone-query-all -c config1 -v view1 -a   # list all zones 
zone-query-all -c config1 -v view1 -y   # list all zones only with deploy flag set.

    -c config_name
    -v view_name
    -a                  # list all zones
    -y                  # list all zones only with deploy flag set.
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

version = "5.5"

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

# max_obj_count is required for both printZone() and zone_query_all()
max_obj_count = "1000"

# ---------------------------------------------------------------------
def printZone(bam, parentZoneid, allzone):

    # allzone = true : print all
    # allzone = false : print only deploy flag set
    
    Newent = None
    Newviewid = None
    zoneEnt = None
    properties = None

    # don't need to use try here.
    # Newent = bam.getAllEntities(parentZoneid, "Zone")

    try:
        rtn_list = bam.getEntities(parentZoneid, "Zone", 0, max_obj_count)
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        raise
        #BAM.bam_logout(bam) 
        #exit(1)
        
    for zoneEnt in rtn_list:   
        # print zoneEnt
        # {u'properties': u'deployable=true|absoluteName=x3.test.corp|', u'type': u'Zone',
        #   u'id': 1293731, u'name': u'x3'}

        # zoneEnt['name'] will print only short name
        # print "Zone name: " , zoneEnt['name']
        
        properties = bam.splitProp(zoneEnt)
        
        # print(properties)
        
        sign = ''
        if properties['deployable'] == 'true':
            sign = '(*)'
        
        if allzone:
            print (properties['absoluteName'],sign)
            
        else:
            if properties['deployable'] == 'true':
                print (properties['absoluteName'],sign)
            
        # call recursive    
        parentid = zoneEnt['id']
        printZone(bam, parentid, allzone)
            
    # ---------- end of printZone() ----------
        

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def zone_query_all(*args):    


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

    allzone = None

    ViewToGet = None
    ZoneToGet = None
    HostsToGet = None

    printDeployOnly = False
    properties = None
    sign = ''

    # read max obj count in API
    max_obj_count = "1000"


    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    
    debug_user = False
    debug_api  = False
    debug_bam  = False

    # ------------------------------------------------------------------------
    # create workingDir, logPath, and logFileName (according to os type)
    #   logPath, and logFileName will be used in bam.print_log()__init__() to setup logger parameter
    # ------------------------------------------------------------------------
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
            opts, args = getopt.getopt(  input_args, "hdc:v:z:ay", ["debug=","version"])            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "hdc:v:z:ay", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 
        
    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v    # zone is not used. Should be removed, but keep it for compatibility.
        elif o == "-y": printDeployOnly = True    
        elif o == "-a": allzone = True
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v
        elif o == "-h":
            print (__doc__)
            return(1)

    if not opts:
        print (__doc__)
        return(1)

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

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required"
        print_log.go(log_error, logMsg)        
        return(1)

    if not (printDeployOnly or allzone):
        logMsg = "Failure: -a or -y option is required"
        print_log.go(log_error, logMsg)        
        return(1)

    # should not required as "zone" is not used. 
    '''
    if convertRR:
        if not (zone == None):
            zone = zone.lower()
        if not (rrName == None):
            rrName = rrName.lower()
    '''

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
               
            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                if allzone:
                    print ('### print all zones. (*) means deploy=True ###')
                else:
                    if printDeployOnly:
                        print ('### print zones with deploy flag set only ###')
                        
                try:
                    rtn_list = bam.getEntities(viewid, "Zone", 0, max_obj_count)
                except ValueError as e:
                    # raise ValueError, "Failed to get view %s" % view
                    logMsg = "Failure: %s Failed to get zone: %s" % (str(e), view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                RecordPrintCount=0
                show_list = ""
            
                for ZoneEnt in rtn_list:
                    # print (ZoneEnt)
                    # --- output ---
                    # {'id': 100917, 'name': 'corp', 'type': 'Zone', 
                    #   'properties': 'deployable=false|absoluteName=corp|'}
                    # {'id': 171586, 'name': 'corp2', 'type': 'Zone', 
                    #   'properties': 'deployable=false|absoluteName=corp2|'}
                    #
                    sign = ''
                    properties = bam.splitProp(ZoneEnt)

                    if properties['deployable'] == 'true':
                        sign = '(*)'    
                    if allzone:
                        print (properties['absoluteName'],sign)
                    else:
                        if printDeployOnly:
                            if properties['deployable'] == 'true':
                                print (properties['absoluteName'],sign)
                    parentid=ZoneEnt['id']
                    # call printZone() to print all zones
                    printZone(bam, parentid, allzone)
                    RecordPrintCount = RecordPrintCount + 1
                    
                #endof for ZoneEnt in rtn_list:

                if RecordPrintCount==0:
                    logMsg = "Failure: No record found!" 
                    print ()
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)
                else:
                    logMsg = "Success: success to get zone info" 
                    print ()
                    print_log.go(log_info, logMsg)                    
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
    zone_query_all()
